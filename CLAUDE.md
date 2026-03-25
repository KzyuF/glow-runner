# VPN Telegram Bot — Project Specification

## Overview
A Telegram bot that manages VPN subscriptions via the Marzban panel API.
Users interact with the bot to: register, buy a subscription, receive a VPN config link, check remaining traffic/time, and renew.

## Tech Stack
- **Language**: Python 3.11+
- **Bot Framework**: aiogram 3.x (async Telegram bot framework)
- **Database**: SQLite via aiosqlite + SQLAlchemy (async ORM)
- **VPN Panel**: Marzban (REST API)
- **Payment**: Telegram Stars (built-in Telegram payments, no external gateways needed)
- **Config**: pydantic-settings for environment variables
- **HTTP Client**: httpx (async)

## Architecture

```
src/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Bot entry point, dispatcher setup
│   ├── middlewares.py        # Auth middleware, rate limiting
│   └── keyboards.py         # Inline keyboards and reply keyboards
├── handlers/
│   ├── __init__.py
│   ├── start.py             # /start command, registration
│   ├── profile.py           # User profile, subscription status
│   ├── buy.py               # Subscription purchase flow
│   ├── keys.py              # Get/regenerate VPN keys
│   └── admin.py             # Admin commands (stats, broadcast)
├── services/
│   ├── __init__.py
│   ├── marzban.py           # Marzban API client (create/delete/get users)
│   ├── payment.py           # Telegram Stars payment processing
│   └── subscription.py      # Subscription logic (create, renew, expire)
├── models/
│   ├── __init__.py
│   ├── database.py          # SQLAlchemy engine and session setup
│   └── user.py              # User model (telegram_id, username, subscription_end, data_limit, marzban_username)
├── utils/
│   ├── __init__.py
│   ├── config.py            # Settings class (from .env)
│   └── helpers.py           # Formatting helpers (bytes to GB, date formatting)
config/
├── .env.example             # Template for environment variables
scripts/
├── setup_server.sh          # Server setup script (install Marzban, configure)
docs/
├── SETUP_GUIDE.md           # Step-by-step setup instructions for the user
```

## Database Schema

### users table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| telegram_id | BIGINT UNIQUE | Telegram user ID |
| username | TEXT | Telegram username |
| marzban_username | TEXT | Username in Marzban panel |
| subscription_end | DATETIME | When subscription expires |
| data_limit_gb | INTEGER | Traffic limit in GB |
| is_active | BOOLEAN | Whether subscription is active |
| created_at | DATETIME | Registration date |

## Marzban API Integration

Base URL: `{MARZBAN_ADDRESS}/api`

Key endpoints to use:
- `POST /admin/token` — get admin JWT token
- `POST /user` — create VPN user
- `GET /user/{username}` — get user info (traffic used, status)
- `PUT /user/{username}` — modify user (reset traffic, change expiry)
- `DELETE /user/{username}` — delete user
- `GET /user/{username}/subscription` — get subscription link

When creating a Marzban user:
```json
{
  "username": "tg_123456789",
  "proxies": {
    "vless": {"flow": "xtls-rprx-vision"}
  },
  "inbounds": {"vless": ["VLESS TCP REALITY"]},
  "expire": 1735689600,
  "data_limit": 32212254720,
  "data_limit_reset_strategy": "no_reset"
}
```

## Bot User Flow

### /start
1. Check if user exists in DB
2. If new → register, show welcome message with inline keyboard
3. If existing → show main menu

### Main Menu (inline keyboard)
- 🛒 Buy subscription
- 🔑 My VPN key
- 👤 Profile
- ❓ How to connect

### Buy Flow
1. User taps "Buy subscription"
2. Show plans: 1 month / 3 months / 6 months (with prices in Stars)
3. User picks a plan → send Telegram Stars invoice
4. On successful payment → create Marzban user → send subscription link
5. If user already has active sub → extend it

### My VPN Key
1. Fetch user from Marzban API
2. Show subscription link + QR code
3. Show traffic used / remaining
4. Button to copy link

### Profile
1. Show: username, subscription status, expiry date, traffic used
2. If expired → show "Renew" button

### How to Connect
Send instructions with links to apps:
- Android: V2RayNG or Hiddify
- iOS: Streisand or V2Box  
- Windows/Mac: Hiddify or Nekoray
- Include step-by-step: "1. Copy the link 2. Open app 3. Tap + 4. Paste"

### Admin Commands (only for ADMIN_TELEGRAM_ID)
- `/stats` — total users, active subs, revenue
- `/broadcast <message>` — send message to all users

## Subscription Plans
```python
PLANS = {
    "1month": {"days": 30, "data_gb": 50, "price_stars": 100, "label": "1 месяц (50 ГБ)"},
    "3months": {"days": 90, "data_gb": 150, "price_stars": 250, "label": "3 месяца (150 ГБ)"},
    "6months": {"days": 180, "data_gb": 300, "price_stars": 450, "label": "6 месяцев (300 ГБ)"},
}
```

## Payment via Telegram Stars
Use aiogram's built-in support for Telegram Payments with Stars:
- Create invoice with `LabeledPrice`
- Currency: "XTR" (Telegram Stars)
- Handle `pre_checkout_query` → always answer OK
- Handle `successful_payment` → activate subscription

## Environment Variables (.env)
```
BOT_TOKEN=your_telegram_bot_token
ADMIN_TELEGRAM_ID=your_telegram_id
MARZBAN_ADDRESS=https://your-domain.com:8000
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=admin_password
DATABASE_URL=sqlite+aiosqlite:///data/bot.db
```

## Error Handling
- All Marzban API calls wrapped in try/except with user-friendly error messages
- If Marzban is down → tell user "Service temporarily unavailable"
- Log errors to file and optionally notify admin via Telegram

## Important Implementation Notes
- All messages in Russian
- Use aiogram 3.x Router pattern (not the old Dispatcher.register)
- Use async/await everywhere
- Store Marzban admin token in memory, refresh on 401
- Generate marzban usernames as `tg_{telegram_id}` for easy mapping
- QR codes generated via `qrcode` library (PIL)
- Subscription link format: `{MARZBAN_ADDRESS}/sub/{marzban_username}/{token}`
