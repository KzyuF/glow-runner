"""Support chat — user↔admin messaging via FSM states."""

import logging

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.keyboards import back_to_main_kb
from src.utils.config import settings

router = Router()
logger = logging.getLogger(__name__)


class SupportStates(StatesGroup):
    waiting_support_message = State()
    waiting_admin_reply = State()


@router.callback_query(lambda c: c.data == "support")
async def support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SupportStates.waiting_support_message)
    await callback.message.edit_text(
        "💬 <b>Поддержка</b>\n\n"
        "Напишите ваше сообщение и мы ответим вам в ближайшее время.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )


@router.message(SupportStates.waiting_support_message)
async def user_sends_support_message(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    await state.clear()

    username = message.from_user.username or "—"
    telegram_id = message.from_user.id
    user_text = message.text or "(без текста)"

    admin_text = (
        f"📩 <b>Сообщение от пользователя</b>\n"
        f"@{username} (ID: <code>{telegram_id}</code>):\n\n"
        f"{user_text}"
    )

    reply_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Ответить",
                callback_data=f"support_reply:{telegram_id}",
            )]
        ]
    )

    try:
        await bot.send_message(
            settings.admin_telegram_id,
            admin_text,
            reply_markup=reply_kb,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to forward support message to admin")

    await message.answer(
        "✅ Сообщение отправлено. Ожидайте ответа.",
        reply_markup=back_to_main_kb(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("support_reply:"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    parts = callback.data.split(":", 1)
    target_id = parts[1] if len(parts) > 1 else ""

    try:
        int(target_id)
    except (ValueError, TypeError):
        await callback.message.answer("Некорректный ID пользователя.")
        return

    await state.update_data(reply_to=target_id)
    await state.set_state(SupportStates.waiting_admin_reply)
    await callback.message.answer(
        f"Напишите ответ для пользователя <code>{target_id}</code>:",
        parse_mode="HTML",
    )


@router.message(SupportStates.waiting_admin_reply)
async def admin_sends_reply(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    target_id = int(data["reply_to"])
    await state.clear()

    reply_text = message.text or "(без текста)"

    try:
        await bot.send_message(
            target_id,
            f"💬 <b>Ответ от поддержки:</b>\n\n{reply_text}",
            parse_mode="HTML",
        )
        await message.answer("✅ Ответ отправлен.")
    except Exception:
        logger.exception("Failed to send reply to user %s", target_id)
        await message.answer("❌ Не удалось отправить ответ пользователю.")
