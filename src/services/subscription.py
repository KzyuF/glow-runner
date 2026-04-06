"""Subscription service — create, renew, expire, referral bonus."""

import logging
import re
import time
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.services.xui_client import xui_client
from src.services.payment import PLANS

logger = logging.getLogger(__name__)

REFERRAL_BONUS_DAYS = 15

_VLESS_UUID_RE = re.compile(r"^vless://([^@]+)@")


def _extract_uuid_from_vless(link: str) -> str:
    """Extract UUID from vless://UUID@... link safely."""
    m = _VLESS_UUID_RE.match(link)
    if not m:
        raise ValueError(f"Cannot extract UUID from vless link: {link[:60]}")
    return m.group(1)


def _is_not_found_error(exc: Exception) -> bool:
    """Check if exception indicates client not found in 3X-UI."""
    msg = str(exc).lower()
    return "not found" in msg or "inbound not found" in msg


def make_client_email(telegram_id: int, username: str | None) -> str:
    """Build 3X-UI client email: '{telegram_id}_{username}' or str(telegram_id)."""
    if username:
        return f"{telegram_id}_{username}"
    return str(telegram_id)


async def _find_existing_client(telegram_id: int, username: str | None) -> str | None:
    """Try to find client in 3X-UI: new format first, then old (bare telegram_id).
    Returns the email that was found, or None."""
    # Try new format: {telegram_id}_{username}
    new_email = make_client_email(telegram_id, username)
    try:
        await xui_client.get_vless_link(new_email)
        return new_email
    except Exception:
        pass

    # Try old format: just telegram_id
    old_email = str(telegram_id)
    if old_email != new_email:
        try:
            await xui_client.get_vless_link(old_email)
            return old_email
        except Exception:
            pass

    return None


async def ensure_xui_client(
    session: AsyncSession,
    user: User,
    limit_ip: int = 3,
) -> str:
    """Ensure user's 3X-UI client exists. Recreate if missing. Returns vless link."""
    client_email = user.marzban_username
    if not client_email:
        raise ValueError("User has no marzban_username")

    # Try stored email first
    try:
        return await xui_client.get_vless_link(client_email)
    except Exception as exc:
        if not _is_not_found_error(exc):
            raise

    # Stored email not found — try alternate formats (old/new) before recreating
    found = await _find_existing_client(user.telegram_id, user.username)
    if found and found != client_email:
        logger.info("Found client under alternate email %s (was %s), updating DB", found, client_email)
        user.marzban_username = found
        await session.commit()
        return await xui_client.get_vless_link(found)

    # Client truly missing — recreate with current email
    logger.warning("3X-UI client %s not found, recreating", client_email)
    now = datetime.utcnow()
    if user.subscription_end and user.subscription_end > now:
        expire_ms = int(user.subscription_end.timestamp() * 1000)
    else:
        expire_ms = int((now.timestamp() + 3600) * 1000)

    await xui_client.create_client(
        email=client_email,
        expire_timestamp_ms=expire_ms,
        limit_ip=limit_ip,
    )

    return await xui_client.get_vless_link(client_email)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    first_name: str | None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Check if a user with this username was created via the website (negative telegram_id)
        if username:
            result2 = await session.execute(
                select(User).where(User.username == username, User.telegram_id < 0)
            )
            user = result2.scalar_one_or_none()
            if user is not None:
                user.telegram_id = telegram_id
                if first_name:
                    user.first_name = first_name
                await session.commit()
                return user
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update username and first_name if changed
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.commit()
    return user


