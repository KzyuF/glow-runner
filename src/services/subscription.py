"""Subscription service — create, renew, expire."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.services.marzban import marzban_client
from src.services.payment import PLANS

logger = logging.getLogger(__name__)



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

    expire_ts = int(new_end.timestamp())
    marzban_username = f"tg_{user.telegram_id}"

    if user.marzban_username:
        # Extend existing user
        await marzban_client.modify_user(
            marzban_username,
            expire=expire_ts,
            data_limit=0,
            status="active",
        )
    else:
        # Create new Marzban user
        await marzban_client.create_user(
            username=marzban_username,
            expire_timestamp=expire_ts,
            data_limit_bytes=0,
        )
        user.marzban_username = marzban_username

    user.subscription_end = new_end
    user.data_limit_gb = 0
    user.is_active = True
    await session.commit()

    link = await marzban_client.get_vless_link(marzban_username)
    return link
