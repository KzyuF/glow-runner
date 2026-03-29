"""Admin dashboard — HTML panel served via aiohttp."""

import asyncio
import html
import logging
import re
from datetime import datetime, timedelta

from aiohttp import web
from sqlalchemy import func, select

from src.models.database import async_session
from src.models.user import User
from src.services.xui_client import xui_client
from src.utils.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "glow_admin"
COOKIE_MAX_AGE = 86400 * 7

# ── SSE log handler ───────────────────────────────────────────

_log_subscribers: list[asyncio.Queue] = []
_log_history: list[str] = []
_MAX_HISTORY = 100


class SSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        entry = self.format(record)
        _log_history.append(entry)
        if len(_log_history) > _MAX_HISTORY:
            _log_history.pop(0)
        for q in list(_log_subscribers):
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass


def install_log_handler() -> None:
    handler = SSELogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


# ── Auth helper ───────────────────────────────────────────────

def _check_auth(request: web.Request) -> bool:
    pw = request.query.get("password")
    if pw == settings.admin_panel_password:
        return True
    cookie = request.cookies.get(COOKIE_NAME)
    return cookie == settings.admin_panel_password


def _set_cookie(resp: web.Response) -> None:
    resp.set_cookie(COOKIE_NAME, settings.admin_panel_password, max_age=COOKIE_MAX_AGE, httponly=True)


def _unauth() -> web.Response:
    return web.Response(
        text=LOGIN_HTML,
        content_type="text/html",
        status=401,
    )


# ── Styles ────────────────────────────────────────────────────

STYLE = """
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:1200px;margin:0 auto;padding:20px}
h1{color:#58a6ff;margin-bottom:16px;font-size:24px}
h2{color:#58a6ff;margin:24px 0 12px;font-size:18px}
a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}
.nav{display:flex;gap:16px;margin-bottom:24px;padding:12px;background:#161b22;border-radius:8px}
.nav a{padding:6px 14px;border-radius:6px;background:#21262d;color:#c9d1d9}
.nav a:hover{background:#30363d;text-decoration:none}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center}
.card .num{font-size:28px;font-weight:700;color:#58a6ff}
.card .lbl{font-size:12px;color:#8b949e;margin-top:4px}
.search{margin-bottom:16px;display:flex;gap:8px}
.search input{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;color:#c9d1d9;flex:1}
.search button{background:#238636;border:none;border-radius:6px;padding:8px 16px;color:#fff;cursor:pointer}
table{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden}
th{background:#21262d;padding:10px 12px;text-align:left;cursor:pointer;user-select:none;font-weight:600;color:#8b949e;font-size:12px;text-transform:uppercase}
th:hover{color:#c9d1d9}
td{padding:8px 12px;border-top:1px solid #21262d}
tr:hover td{background:#1c2128}
.active{color:#3fb950}.expired{color:#f85149}.none{color:#8b949e}
.btn{display:inline-block;background:#238636;border:none;border-radius:6px;padding:6px 14px;color:#fff;cursor:pointer;font-size:13px;text-decoration:none}
.btn:hover{background:#2ea043;text-decoration:none}
.btn-sm{padding:4px 10px;font-size:12px}
#logs{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;font-family:'Fira Code',monospace;font-size:12px;height:600px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.log-ERROR{color:#f85149}.log-WARNING{color:#d29922}.log-INFO{color:#3fb950}.log-DEBUG{color:#8b949e}
.detail{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.detail dt{color:#8b949e;font-size:12px;margin-top:12px}.detail dd{font-size:15px;margin-top:2px}
.form-inline{display:flex;gap:8px;align-items:center;margin-top:16px}
.form-inline input{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#c9d1d9;width:80px}
.login-box{max-width:360px;margin:100px auto;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:32px;text-align:center}
.login-box h1{margin-bottom:20px}
.login-box input{width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;color:#c9d1d9;margin-bottom:12px}
.login-box button{width:100%}
</style>
"""

