from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_products_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [InlineKeyboardButton(text="💎 БРАСЛЕТЫ", callback_data="admin_bracelets")],
        [InlineKeyboardButton(text="🖼️ КОЛЛЕКЦИИ ВИТРИНЫ", callback_data="admin_collections")],
        [InlineKeyboardButton(text="📦 ТОВАРЫ ВИТРИНЫ", callback_data="admin_showcase")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_categories_keyboard(categories: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(
                text=f"{cat['emoji']} {cat['name']}",
                callback_data=f"admin_cat_edit_{cat['id']}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_cat_create"),
        InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_products")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)