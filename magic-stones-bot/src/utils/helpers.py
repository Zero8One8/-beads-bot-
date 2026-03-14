"""
Вспомогательные функции.
"""
import re
import json
from typing import List, Optional
from datetime import datetime


def format_price(price: float) -> str:
    """Форматирует цену: 1234 -> 1 234₽"""
    if not price:
        return "0₽"
    return f"{price:,.0f}".replace(",", " ") + "₽"


def format_number(num: int) -> str:
    """Форматирует число: 1234 -> 1 234"""
    return f"{num:,}".replace(",", " ")


def format_datetime(dt_str: Optional[str]) -> str:
    """Форматирует дату из БД в читаемый вид."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace(" ", "T"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return dt_str[:16]


def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы Markdown."""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def split_long_message(text: str, max_length: int = 3500) -> List[str]:
    """Разбивает длинное сообщение на части."""
    parts = []
    while len(text) > max_length:
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = max_length
        parts.append(text[:split_at])
        text = text[split_at:].strip()
    parts.append(text)
    return parts


def safe_json_parse(json_str: str, default=None):
    """Безопасный парсинг JSON."""
    if json_str is None:
        return default if default is not None else []
    try:
        if isinstance(json_str, str):
            return json.loads(json_str)
        return json_str
    except:
        return default if default is not None else []