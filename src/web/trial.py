"""HTTP server for free trial VPN keys and Freekassa webhooks."""

import hashlib
import logging
import time

import aiosqlite
from aiohttp import web

from src.models.database import async_session
from src.services.payment import PLANS
from src.services.subscription import activate_subscription, get_or_create_user
from src.services.xui_client import xui_client
from src.utils.config import settings

logger = logging.getLogger(__name__)

DB_PATH = "data/trials.db"
TRIAL_HOURS = 6
COOLDOWN_SECONDS = 24 * 3600  # 24 hours

FREEKASSA_IPS = {
    "168.119.157.136",
    "168.119.60.227",
    "178.154.197.79",
    "51.250.54.238",
}


async def _init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS trials ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  ip TEXT NOT NULL,"
            "  email TEXT NOT NULL,"
            "  created_at INTEGER NOT NULL"
            ")"
        )
        await db.commit()


def _get_client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    peername = request.transport.get_extra_info("peername")
    if peername:
        return peername[0]
    return "unknown"


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=200)
    else:
        resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# ── Health ─────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


# ── Trial ──────────────────────────────────────────────────────

async def handle_trial(request: web.Request) -> web.Response:
    ip = _get_client_ip(request)
    now = int(time.time())
    cutoff = now - COOLDOWN_SECONDS

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM trials WHERE ip = ? AND created_at > ? LIMIT 1",
            (ip, cutoff),
        )
        row = await cursor.fetchone()
        if row:
            return web.json_response(
                {
                    "error": (
                        "Вы уже получали бесплатный ключ. "
                        "Попробуйте позже или купите подписку в нашем боте @glowvpnbot"
                    )
                },
                status=429,
            )

        email = f"trial_{now}"
        expire_ms = (now + TRIAL_HOURS * 3600) * 1000

        try:
            await xui_client.create_client(
                email=email,
                expire_timestamp_ms=expire_ms,
                limit_ip=1,
            )
            link = await xui_client.get_vless_link(email)
        except Exception:
            logger.exception("Failed to create trial client")
            return web.json_response(
                {"error": "Сервис временно недоступен. Попробуйте позже."},
                status=503,
            )

        await db.execute(
            "INSERT INTO trials (ip, email, created_at) VALUES (?, ?, ?)",
            (ip, email, now),
        )
        await db.commit()

    return web.json_response({"key": link, "expires_in": "6 часов"})


# ── Freekassa webhook ──────────────────────────────────────────

async def handle_freekassa(request: web.Request) -> web.Response:
    # Verify IP
    sender_ip = _get_client_ip(request)
    if sender_ip not in FREEKASSA_IPS:
        logger.warning(f"Freekassa webhook from unknown IP: {sender_ip}")
        return web.Response(text="DENIED", status=403)

    data = await request.post()

    merchant_id = data.get("MERCHANT_ID", "")
    amount = data.get("AMOUNT", "")
    order_id = data.get("MERCHANT_ORDER_ID", "")
    received_sign = data.get("SIGN", "")

    # Verify signature: md5(MERCHANT_ID:AMOUNT:SECRET2:MERCHANT_ORDER_ID)
    sign_str = f"{merchant_id}:{amount}:{settings.freekassa_secret2}:{order_id}"
    expected_sign = hashlib.md5(sign_str.encode()).hexdigest()

    if received_sign != expected_sign:
        logger.warning("Freekassa webhook: invalid signature")
        return web.Response(text="INVALID SIGN", status=400)

    telegram_id_str = data.get("us_telegram_id", "")
    plan_key = data.get("us_plan", "")

    if not telegram_id_str or not plan_key:
        logger.warning("Freekassa webhook: missing us_telegram_id or us_plan")
        return web.Response(text="MISSING PARAMS", status=400)

    if plan_key not in PLANS:
        logger.warning(f"Freekassa webhook: unknown plan {plan_key}")
        return web.Response(text="UNKNOWN PLAN", status=400)

    try:
        telegram_id = int(telegram_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Freekassa webhook: invalid telegram_id: {telegram_id_str}")
        return web.Response(text="INVALID TELEGRAM_ID", status=400)

    bot = request.app.get("bot")
    if bot is None:
        logger.error("Freekassa webhook: bot not available in app")
        return web.Response(text="BOT UNAVAILABLE", status=500)

    try:
        async with async_session() as session:
            user = await get_or_create_user(session, telegram_id, username=None)
            link = await activate_subscription(session, user, plan_key, bot=bot)

        plan = PLANS[plan_key]
        text = (
            f"✅ Оплата картой прошла успешно!\n\n"
            f"Тариф: {plan['label']}\n"
            f"Ваша ссылка для подключения:\n"
            f"<code>{link}</code>\n\n"
            f"Скопируйте ссылку и откройте в VPN-приложении."
        )
        await bot.send_message(telegram_id, text, parse_mode="HTML")
        logger.info(f"Freekassa payment processed: tg={telegram_id}, plan={plan_key}")
    except Exception:
        logger.exception(f"Freekassa webhook: activation failed for tg={telegram_id}")
        try:
            await bot.send_message(
                telegram_id,
                "❌ Оплата получена, но произошла ошибка активации. Обратитесь в поддержку через главное меню.",
            )
        except Exception:
            pass

    return web.Response(text="YES")


# ── App setup ──────────────────────────────────────────────────

def create_app(bot=None) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    if bot is not None:
        app["bot"] = bot
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/trial", handle_trial)
    app.router.add_post("/api/freekassa/notification", handle_freekassa)

    from src.web.admin import register_admin_routes
    register_admin_routes(app)

    return app


async def run_trial_server(bot=None) -> None:
    await _init_db()
    app = create_app(bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8888)
    await site.start()
    logger.info("HTTP server started on port 8888")
