"""/start command, registration, referral, and fallback handler."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, howto_back_kb, howto_platforms_kb, info_kb, main_menu_kb
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

HOWTO_CHOOSE_TEXT = "📲 <b>Как подключиться к VPN</b>\n\nВыберите вашу платформу:"

HOWTO_ANDROID = (
    "📱 <b>Подключение на Android</b>\n\n"
    "<b>Шаг 1: Скачайте приложение</b>\n"
    "Рекомендуем HAPP или Hiddify:\n"
    "• <a href='https://play.google.com/store/apps/details?id=su.ffg.happ'>HAPP</a>\n"
    "• <a href='https://play.google.com/store/apps/details?id=app.hiddify.com'>Hiddify</a>\n"
    "• <a href='https://play.google.com/store/apps/details?id=com.v2ray.ang'>V2RayNG</a>\n\n"
    "<b>Шаг 2: Скопируйте VPN-ключ</b>\n"
    "Нажмите кнопку «🔑 Мой VPN-ключ» в главном меню бота. "
    "Нажмите на ключ чтобы скопировать его.\n\n"
    "<b>Шаг 3: Откройте приложение</b>\n"
    "Нажмите «+» → «Импорт из буфера обмена». Ключ добавится автоматически.\n\n"
    "<b>Шаг 4: Подключитесь</b>\n"
    "Нажмите кнопку подключения. Готово!"
)

HOWTO_IOS = (
    "🍎 <b>Подключение на iPhone/iPad</b>\n\n"
    "<b>Шаг 1: Скачайте приложение</b>\n"
    "Рекомендуемые приложения (доступны в российском App Store):\n"
    "• <a href='https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973'>HAPP Plus</a>\n"
    "• <a href='https://apps.apple.com/app/npv-tunnel/id1629465476'>Npv Tunnel</a>\n"
    "• <a href='https://apps.apple.com/app/v2rayu/id1569046443'>V2rayU</a>\n"
    "• <a href='https://apps.apple.com/app/v2ray-client/id6747379524'>V2Ray Client+</a>\n\n"
    "⚠️ Приложения Streisand, V2Box и v2RayTun были удалены из российского "
    "App Store.\n\n"
    "<b>Шаг 2: Скопируйте VPN-ключ</b>\n"
    "Нажмите «🔑 Мой VPN-ключ» в главном меню. Нажмите на ключ чтобы скопировать.\n\n"
    "<b>Шаг 3: Откройте HAPP Plus</b>\n"
    "Нажмите «+» в правом верхнем углу → «Из буфера обмена». Ключ добавится.\n\n"
    "<b>Шаг 4: Подключитесь</b>\n"
    "Выберите добавленный сервер и нажмите кнопку подключения. Готово!"
)

HOWTO_DESKTOP = (
    "💻 <b>Подключение на Windows/Mac</b>\n\n"
    "<b>Шаг 1: Скачайте Hiddify</b>\n"
    "• <a href='https://hiddify.com/'>Windows/Mac/Linux — Hiddify</a>\n"
    "• <a href='https://github.com/2dust/v2rayN/releases'>V2RayN (Windows)</a>\n\n"
    "<b>Шаг 2: Скопируйте VPN-ключ</b>\n"
    "Нажмите «🔑 Мой VPN-ключ» в боте. Скопируйте ключ.\n\n"
    "<b>Шаг 3: Импортируйте ключ</b>\n"
    "Откройте приложение → добавьте сервер из буфера обмена.\n\n"
    "<b>Шаг 4: Подключитесь</b>\n"
    "Выберите сервер и нажмите подключение. Готово!"
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
        HOWTO_CHOOSE_TEXT, reply_markup=howto_platforms_kb(), parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "howto_android")
async def howto_android(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        HOWTO_ANDROID, reply_markup=howto_back_kb(), parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data == "howto_ios")
async def howto_ios(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        HOWTO_IOS, reply_markup=howto_back_kb(), parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data == "howto_desktop")
async def howto_desktop(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        HOWTO_DESKTOP, reply_markup=howto_back_kb(), parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data == "howto_back")
async def howto_back(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        HOWTO_CHOOSE_TEXT, reply_markup=howto_platforms_kb(), parse_mode="HTML"
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
