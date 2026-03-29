"""/start command, registration, and fallback handler."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, info_kb, main_menu_kb
from src.services.subscription import get_or_create_user

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "🌐 Добро пожаловать в GlowVPN!\n\n"
    "Быстрый и надёжный VPN для вашей безопасности.\n\n"
    "⚡ Скорость до 755 Мбит/с\n"
    "🔒 Безлимитный трафик\n"
    "📱 До 3 устройств\n"
    "🕐 Подключение за 1 минуту\n\n"
    "Выберите действие:"
)

HELP_TEXT = (
    "📋 <b>Доступные команды:</b>\n\n"
    "/start — Главное меню\n"
    "/menu — Главное меню\n"
    "/help — Список команд\n\n"
    "По всем вопросам пишите: @KzyuF"
)

HOWTO_TEXT = (
    "📱 <b>Как подключиться к VPN</b>\n\n"
    "<b>Android:</b> V2RayNG или Hiddify\n"
    "<b>iOS:</b> Streisand или V2Box\n"
    "<b>Windows/Mac:</b> Hiddify или Nekoray\n\n"
    "<b>Инструкция:</b>\n"
    "1. Скопируйте ссылку из раздела «Мой VPN-ключ»\n"
    "2. Откройте приложение\n"
    "3. Нажмите «+» (добавить)\n"
    "4. Вставьте ссылку\n"
    "5. Подключитесь!"
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=back_to_main_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(lambda c: c.data == "howto")
async def howto(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        HOWTO_TEXT, reply_markup=back_to_main_kb(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "support")
async def support(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "💬 По всем вопросам пишите: @KzyuF",
        reply_markup=back_to_main_kb(),
    )


@router.callback_query(lambda c: c.data == "info")
async def info(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "📄 Документы GlowVPN:",
        reply_markup=info_kb(),
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "Я бот и не понимаю сообщения. Используйте меню ниже:",
        reply_markup=main_menu_kb(),
    )
