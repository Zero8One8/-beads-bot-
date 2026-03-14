"""
Клавиатуры для диагностики.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_diagnostic_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для диагностики."""
    buttons = [
        [InlineKeyboardButton(text="💳 Оплатить 3000⭐", callback_data="diagnostic_pay")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_diagnostic_admin_keyboard(diag_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для админа при просмотре диагностики."""
    buttons = [
        [InlineKeyboardButton(text="📝 Ввести результат", callback_data=f"diag_result_{diag_id}")],
        [InlineKeyboardButton(text="✨ Назначить услугу", callback_data=f"diag_service_{diag_id}")],
        [InlineKeyboardButton(text="✍️ Написать клиенту", callback_data=f"diag_contact_{diag_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_diagnostics")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)