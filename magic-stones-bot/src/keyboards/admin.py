"""
Клавиатуры для админ-панели.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура админки."""
    buttons = [
        [InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="admin_orders"),
         InlineKeyboardButton(text="💎 ТОВАРЫ", callback_data="admin_products")],
        [InlineKeyboardButton(text="📚 КОНТЕНТ", callback_data="admin_content"),
         InlineKeyboardButton(text="🎟️ ПРОМОКОДЫ", callback_data="admin_promos")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats"),
         InlineKeyboardButton(text="📢 РАССЫЛКИ", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📥 ЭКСПОРТ", callback_data="admin_export"),
         InlineKeyboardButton(text="⚙️ НАСТРОЙКИ", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🔮 КЛУБ", callback_data="admin_club"),
         InlineKeyboardButton(text="📅 ПЛАНИРОВЩИК", callback_data="admin_scheduler")],
        [InlineKeyboardButton(text="🌐 САЙТ", callback_data="admin_site"),
         InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)