async def activate_subscription(
    session: AsyncSession,
    user: User,
    plan_key: str,
    bot: Bot | None = None,
) -> str:
    """Create or extend subscription. Returns vless:// link."""
    plan = PLANS[plan_key]
    now = datetime.utcnow()

    # Calculate new expiry
    if user.subscription_end and user.subscription_end > now:
        new_end = user.subscription_end + timedelta(days=plan["days"])
    else:
        new_end = now + timedelta(days=plan["days"])

    expire_ts_ms = int(new_end.timestamp() * 1000)

    if user.marzban_username:
        client_email = user.marzban_username
        # Try to update existing client; recreate if not found in 3X-UI
        try:
            link = await xui_client.get_vless_link(client_email)
            client_uuid = _extract_uuid_from_vless(link)
            await xui_client.update_client(
                client_uuid=client_uuid,
                email=client_email,
                expire_timestamp_ms=expire_ts_ms,
                limit_ip=3,
            )
        except Exception as exc:
            if not _is_not_found_error(exc):
                raise
            # Try to find under alternate email format
            found = await _find_existing_client(user.telegram_id, user.username)
            if found:
                logger.info("Found client under %s (DB had %s), updating", found, client_email)
                link = await xui_client.get_vless_link(found)
                client_uuid = _extract_uuid_from_vless(link)
                await xui_client.update_client(
                    client_uuid=client_uuid,
                    email=found,
                    expire_timestamp_ms=expire_ts_ms,
                    limit_ip=3,
                )
                client_email = found
                user.marzban_username = found
            else:
                # Truly missing — recreate with new format
                client_email = make_client_email(user.telegram_id, user.username)
                logger.warning("Client not found in 3X-UI, creating %s", client_email)
                await xui_client.create_client(
                    email=client_email,
                    expire_timestamp_ms=expire_ts_ms,
                    limit_ip=3,
                )
                user.marzban_username = client_email
    else:
        # New client — build email in new format
        client_email = make_client_email(user.telegram_id, user.username)
        # Check if client already exists in 3X-UI (new or old format)
        found = await _find_existing_client(user.telegram_id, user.username)
        if found:
            link = await xui_client.get_vless_link(found)
            client_uuid = _extract_uuid_from_vless(link)
            await xui_client.update_client(
                client_uuid=client_uuid,
                email=found,
                expire_timestamp_ms=expire_ts_ms,
                limit_ip=3,
            )
            client_email = found
        else:
            await xui_client.create_client(
                email=client_email,
                expire_timestamp_ms=expire_ts_ms,
                limit_ip=3,
            )
        user.marzban_username = client_email

    user.subscription_end = new_end
    user.data_limit_gb = 0
    user.is_active = True
    user.notifications_sent = ""
    await session.commit()

    # Referral bonus
    if user.referred_by and not user.referral_bonus_given:
        await _give_referral_bonus(session, user, bot)

    link = await xui_client.get_vless_link(client_email)
    return link


async def _give_referral_bonus(
    session: AsyncSession,
    user: User,
    bot: Bot | None,
) -> None:
    """Add +15 days to the referrer's subscription."""
    result = await session.execute(
        select(User).where(User.telegram_id == user.referred_by)
    )
    referrer = result.scalar_one_or_none()
    if not referrer:
        return

    now = datetime.utcnow()

    # Extend referrer subscription
    if referrer.subscription_end and referrer.subscription_end > now:
        referrer.subscription_end += timedelta(days=REFERRAL_BONUS_DAYS)
    else:
        referrer.subscription_end = now + timedelta(days=REFERRAL_BONUS_DAYS)
        referrer.is_active = True

    # Update 3X-UI expiry if referrer has a VPN account
    if referrer.marzban_username:
        try:
            new_expire_ms = int(referrer.subscription_end.timestamp() * 1000)
            link = await xui_client.get_vless_link(referrer.marzban_username)
            client_uuid = _extract_uuid_from_vless(link)
            await xui_client.update_client(
                client_uuid=client_uuid,
                email=referrer.marzban_username,
                expire_timestamp_ms=new_expire_ms,
            )
        except Exception:
            logger.exception("Failed to update referrer 3X-UI expiry — bonus not marked as given")
            await session.commit()
            return

    referrer.referral_count += 1
    user.referral_bonus_given = True
    await session.commit()

    # Notify referrer
    if bot:
        display_name = f"@{user.username}" if user.username else "друг"
        try:
            await bot.send_message(
                referrer.telegram_id,
                f"🎉 Ваш друг {display_name} купил подписку! "
                f"Вам начислено +{REFERRAL_BONUS_DAYS} дней.",
            )
        except Exception:
            logger.debug("Failed to notify referrer %s", referrer.telegram_id)
