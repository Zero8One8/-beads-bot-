from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_club_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно (24ч)", callback_data="club_trial")],
        [InlineKeyboardButton(text="📅 Месяц — 1990⭐", callback_data="club_buy_month")],
        [InlineKeyboardButton(text="🌟 Год — 19900⭐", callback_data="club_buy_year")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_club_content_list_keyboard(items: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton(
                text=item['title'],
                callback_data=f"club_item_{item['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="club")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_club_content_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="← К списку", callback_data="club_back")],
        [InlineKeyboardButton(text="← В меню клуба", callback_data="club")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)