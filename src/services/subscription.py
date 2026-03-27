"""Subscription service — create, renew, expire."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.services.xui_client import xui_client
from src.services.payment import PLANS

logger = logging.getLogger(__name__)


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
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def activate_subscription(
    session: AsyncSession,
    user: User,
    plan_key: str,
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
        client_uuid = link.split("://")[1].split("@")[0]
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
    await session.commit()

    link = await xui_client.get_vless_link(client_email)
    return link
