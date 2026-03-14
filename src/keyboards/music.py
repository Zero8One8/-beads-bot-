"""
Клавиатуры для музыкальной библиотеки.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict


def get_music_keyboard(tracks: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком музыкальных треков."""
    buttons = []
    for track in tracks[:10]:  # Показываем первые 10 треков
        buttons.append([
            InlineKeyboardButton(
                text=f"🎵 {track['name']}",
                callback_data=f"music_{track['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)