"""
Клавиатуры для статистики.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_stats_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню статистики."""
    buttons = [
        [InlineKeyboardButton(text="👥 ПОЛЬЗОВАТЕЛИ", callback_data="stats_users"),
         InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="stats_orders")],
        [InlineKeyboardButton(text="💎 ПОПУЛЯРНЫЕ ТОВАРЫ", callback_data="stats_products"),
         InlineKeyboardButton(text="🔮 ПОПУЛЯРНЫЕ КАМНИ", callback_data="stats_stones")],
        [InlineKeyboardButton(text="📊 ВОРОНКА ПРОДАЖ", callback_data="stats_funnel"),
         InlineKeyboardButton(text="💰 БОНУСЫ", callback_data="stats_cashback")],
        [InlineKeyboardButton(text="📈 ПРОГНОЗЫ", callback_data="stats_forecast")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_funnel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для воронки."""
    buttons = [
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_funnel")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)