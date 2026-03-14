"""
Клавиатуры для планировщика постов.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

def get_scheduler_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню планировщика."""
    buttons = [
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ ПОСТ", callback_data="scheduler_add")],
        [InlineKeyboardButton(text="📋 СПИСОК ЗАПЛАНИРОВАННЫХ", callback_data="scheduler_list")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_posts_list_keyboard(posts: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура со списком доступных постов."""
    buttons = []
    for p in posts[:20]:
        buttons.append([InlineKeyboardButton(text=p, callback_data=f"scheduler_post_{p}")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_scheduler")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)