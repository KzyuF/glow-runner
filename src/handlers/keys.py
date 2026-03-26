"""VPN key handler — show subscription link, QR code, traffic."""

import io
import logging

from aiogram import Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

import qrcode

from src.bot.keyboards import back_to_main_kb
from src.services.marzban import marzban_client
from src.services.subscription import get_or_create_user
from src.utils.helpers import bytes_to_gb

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data == "my_key")
async def show_key(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )

    if not user.marzban_username:
        await callback.message.edit_text(
            "У вас пока нет активной подписки. Купите подписку, чтобы получить ключ.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    try:
        link = await marzban_client.get_vless_link(user.marzban_username)
        usage = await marzban_client.get_user_usage(user.marzban_username)
    except Exception:
        logger.exception("Ошибка получения данных из Marzban")
        await callback.message.edit_text(
            "⚠️ Сервис временно недоступен. Попробуйте позже.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    used = bytes_to_gb(usage["used_traffic"])

    text = (
        f"🔑 <b>Ваш VPN-ключ</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"Использовано трафика: {used} ГБ\n\n"
        f"Скопируйте ссылку или отсканируйте QR-код ниже."
    )

    # Generate QR code
    img = qrcode.make(link)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await callback.message.delete()
    await callback.message.answer_photo(
        photo=BufferedInputFile(buf.read(), filename="vpn_qr.png"),
        caption=text,
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
