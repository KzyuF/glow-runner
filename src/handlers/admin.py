"""Admin commands — stats, broadcast."""

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.utils.config import settings

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_telegram_id


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    total = await session.scalar(select(func.count(User.id)))
    active = await session.scalar(
        select(func.count(User.id)).where(User.is_active.is_(True))
    )

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"Всего пользователей: {total}\n"
        f"Активных подписок: {active}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return

    text = message.text.partition("/broadcast")[2].strip()
    if not text:
        await message.answer("Использование: /broadcast <сообщение>")
        return

    result = await session.execute(
        select(User.telegram_id).where(User.telegram_id > 0)
    )
    user_ids = [row[0] for row in result.all()]

    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            logger.debug("Не удалось отправить сообщение пользователю %s", uid)

    await message.answer(f"✅ Рассылка завершена: {sent}/{len(user_ids)}")