LOGIN_HTML = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GlowVPN Admin</title>{STYLE}</head>
<body><div class="login-box"><h1>GlowVPN Admin</h1>
<form method="get"><input name="password" type="password" placeholder="Пароль"><br>
<button class="btn" type="submit">Войти</button></form></div></body></html>"""

NAV = """<div class="nav"><a href="/admin/dashboard">Dashboard</a><a href="/admin/logs">Logs</a></div>"""


# ── Dashboard ─────────────────────────────────────────────────

async def handle_dashboard(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _unauth()

    search = request.query.get("q", "").strip()
    sort_col = request.query.get("sort", "created_at")
    sort_dir = request.query.get("dir", "desc")

    allowed_cols = {
        "telegram_id", "username", "marzban_username", "is_active",
        "subscription_end", "referral_count", "created_at",
    }
    if sort_col not in allowed_cols:
        sort_col = "created_at"

    async with async_session() as session:
        total = await session.scalar(select(func.count(User.id))) or 0
        active = await session.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0

        query = select(User)
        if search:
            query = query.where(
                User.username.ilike(f"%{search}%") | User.telegram_id.cast(type_=None).__eq__(int(search) if search.isdigit() else -1)
                if search.isdigit()
                else User.username.ilike(f"%{search}%")
            )

        col = getattr(User, sort_col, User.created_at)
        query = query.order_by(col.desc() if sort_dir == "desc" else col.asc())

        result = await session.execute(query)
        users = result.scalars().all()

        # Build referrer map
        all_ids = {u.telegram_id: u for u in users}

    now = datetime.utcnow()

    def _toggle_dir(c):
        return "asc" if sort_col == c and sort_dir == "desc" else "desc"

    def _sort_link(c, label):
        arrow = ""
        if sort_col == c:
            arrow = " ▲" if sort_dir == "asc" else " ▼"
        q = f"?sort={c}&dir={_toggle_dir(c)}"
        if search:
            q += f"&q={html.escape(search)}"
        return f'<a href="/admin/dashboard{q}" style="color:inherit;text-decoration:none">{label}{arrow}</a>'

    rows = []
    for u in users:
        if u.subscription_end and u.subscription_end > now:
            status = '<span class="active">Активна</span>'
        elif u.subscription_end:
            status = '<span class="expired">Истекла</span>'
        else:
            status = '<span class="none">Нет</span>'

        ref_by = ""
        if u.referred_by:
            ref_user = all_ids.get(u.referred_by)
            ref_by = f"@{ref_user.username}" if ref_user and ref_user.username else str(u.referred_by)

        sub_end = u.subscription_end.strftime("%d.%m.%Y %H:%M") if u.subscription_end else "—"
        created = u.created_at.strftime("%d.%m.%Y") if u.created_at else "—"

        rows.append(
            f"<tr>"
            f'<td><a href="/admin/user/{u.telegram_id}">{u.telegram_id}</a></td>'
            f"<td>{html.escape(u.username or '—')}</td>"
            f"<td>{html.escape(u.marzban_username or '—')}</td>"
            f"<td>{status}</td>"
            f"<td>{sub_end}</td>"
            f"<td>{html.escape(ref_by)}</td>"
            f"<td>{u.referral_count}</td>"
            f"<td><code>{u.referral_code}</code></td>"
            f"<td>{created}</td>"
            f"</tr>"
        )

    table_html = "".join(rows) if rows else "<tr><td colspan='9' style='text-align:center;padding:20px'>Нет пользователей</td></tr>"

    body = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GlowVPN Dashboard</title>{STYLE}</head><body><div class="wrap">
<h1>GlowVPN Admin</h1>{NAV}
<div class="cards">
<div class="card"><div class="num">{total}</div><div class="lbl">Всего пользователей</div></div>
<div class="card"><div class="num">{active}</div><div class="lbl">Активных подписок</div></div>
</div>
<div class="search"><form method="get" style="display:flex;gap:8px;width:100%">
<input name="q" placeholder="Поиск по username или telegram_id" value="{html.escape(search)}">
<button class="btn" type="submit">Найти</button></form></div>
<table><thead><tr>
<th>{_sort_link('telegram_id','Telegram ID')}</th>
<th>{_sort_link('username','Username')}</th>
<th>{_sort_link('marzban_username','VPN Username')}</th>
<th>{_sort_link('is_active','Статус')}</th>
<th>{_sort_link('subscription_end','Истекает')}</th>
<th>Приглашён от</th>
<th>{_sort_link('referral_count','Рефералы')}</th>
<th>Реф. код</th>
<th>{_sort_link('created_at','Регистрация')}</th>
</tr></thead><tbody>{table_html}</tbody></table>
</div></body></html>"""

    resp = web.Response(text=body, content_type="text/html")
    _set_cookie(resp)
    return resp


