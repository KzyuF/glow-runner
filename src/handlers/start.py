"""/start command and registration."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, main_menu_kb
from src.services.subscription import get_or_create_user

router = Router()

WELCOME_TEXT = (
    "👋 Добро пожаловать в VPN-бот!\n\n"
    "Здесь вы можете купить быструю и надёжную VPN-подписку.\n"
    "Выберите действие:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb())
    await callback.answer()


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


@router.callback_query(lambda c: c.data == "howto")
async def howto(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        HOWTO_TEXT, reply_markup=back_to_main_kb(), parse_mode="HTML"
    )
    await callback.answer()
