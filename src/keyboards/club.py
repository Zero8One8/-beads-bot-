"""
Клавиатуры для закрытого клуба.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict


def get_club_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню клуба (для неподписанных)."""
    buttons = [
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно (24ч)", callback_data="club_trial")],
        [InlineKeyboardButton(text="📅 Месяц — 1990⭐", callback_data="club_buy_month")],
        [InlineKeyboardButton(text="🌟 Год — 19900⭐ (скидка 17%)", callback_data="club_buy_year")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_club_content_list_keyboard(items: List[Dict]) -> InlineKeyboardMarkup:
    """Список доступных материалов клуба."""
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
    """Клавиатура под материалом."""
    buttons = [
        [InlineKeyboardButton(text="← К списку", callback_data="club_back")],
        [InlineKeyboardButton(text="← В меню клуба", callback_data="club")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_club_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для админ-панели клуба."""
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК ПОДПИСЧИКОВ", callback_data="admin_club_list")],
        [InlineKeyboardButton(text="📝 РЕДАКТИРОВАТЬ ОПИСАНИЕ", callback_data="admin_club_edit_info")],
        [InlineKeyboardButton(text="📚 УПРАВЛЕНИЕ КОНТЕНТОМ", callback_data="admin_club_content")],
        [InlineKeyboardButton(text="➕ ПРОДЛИТЬ ПОДПИСКУ", callback_data="admin_club_extend")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)  
