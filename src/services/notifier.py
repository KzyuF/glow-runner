"""Background notifier — subscription expiry reminders."""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from src.models.database import async_session
from src.models.user import User

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 3600  # 1 hour

THRESHOLDS = [
    ("7d", timedelta(days=7), "⏰ Ваша VPN-подписка истекает через 7 дней. Продлите подписку чтобы не потерять доступ!"),
    ("3d", timedelta(days=3), "⚠️ Ваша VPN-подписка истекает через 3 дня!"),
    ("1d", timedelta(days=1), "🔴 Ваша VPN-подписка истекает завтра!"),
    ("3h", timedelta(hours=3), "❗ Ваша VPN-подписка истекает через 3 часа! Продлите сейчас чтобы не потерять доступ!"),
]

RENEW_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy")],
    ]
)


def _parse_sent(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return set(raw.split(","))


def _dump_sent(sent: set[str]) -> str:
    return ",".join(sorted(sent))


async def _check_once(bot: Bot) -> None:
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active.is_(True),
                User.subscription_end.isnot(None),
                User.telegram_id > 0,
            )
        )
        users = result.scalars().all()

        for user in users:
            sent = _parse_sent(user.notifications_sent)
            changed = False

            for key, delta, text in THRESHOLDS:
                if key in sent:
                    continue
                time_left = user.subscription_end - now
                if time_left <= delta:
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            text,
                            reply_markup=RENEW_KB,
                        )
                        logger.info(
                            "Sent %s notification to %s", key, user.telegram_id
                        )
                    except Exception:
                        logger.debug(
                            "Failed to send %s notification to %s",
                            key, user.telegram_id,
                        )
                    sent.add(key)
                    changed = True

            if changed:
                user.notifications_sent = _dump_sent(sent)

        await session.commit()


async def run_notifier(bot: Bot) -> None:
    """Background loop — runs every CHECK_INTERVAL seconds."""
    while True:
        try:
            await _check_once(bot)
        except Exception:
            logger.exception("Notifier error")
        await asyncio.sleep(CHECK_INTERVAL)
