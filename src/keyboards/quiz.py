from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

def get_quiz_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"quiz_ans_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_totem_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_ans_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quiz_result_keyboard(stone: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💎 Посмотреть браслеты", callback_data=f"stone_products_{stone}")],
        [InlineKeyboardButton(text="🔄 Пройти ещё раз", callback_data="quiz")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)