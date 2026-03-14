"""
Клавиатуры для экспорта.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_export_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура экспорта."""
    buttons = [
        [InlineKeyboardButton(text="📦 Заказы", callback_data="export_orders")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="export_users")],
        [InlineKeyboardButton(text="💎 Товары", callback_data="export_products")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)