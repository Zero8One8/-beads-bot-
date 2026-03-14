"""
Клавиатуры для услуг.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

from src.utils.helpers import format_price


def get_services_keyboard(services: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком услуг."""
    buttons = []
    for s in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s['name']} — {format_price(s['price'])}",
                callback_data=f"service_{s['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_service_detail_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для детальной страницы услуги."""
    buttons = [
        [InlineKeyboardButton(text="📅 ЗАПИСАТЬСЯ", callback_data=f"service_book_{service_id}")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="services")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_dates_keyboard(dates: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора даты."""
    buttons = []
    for d in dates:
        buttons.append([InlineKeyboardButton(text=d, callback_data=f"date_{d}")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_times_keyboard(times: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени."""
    buttons = []
    for t in times:
        buttons.append([InlineKeyboardButton(text=t, callback_data=f"time_{t}")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_booking_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения записи."""
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="booking_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
