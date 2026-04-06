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


async def ensure_xui_client(
    session: AsyncSession,
    user: User,
    limit_ip: int = 3,
) -> str:
    """Ensure user's 3X-UI client exists. Recreate if missing. Returns vless link."""
    client_email = user.marzban_username
    if not client_email:
        raise ValueError("User has no marzban_username")

    try:
        return await xui_client.get_vless_link(client_email)
    except Exception as exc:
        if not _is_not_found_error(exc):
            raise

    # Client not found — recreate it
    logger.warning("3X-UI client %s not found, recreating", client_email)

    # Determine expire: use subscription_end if active, otherwise 1 hour from now
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
            if _is_not_found_error(exc):
                logger.warning("Client %s not found in 3X-UI during activation, recreating", client_email)
                await xui_client.create_client(
                    email=client_email,
                    expire_timestamp_ms=expire_ts_ms,
                    limit_ip=3,
                )
            else:
                raise
    else:
        # New client — use telegram_id as email
        client_email = str(user.telegram_id)
        # Check if client already exists in 3X-UI (e.g. created via trial or web)
        existing = False
        try:
            link = await xui_client.get_vless_link(client_email)
            existing = True
        except (ValueError, Exception):
            pass

        if existing:
            client_uuid = _extract_uuid_from_vless(link)
            await xui_client.update_client(
                client_uuid=client_uuid,
                email=client_email,
                expire_timestamp_ms=expire_ts_ms,
                limit_ip=3,
            )
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
