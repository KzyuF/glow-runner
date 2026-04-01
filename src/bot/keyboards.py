"""Inline keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services.payment import PLANS


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="🔑 Мой VPN-ключ", callback_data="my_key")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton(text="📲 Как подключиться", callback_data="howto")],
            [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="referral")],
            [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")],
            [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info")],
        ]
    )


def payment_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="pay_stars")],
            [InlineKeyboardButton(text="💳 Картой/СБП", callback_data="pay_platega")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )


def plans_stars_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, plan in PLANS.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{plan['label']} — {plan['price_stars']} ⭐",
                    callback_data=f"plan:{key}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="buy")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plans_card_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, plan in PLANS.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{plan['label']} — {plan['price_rub']} ₽",
                    callback_data=f"fk_plan:{key}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="buy")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plans_platega_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, plan in PLANS.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{plan['label']} — {plan['price_rub']} ₽",
                    callback_data=f"platega_plan:{key}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="buy")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
        ]
    )


def info_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Пользовательское соглашение",
                url="https://telegra.ph/Polzovatelskoe-soglashenie-GlowVPN-03-27",
            )],
            [InlineKeyboardButton(
                text="Политика конфиденциальности",
                url="https://telegra.ph/Politika-konfidencialnosti-GlowVPN-03-27",
            )],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )


def howto_platforms_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Android", callback_data="howto_android")],
            [InlineKeyboardButton(text="🍎 iPhone/iPad", callback_data="howto_ios")],
            [InlineKeyboardButton(text="🪟 Windows", callback_data="howto_windows")],
            [InlineKeyboardButton(text="🍎 macOS", callback_data="howto_macos")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )


def howto_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к выбору платформы", callback_data="howto_back")],
        ]
    )


def renew_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
        ]
    )
