# VPN Telegram Bot

Telegram-бот для продажи VPN-подписок через Marzban-панель.

## Быстрый старт

1. Прочитай `docs/SETUP_GUIDE.md` — полная инструкция
2. Арендуй VPS и установи Marzban
3. Создай бота через @BotFather
4. Заполни `config/.env`
5. Запусти: `docker-compose up -d --build`

## Для разработки с Claude Code

```bash
claude
> Прочитай CLAUDE.md и реализуй весь проект
```

## Стек

- Python 3.11 + aiogram 3.x
- Marzban API (VLESS + Reality)
- Telegram Stars для оплаты
- SQLite + SQLAlchemy
- Docker для деплоя
