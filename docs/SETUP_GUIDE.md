# Полное руководство по запуску VPN-бота

## Что тебе нужно сделать ПЕРЕД вайбкодингом

### 1. Арендовать VPS-сервер (10 минут)

Тебе нужен сервер за границей. Рекомендации:

| Хостинг | Цена | Где |
|---------|------|-----|
| Hetzner | от 4€/мес | Германия, Финляндия |
| Aéza | от 3€/мес | Нидерланды, Швеция |
| BuyVM | от $3.50/мес | Люксембург, США |

**Минимум**: 1 vCPU, 1 ГБ RAM, 20 ГБ SSD, Ubuntu 22.04 или 24.04

После покупки у тебя будет: **IP-адрес**, **логин** (обычно root), **пароль** или SSH-ключ.

### 2. Установить Marzban на сервер (15 минут)

Подключись к серверу:
```bash
ssh root@YOUR_SERVER_IP
```

Запусти скрипт установки (или используй наш `scripts/setup_server.sh`):
```bash
sudo bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install
```

Задай логин/пароль в `/opt/marzban/.env`:
```
SUDO_USERNAME=admin
SUDO_PASSWORD=твой_надежный_пароль
```

Перезапусти:
```bash
marzban restart
```

### 3. Настроить Marzban-панель (10 минут)

Зайди в панель через SSH-туннель:
```bash
ssh -L 8000:localhost:8000 root@YOUR_SERVER_IP
```
Открой в браузере: `http://localhost:8000/dashboard`

В панели:
1. Перейди в **Inbounds** (или **Настройки Xray**)
2. Добавь inbound: **VLESS + TCP + Reality**
3. В настройках Reality укажи `dest: google.com:443` и `serverNames: ["google.com"]`
4. Сохрани

### 4. Создать Telegram-бота (5 минут)

1. Открой @BotFather в Telegram
2. Отправь `/newbot`
3. Придумай имя и юзернейм
4. Скопируй **токен бота**

### 5. Узнать свой Telegram ID (2 минуты)

Открой @userinfobot в Telegram — он покажет твой числовой ID.

### 6. Заполнить config/.env

```bash
cp config/.env.example config/.env
```

Заполни:
```
BOT_TOKEN=токен_от_botfather
ADMIN_TELEGRAM_ID=твой_числовой_id
MARZBAN_ADDRESS=http://YOUR_SERVER_IP:8000
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=твой_пароль_marzban
```

---

## Как использовать с Claude Code (вайбкодинг)

### Вариант A — Локально на своём компьютере

1. Установи Python 3.11+ и Claude Code
2. Склонируй/скопируй этот проект в папку
3. Открой терминал в папке проекта
4. Запусти Claude Code:
   ```bash
   claude
   ```
5. Скажи Claude Code:
   ```
   Прочитай CLAUDE.md и реализуй весь проект. Начни с models/database.py и models/user.py,
   потом services/marzban.py, затем handlers и bot/main.py. Все сообщения на русском языке.
   ```

### Вариант B — Деплой через Docker

После того как Claude Code напишет весь код:
```bash
# На своём компе или на сервере
docker-compose up -d --build
```

### Вариант C — Запуск напрямую на сервере

```bash
pip install -r requirements.txt
python -m src.bot.main
```

---

## Как подключаться к VPN (для тебя и пользователей)

1. Бот выдаст ссылку вида `vless://...`
2. Скачай приложение:
   - **Android**: V2RayNG (Google Play) или Hiddify
   - **iOS**: Streisand (App Store) или V2Box
   - **Windows/Mac**: Hiddify Desktop или Nekoray
3. В приложении нажми **+** → **Вставить из буфера**
4. Подключись — готово!

---

## Структура проекта для Claude Code

```
vpn-telegram-bot/
├── CLAUDE.md              ← Главный файл! Claude Code читает его первым
├── requirements.txt       ← Зависимости Python
├── Dockerfile             ← Для деплоя
├── docker-compose.yml     ← Для деплоя
├── .gitignore
├── config/
│   └── .env.example       ← Шаблон переменных
├── scripts/
│   └── setup_server.sh    ← Скрипт установки сервера
├── docs/
│   └── SETUP_GUIDE.md     ← Это руководство
└── src/
    ├── bot/
    │   ├── main.py         ← Точка входа
    │   ├── keyboards.py    ← Клавиатуры бота
    │   └── middlewares.py   ← Мидлвари
    ├── handlers/
    │   ├── start.py        ← /start и регистрация
    │   ├── profile.py      ← Профиль пользователя
    │   ├── buy.py          ← Покупка подписки
    │   ├── keys.py         ← Выдача VPN-ключа
    │   └── admin.py        ← Админские команды
    ├── services/
    │   ├── marzban.py      ← API-клиент Marzban
    │   ├── payment.py      ← Оплата через Stars
    │   └── subscription.py ← Логика подписок
    ├── models/
    │   ├── database.py     ← Настройка БД
    │   └── user.py         ← Модель пользователя
    └── utils/
        ├── config.py       ← Настройки из .env
        └── helpers.py      ← Вспомогательные функции
```

## Примерные затраты

| Что | Стоимость |
|-----|-----------|
| VPS-сервер | 3-5€/мес |
| Домен (опционально) | 5-10€/год |
| Telegram-бот | Бесплатно |
| Marzban | Бесплатно (open source) |
| **Итого** | **~4€/мес** |
