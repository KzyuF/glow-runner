"""Subscription purchase flow with Telegram Stars."""

import logging

from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import back_to_main_kb, plans_kb
from src.services.payment import PLANS
from src.services.subscription import activate_subscription, get_or_create_user

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data == "buy")
async def show_plans(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🛒 Выберите тариф:", reply_markup=plans_kb()
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("plan:"))
async def send_invoice(callback: CallbackQuery, bot: Bot) -> None:
    plan_key = callback.data.split(":")[1]
    logger.info(f"Plan selected: {plan_key}")
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="VPN-подписка",
            description=plan["label"],
            payload=plan_key,
            currency="XTR",
            prices=[LabeledPrice(label=plan["label"], amount=plan["price_stars"])],
        )
    except Exception as e:
        logger.error(f"Failed to send invoice: {e}")
        await callback.answer("Ошибка создания счёта. Попробуйте позже.", show_alert=True)
        return
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def on_successful_payment(message: Message, session: AsyncSession) -> None:
    payment: SuccessfulPayment = message.successful_payment
    plan_key = payment.invoice_payload

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )

    try:
        link = await activate_subscription(session, user, plan_key)
        plan = PLANS[plan_key]
        text = (
            f"✅ Оплата прошла успешно!\n\n"
            f"Тариф: {plan['label']}\n"
            f"Ваша ссылка для подключения:\n"
            f"<code>{link}</code>\n\n"
            f"Скопируйте ссылку и откройте в VPN-приложении."
        )
    except Exception:
        logger.exception("Ошибка активации подписки")
        text = "❌ Оплата получена, но произошла ошибка активации. Обратитесь к администратору."

    await message.answer(text, reply_markup=back_to_main_kb(), parse_mode="HTML")
