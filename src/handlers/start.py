"""/start command, registration, referral, and fallback handler."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, info_kb, main_menu_kb
from src.models.user import User
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


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, command: CommandObject, session: AsyncSession) -> None:
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )

    # Handle referral deep link
    args = command.args or ""
    if args.startswith("ref_"):
        ref_code = args[4:]
        # Don't allow self-referral, and only set once
        if not user.referred_by:
            result = await session.execute(
                select(User).where(
                    User.referral_code == ref_code,
                    User.telegram_id != user.telegram_id,
                )
            )
            referrer = result.scalar_one_or_none()
            if referrer:
                user.referred_by = referrer.telegram_id
                await session.commit()
                logger.info(
                    "User %s referred by %s", user.telegram_id, referrer.telegram_id
                )

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


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


@router.callback_query(lambda c: c.data == "referral")
async def referral(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )

    if not user.is_active:
        await callback.message.edit_text(
            "👥 Реферальная программа доступна только для пользователей "
            "с активной подпиской. Купите подписку чтобы приглашать друзей.",
            reply_markup=back_to_main_kb(),
        )
        return

    text = (
        f"👥 <b>Пригласить друга</b>\n\n"
        f"Поделитесь ссылкой с другом. Когда он купит подписку от 1 месяца, "
        f"вы получите +15 дней к вашей подписке!\n\n"
        f"Ваша ссылка:\n"
        f"<code>https://t.me/glowvpnbot?start=ref_{user.referral_code}</code>\n\n"
        f"Приглашено друзей: {user.referral_count}"
    )
    await callback.message.edit_text(
        text, reply_markup=back_to_main_kb(), parse_mode="HTML"
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "Я бот и не понимаю сообщения. Используйте меню ниже:",
        reply_markup=main_menu_kb(),
    )
