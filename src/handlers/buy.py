"""Subscription purchase flow — Telegram Stars and Platega."""

import logging
import time

import httpx
from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import (
    back_to_main_kb,
    payment_methods_kb,
    plans_kb,
)
from src.services.payment import PLANS
from src.services.subscription import activate_subscription, get_or_create_user
from src.utils.config import settings

router = Router()
logger = logging.getLogger(__name__)

SUPPORT_NOTE = "\n\nЕсли проблема не решится — обратитесь в поддержку через главное меню."

# Double-click protection: user_id -> last invoice timestamp
_invoice_cooldown: dict[int, float] = {}
COOLDOWN_SECONDS = 5.0


# ── Step 1: choose plan ───────────────────────────────────────

@router.callback_query(lambda c: c.data == "buy")
async def show_plans(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "🛒 Выберите тариф:", reply_markup=plans_kb()
    )


# ── Step 2: choose payment method ─────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("choose_plan:"))
async def show_payment_methods(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 1)
    plan_key = parts[1] if len(parts) > 1 else ""
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        f"🛒 Тариф: {plan['label']}\n\nВыберите способ оплаты:",
        reply_markup=payment_methods_kb(plan_key),
    )


# ── Stars flow ─────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("plan:"))
async def send_invoice(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":", 1)
    plan_key = parts[1] if len(parts) > 1 else ""
    logger.info(f"Plan selected: {plan_key}")
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    user_id = callback.from_user.id
    now = time.monotonic()
    if now - _invoice_cooldown.get(user_id, 0) < COOLDOWN_SECONDS:
        await callback.answer("Счёт уже отправлен, подождите.", show_alert=True)
        return
    _invoice_cooldown[user_id] = now

    await callback.answer()

    try:
        logger.info(f"Sending invoice to {user_id}, plan={plan_key}")
        await bot.send_invoice(
            chat_id=user_id,
            title="VPN-подписка",
            description=plan["label"],
            payload=plan_key,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=plan["label"], amount=plan["price_stars"])],
        )
        logger.info(f"Invoice sent successfully to {user_id}")
    except Exception as e:
        logger.error(f"Failed to send invoice: {e}")
        _invoice_cooldown.pop(user_id, None)


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(lambda m: m.successful_payment is not None)
async def on_successful_payment(message: Message, session: AsyncSession, bot: Bot) -> None:
    payment: SuccessfulPayment = message.successful_payment
    plan_key = payment.invoice_payload

    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )

    try:
        link = await activate_subscription(session, user, plan_key, bot=bot)
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
        try:
            await bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            logger.info(f"Refund issued to {message.from_user.id}")
        except Exception:
            logger.exception("Ошибка возврата оплаты")
        text = "❌ Произошла ошибка. Оплата возвращена. Попробуйте позже или обратитесь в поддержку через главное меню."

    await message.answer(text, reply_markup=back_to_main_kb(), parse_mode="HTML")


# ── Platega (card/SBP) flow ──────────────────────────────────

PLATEGA_API_URL = "https://app.platega.io/transaction/process"


@router.callback_query(lambda c: c.data and c.data.startswith("platega_method:"))
async def send_platega_link(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка", show_alert=True)
        return

    _, plan_key, method_str = parts
    plan = PLANS.get(plan_key)
    if not plan:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    try:
        payment_method = int(method_str)
    except (ValueError, TypeError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id
    now = time.monotonic()
    if now - _invoice_cooldown.get(user_id, 0) < COOLDOWN_SECONDS:
        await callback.answer("Счёт уже отправлен, подождите.", show_alert=True)
        return
    _invoice_cooldown[user_id] = now

    await callback.answer()

    amount = plan["price_rub"]
    payload_str = f"{user_id}:{plan_key}"

    body = {
        "paymentMethod": payment_method,
        "paymentDetails": {"amount": amount, "currency": "RUB"},
        "description": f"GlowVPN подписка {plan['label']}",
        "return": "https://glowbestvpn.site/payment/success",
        "failedUrl": "https://glowbestvpn.site/payment/fail",
        "payload": payload_str,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                PLATEGA_API_URL,
                json=body,
                headers={
                    "X-MerchantId": settings.platega_merchant_id,
                    "X-Secret": settings.platega_secret,
                },
            )
            data = resp.json()

        redirect_url = data.get("redirect")
        if not redirect_url:
            raise ValueError(f"No redirect in Platega response: {data}")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=redirect_url)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="buy")],
            ]
        )
        await callback.message.edit_text(
            f"💳 Оплата тарифа: {plan['label']}\n"
            f"Сумма: {amount} ₽\n\n"
            f"Нажмите кнопку ниже для перехода к оплате:",
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(f"Failed to create Platega transaction: {e}")
        _invoice_cooldown.pop(user_id, None)
        try:
            await callback.message.edit_text(
                "⚠️ Не удалось создать платёж. Попробуйте позже." + SUPPORT_NOTE,
                reply_markup=back_to_main_kb(),
            )
        except Exception:
            pass
