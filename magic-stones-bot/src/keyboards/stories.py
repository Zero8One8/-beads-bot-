"""
Клавиатуры для историй.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_stories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для историй."""
    buttons = [
        [InlineKeyboardButton(text="✏️ НАПИСАТЬ ИСТОРИЮ", callback_data="story_create")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)