# ── User detail ───────────────────────────────────────────────

async def handle_user_detail(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _unauth()

    try:
        telegram_id = int(request.match_info["telegram_id"])
    except (ValueError, TypeError):
        return web.Response(text="Invalid telegram_id", status=400)

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return web.Response(text="User not found", status=404)

        # Referrer info
        referrer_name = "—"
        if user.referred_by:
            r = await session.execute(
                select(User).where(User.telegram_id == user.referred_by)
            )
            ref = r.scalar_one_or_none()
            if ref:
                referrer_name = f'<a href="/admin/user/{ref.telegram_id}">@{html.escape(ref.username or str(ref.telegram_id))}</a>'

        # Referrals by this user
        r2 = await session.execute(
            select(User).where(User.referred_by == user.telegram_id)
        )
        referrals = r2.scalars().all()

    now = datetime.utcnow()
    if user.subscription_end and user.subscription_end > now:
        status = '<span class="active">Активна</span>'
    elif user.subscription_end:
        status = '<span class="expired">Истекла</span>'
    else:
        status = '<span class="none">Нет</span>'

    sub_end = user.subscription_end.strftime("%d.%m.%Y %H:%M") if user.subscription_end else "—"
    created = user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "—"

    ref_rows = ""
    for ru in referrals:
        paid = "Да" if ru.referral_bonus_given else "Нет"
        ref_rows += (
            f'<tr><td><a href="/admin/user/{ru.telegram_id}">{ru.telegram_id}</a></td>'
            f'<td>{html.escape(ru.username or "—")}</td>'
            f'<td>{paid}</td></tr>'
        )
    ref_table = f"<table><thead><tr><th>Telegram ID</th><th>Username</th><th>Оплатил</th></tr></thead><tbody>{ref_rows}</tbody></table>" if ref_rows else "<p style='color:#8b949e'>Нет рефералов</p>"

    body = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>User {telegram_id}</title>{STYLE}</head><body><div class="wrap">
<h1>GlowVPN Admin</h1>{NAV}
<h2>Пользователь {telegram_id}</h2>
<div class="detail"><dl>
<dt>Telegram ID</dt><dd>{user.telegram_id}</dd>
<dt>Username</dt><dd>@{html.escape(user.username or '—')}</dd>
<dt>VPN Username</dt><dd>{html.escape(user.marzban_username or '—')}</dd>
<dt>Статус подписки</dt><dd>{status}</dd>
<dt>Подписка до</dt><dd>{sub_end}</dd>
<dt>Реферальный код</dt><dd><code>{user.referral_code}</code></dd>
<dt>Приглашён от</dt><dd>{referrer_name}</dd>
<dt>Бонус начислен</dt><dd>{'Да' if user.referral_bonus_given else 'Нет'}</dd>
<dt>Количество рефералов</dt><dd>{user.referral_count}</dd>
<dt>Дата регистрации</dt><dd>{created}</dd>
</dl>
<form class="form-inline" method="post" action="/admin/extend/{user.telegram_id}">
<label>Продлить на</label><input name="days" type="number" value="30" min="1">
<label>дней</label><button class="btn btn-sm" type="submit">Продлить</button>
</form>
</div>
<h2>Реферальная цепочка</h2>
{ref_table}
</div></body></html>"""

    resp = web.Response(text=body, content_type="text/html")
    _set_cookie(resp)
    return resp


# ── Extend subscription ──────────────────────────────────────

async def handle_extend(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _unauth()

    try:
        telegram_id = int(request.match_info["telegram_id"])
    except (ValueError, TypeError):
        return web.Response(text="Invalid telegram_id", status=400)
    data = await request.post()
    try:
        days = int(data.get("days", 30))
    except (ValueError, TypeError):
        days = 30

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return web.Response(text="User not found", status=404)

        now = datetime.utcnow()
        if user.subscription_end and user.subscription_end > now:
            user.subscription_end += timedelta(days=days)
        else:
            user.subscription_end = now + timedelta(days=days)
        user.is_active = True

        # Update 3X-UI
        if user.marzban_username:
            try:
                new_expire_ms = int(user.subscription_end.timestamp() * 1000)
                link = await xui_client.get_vless_link(user.marzban_username)
                m = re.match(r"^vless://([^@]+)@", link)
                if not m:
                    raise ValueError(f"Cannot parse vless link: {link[:60]}")
                client_uuid = m.group(1)
                await xui_client.update_client(
                    client_uuid=client_uuid,
                    email=user.marzban_username,
                    expire_timestamp_ms=new_expire_ms,
                )
            except Exception:
                logger.exception("Failed to extend user in 3X-UI")

        await session.commit()

    raise web.HTTPFound(f"/admin/user/{telegram_id}")


# ── Logs (SSE) ────────────────────────────────────────────────

async def handle_logs_page(request: web.Request) -> web.Response:
    if not _check_auth(request):
        return _unauth()

    body = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GlowVPN Logs</title>{STYLE}</head><body><div class="wrap">
<h1>GlowVPN Admin</h1>{NAV}
<h2>Логи (realtime)</h2>
<div id="logs"></div>
</div>
<script>
const el = document.getElementById('logs');
function colorize(line) {{
    let cls = 'log-DEBUG';
    if (line.includes('[ERROR]')) cls = 'log-ERROR';
    else if (line.includes('[WARNING]')) cls = 'log-WARNING';
    else if (line.includes('[INFO]')) cls = 'log-INFO';
    return '<span class="' + cls + '">' + line + '</span>';
}}
const es = new EventSource('/admin/logs/stream');
es.onmessage = function(e) {{
    el.innerHTML += colorize(e.data) + '\\n';
    el.scrollTop = el.scrollHeight;
}};
es.onerror = function() {{ setTimeout(() => location.reload(), 5000); }};
</script></body></html>"""

    resp = web.Response(text=body, content_type="text/html")
    _set_cookie(resp)
    return resp


async def handle_logs_stream(request: web.Request) -> web.StreamResponse:
    if not _check_auth(request):
        return _unauth()

    resp = web.StreamResponse()
    resp.content_type = "text/event-stream"
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    await resp.prepare(request)

    # Send history
    for line in _log_history:
        await resp.write(f"data: {line}\n\n".encode())

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    _log_subscribers.append(queue)
    try:
        while True:
            line = await queue.get()
            await resp.write(f"data: {line}\n\n".encode())
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        _log_subscribers.remove(queue)

    return resp


# ── Route registration ────────────────────────────────────────

def register_admin_routes(app: web.Application) -> None:
    install_log_handler()
    app.router.add_get("/admin/dashboard", handle_dashboard)
    app.router.add_get("/admin/logs", handle_logs_page)
    app.router.add_get("/admin/logs/stream", handle_logs_stream)
    app.router.add_get("/admin/user/{telegram_id}", handle_user_detail)
    app.router.add_post("/admin/extend/{telegram_id}", handle_extend)
