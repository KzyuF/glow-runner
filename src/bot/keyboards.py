"""Inline keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services.payment import PLANS


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="🔑 Мой VPN-ключ", callback_data="my_key")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton(text="❓ Как подключиться", callback_data="howto")],
        ]
    )


def plans_kb() -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
        ]
    )


def renew_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
        ]
    )
