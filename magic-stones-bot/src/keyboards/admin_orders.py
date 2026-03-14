"""
Клавиатуры для управления заказами.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional

from src.services.order_manager import OrderManager
from src.utils.helpers import format_price

def get_orders_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню заказов."""
    buttons = [
        [InlineKeyboardButton(text="📋 ВСЕ ЗАКАЗЫ", callback_data="orders_list_all")],
        [InlineKeyboardButton(text="⏳ ОЖИДАЮТ ОПЛАТЫ", callback_data="orders_status_pending")],
        [InlineKeyboardButton(text="✅ ОПЛАЧЕНЫ", callback_data="orders_status_paid")],
        [InlineKeyboardButton(text="🚚 ОТПРАВЛЕНЫ", callback_data="orders_status_shipped")],
        [InlineKeyboardButton(text="📦 ДОСТАВЛЕНЫ", callback_data="orders_status_delivered")],
        [InlineKeyboardButton(text="❌ ОТМЕНЕНЫ", callback_data="orders_status_cancelled")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_orders_list_keyboard(orders: List[Dict], status_filter: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура со списком заказов."""
    buttons = []
    
    for o in orders:
        status_emoji = {
            'pending': '⏳',
            'paid': '✅',
            'processing': '🔨',
            'shipped': '🚚',
            'delivered': '📦',
            'cancelled': '❌'
        }.get(o['status'], '📦')
        
        date = o['created_at'][:10] if o['created_at'] else ''
        name = o['first_name'] or f"ID{o['user_id']}"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_emoji} #{o['id']} | {name} | {format_price(o['total_price'])} | {date}",
                callback_data=f"order_view_{o['id']}"
            )
        ])
    
    back_data = f"orders_status_{status_filter}" if status_filter else "admin_orders"
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data=back_data)])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_order_detail_keyboard(order_id: int, current_status: str) -> InlineKeyboardMarkup:
    """Клавиатура для деталей заказа."""
    buttons = [
        [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ СТАТУС", callback_data=f"order_change_status_{order_id}")],
        [InlineKeyboardButton(text="📞 НАПИСАТЬ КЛИЕНТУ", callback_data=f"contact_user_{order_id}")],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="orders_list_all")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_status_change_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора статуса."""
    buttons = []
    
    for status, label in OrderManager.STATUSES.items():
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"order_set_status_{order_id}_{status}")
        ])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"order_view_{order_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)