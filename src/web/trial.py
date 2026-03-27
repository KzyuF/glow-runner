"""HTTP server for free trial VPN keys."""

import logging
import time

import aiosqlite
from aiohttp import web

from src.services.xui_client import xui_client

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
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


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


def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/trial", handle_trial)
    return app


async def run_trial_server() -> None:
    await _init_db()
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8888)
    await site.start()
    logger.info("Trial HTTP server started on port 8888")
