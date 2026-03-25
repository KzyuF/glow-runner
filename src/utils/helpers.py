"""Formatting helpers."""

from datetime import datetime


def bytes_to_gb(b: int | None) -> str:
    if b is None:
        return "0.00"
    return f"{b / (1024 ** 3):.2f}"


def format_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def format_expiry_status(subscription_end: datetime | None) -> str:
    if subscription_end is None:
        return "Нет подписки"
    now = datetime.utcnow()
    if subscription_end < now:
        return "Истекла"
    delta = subscription_end - now
    days = delta.days
    if days > 0:
        return f"Осталось {days} дн."
    hours = delta.seconds // 3600
    return f"Осталось {hours} ч."
