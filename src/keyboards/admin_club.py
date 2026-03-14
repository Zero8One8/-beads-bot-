"""
Клавиатуры для управления клубом.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_admin_club_keyboard() -> InlineKeyboardMarkup:
    """Главное меню управления клубом."""
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК ПОДПИСЧИКОВ", callback_data="admin_club_list")],
        [InlineKeyboardButton(text="📝 РЕДАКТИРОВАТЬ ОПИСАНИЕ", callback_data="admin_club_edit_info")],
        [InlineKeyboardButton(text="📚 УПРАВЛЕНИЕ КОНТЕНТОМ", callback_data="admin_club_content")],
        [InlineKeyboardButton(text="➕ ПРОДЛИТЬ ПОДПИСКУ", callback_data="admin_club_extend")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscribers_list_keyboard(subs: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком подписчиков."""
    buttons = []
    for s in subs:
        name = s['first_name'] or s['username'] or str(s['user_id'])
        status_emoji = {
            'active': '✅',
            'trial': '🆓',
            'expired': '⌛'
        }.get(s['status'], '❓')
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {name}",
                callback_data=f"admin_club_user_{s['user_id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)