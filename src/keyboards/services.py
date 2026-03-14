from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_services_keyboard(services: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s['name']} — {s['price']}₽",
                callback_data=f"service_{s['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_dates_keyboard(dates: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    for d in dates:
        buttons.append([InlineKeyboardButton(text=d, callback_data=f"date_{d}")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_times_keyboard(times: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    for t in times:
        buttons.append([InlineKeyboardButton(text=t, callback_data=f"time_{t}")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_booking_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="booking_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)