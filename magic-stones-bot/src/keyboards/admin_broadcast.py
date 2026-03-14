"""
Клавиатуры для управления рассылками.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_broadcast_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню рассылок."""
    buttons = [
        [InlineKeyboardButton(text="📝 СОЗДАТЬ РАССЫЛКУ", callback_data="broadcast_create")],
        [InlineKeyboardButton(text="📊 ИСТОРИЯ РАССЫЛОК", callback_data="broadcast_history")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_audience_keyboard() -> InlineKeyboardMarkup:
    """Выбор аудитории для рассылки."""
    buttons = [
        [InlineKeyboardButton(text="👥 ВСЕ ПОЛЬЗОВАТЕЛИ", callback_data="audience_all")],
        [InlineKeyboardButton(text="🔥 АКТИВНЫЕ (30 дней)", callback_data="audience_active")],
        [InlineKeyboardButton(text="🔔 ПОДПИСАННЫЕ НА НОВИНКИ", callback_data="audience_subscribers")],
        [InlineKeyboardButton(text="💰 КУПИВШИЕ ХОТЯ БЫ РАЗ", callback_data="audience_buyers")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение отправки."""
    buttons = [
        [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ ОТМЕНИТЬ", callback_data="broadcast_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)