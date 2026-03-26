"""Profile handler."""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, renew_kb
from src.services.marzban import marzban_client
from src.services.subscription import get_or_create_user
from src.utils.helpers import bytes_to_gb, format_date, format_expiry_status

router = Router()
logger = logging.getLogger(__name__)

SUPPORT_NOTE = "\n\nЕсли проблема не решится — напишите @KzyuF"


@router.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Telegram: @{user.username or '—'}\n"
        f"Подписка: {format_expiry_status(user.subscription_end)}\n"
        f"Истекает: {format_date(user.subscription_end)}\n"
    )

    if user.marzban_username:
        try:
            usage = await marzban_client.get_user_usage(user.marzban_username)
            used = bytes_to_gb(usage["used_traffic"])
            text += f"Использовано трафика: {used} ГБ\n"
        except Exception:
            logger.exception("Ошибка получения данных из Marzban")
            text += "Трафик: нет данных" + SUPPORT_NOTE + "\n"

    kb = renew_kb() if not user.is_active else back_to_main_kb()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()
