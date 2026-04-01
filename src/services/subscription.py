"""Subscription service — create, renew, expire, referral bonus."""

import logging
import re
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


def _make_client_email(telegram_username: str | None, telegram_id: int) -> str:
    """Use Telegram @username if available, otherwise tg_{id}."""
    if telegram_username:
        return telegram_username
    return f"tg_{telegram_id}"


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Check if a user with this username was created via the website (telegram_id=0)
        if username:
            result2 = await session.execute(
                select(User).where(User.username == username, User.telegram_id == 0)
            )
            user = result2.scalar_one_or_none()
            if user is not None:
                user.telegram_id = telegram_id
                await session.commit()
                return user
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
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
    client_email = _make_client_email(user.username, user.telegram_id)

    if user.marzban_username:
        # Existing client — get UUID from the stored email and update
        client_email = user.marzban_username
        link = await xui_client.get_vless_link(client_email)
        # Extract UUID from vless://UUID@...
        client_uuid = _extract_uuid_from_vless(link)
        await xui_client.update_client(
            client_uuid=client_uuid,
            email=client_email,
            expire_timestamp_ms=expire_ts_ms,
        )
    else:
        # Create new 3X-UI client
        await xui_client.create_client(
            email=client_email,
            expire_timestamp_ms=expire_ts_ms,
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
