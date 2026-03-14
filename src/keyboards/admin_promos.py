from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_promos_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК ПРОМОКОДОВ", callback_data="admin_promos_list")],
        [InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_promo_create")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_promos_list_keyboard(promos: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for p in promos[:20]:
        discount = f"{p['discount_pct']}%" if p['discount_pct'] else f"{p['discount_rub']}₽"
        buttons.append([
            InlineKeyboardButton(
                text=f"{p['code']} — {discount}",
                callback_data=f"admin_promo_view_{p['code']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_promos")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)