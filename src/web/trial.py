"""HTTP server for free trial VPN keys and Platega callbacks."""

import logging
import time
import uuid as uuid_mod

import aiosqlite
import httpx
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


# ── Web payment (Platega) ─────────────────────────────────────

PLATEGA_API_URL = "https://app.platega.io/transaction/process"


async def handle_pay(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    plan_key = data.get("plan", "")
    method = data.get("method")

    plan = PLANS.get(plan_key)
    if not plan:
        return web.json_response({"error": "Неизвестный тариф"}, status=400)

    if method is None:
        return web.json_response({"error": "Не указан способ оплаты"}, status=400)

    try:
        payment_method = int(method)
    except (ValueError, TypeError):
        return web.json_response({"error": "Некорректный способ оплаты"}, status=400)

    transaction_id = uuid_mod.uuid4().hex[:16]
    amount = plan["price_rub"]

    body = {
        "paymentMethod": payment_method,
        "paymentDetails": {"amount": amount, "currency": "RUB"},
        "description": f"GlowVPN подписка {plan['label']}",
        "return": "https://glowbestvpn.site/payment/success",
        "failedUrl": "https://glowbestvpn.site/payment/fail",
        "payload": f"web:{transaction_id}",
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
            result = resp.json()

        redirect_url = result.get("redirect")
        if not redirect_url:
            logger.error(f"Platega /api/pay: no redirect in response: {result}")
            return web.json_response(
                {"error": "Не удалось создать платёж. Попробуйте позже."},
                status=502,
            )

        return web.json_response({"redirect": redirect_url})
    except Exception:
        logger.exception("Failed to create Platega transaction from web")
        return web.json_response(
            {"error": "Сервис оплаты временно недоступен."},
            status=503,
        )


# ── Platega callback ──────────────────────────────────────────

async def handle_platega(request: web.Request) -> web.Response:
    # Verify merchant credentials from headers
    merchant_id = request.headers.get("X-MerchantId", "")
    secret = request.headers.get("X-Secret", "")

    if merchant_id != settings.platega_merchant_id or secret != settings.platega_secret:
        logger.warning("Platega callback: invalid credentials")
        return web.Response(text="DENIED", status=403)

    try:
        data = await request.json()
    except Exception:
        return web.Response(text="INVALID JSON", status=400)

    status = data.get("status", "")
    payload = data.get("payload", "")
    transaction_id = data.get("id", "")

    logger.info(f"Platega callback: id={transaction_id}, status={status}, payload={payload}")

    if status != "CONFIRMED":
        return web.Response(text="OK", status=200)

    # Parse payload: "telegram_id:plan_key"
    parts = payload.split(":", 1)
    if len(parts) != 2:
        logger.warning(f"Platega callback: invalid payload format: {payload}")
        return web.Response(text="INVALID PAYLOAD", status=400)

    telegram_id_str, plan_key = parts

    try:
        telegram_id = int(telegram_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Platega callback: invalid telegram_id: {telegram_id_str}")
        return web.Response(text="INVALID TELEGRAM_ID", status=400)

    if plan_key not in PLANS:
        logger.warning(f"Platega callback: unknown plan {plan_key}")
        return web.Response(text="UNKNOWN PLAN", status=400)

    bot = request.app.get("bot")
    if bot is None:
        logger.error("Platega callback: bot not available in app")
        return web.Response(text="BOT UNAVAILABLE", status=500)

    try:
        async with async_session() as session:
            user = await get_or_create_user(session, telegram_id, username=None)
            await activate_subscription(session, user, plan_key, bot=bot)

        await bot.send_message(
            telegram_id,
            "✅ Оплата прошла! Ваша подписка активирована.\n"
            "Нажмите «🔑 Мой VPN-ключ» чтобы получить ключ.",
        )
        logger.info(f"Platega payment processed: tg={telegram_id}, plan={plan_key}")
    except Exception:
        logger.exception(f"Platega callback: activation failed for tg={telegram_id}")
        try:
            await bot.send_message(
                telegram_id,
                "❌ Оплата получена, но произошла ошибка активации. "
                "Обратитесь в поддержку через главное меню.",
            )
        except Exception:
            pass

    return web.Response(text="OK", status=200)


# ── App setup ──────────────────────────────────────────────────

def create_app(bot=None) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    if bot is not None:
        app["bot"] = bot
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/trial", handle_trial)
    app.router.add_post("/api/pay", handle_pay)
    app.router.add_post("/api/platega/callback", handle_platega)

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
