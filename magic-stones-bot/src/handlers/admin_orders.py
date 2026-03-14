"""
Админ-панель: управление заказами.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel, OrderModel
from src.utils.helpers import format_price, format_datetime

logger = logging.getLogger(__name__)
router = Router()


class AdminOrderStates(StatesGroup):
    waiting_status = State()
    waiting_tracking = State()


# Статусы заказов для отображения
STATUSES = {
    'pending': '⏳ Ожидает оплаты',
    'paid': '✅ Оплачен',
    'processing': '🔨 В обработке',
    'shipped': '🚚 Отправлен',
    'delivered': '📦 Доставлен',
    'cancelled': '❌ Отменён'
}


@router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    """Главное меню заказов."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    stats = OrderModel.get_stats_by_status()
    
    text = "📦 *УПРАВЛЕНИЕ ЗАКАЗАМИ*\n\n📊 *Статусы:*\n"
    for status, count in stats.items():
        text += f"{STATUSES.get(status, status)}: {count}\n"
    
    buttons = [
        [InlineKeyboardButton(text="📋 ВСЕ ЗАКАЗЫ", callback_data="orders_list_all")],
        [InlineKeyboardButton(text="⏳ ОЖИДАЮТ ОПЛАТЫ", callback_data="orders_status_pending")],
        [InlineKeyboardButton(text="✅ ОПЛАЧЕНЫ", callback_data="orders_status_paid")],
        [InlineKeyboardButton(text="🔨 В ОБРАБОТКЕ", callback_data="orders_status_processing")],
        [InlineKeyboardButton(text="🚚 ОТПРАВЛЕНЫ", callback_data="orders_status_shipped")],
        [InlineKeyboardButton(text="📦 ДОСТАВЛЕНЫ", callback_data="orders_status_delivered")],
        [InlineKeyboardButton(text="❌ ОТМЕНЕНЫ", callback_data="orders_status_cancelled")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "orders_list_all")
async def orders_list_all(callback: CallbackQuery):
    """Список всех заказов."""
    orders = OrderModel.get_all(limit=20)
    await show_orders_list(callback, orders, "ПОСЛЕДНИЕ 20 ЗАКАЗОВ")


@router.callback_query(F.data.startswith("orders_status_"))
async def orders_by_status(callback: CallbackQuery):
    """Список заказов по статусу."""
    status = callback.data.replace("orders_status_", "")
    orders = OrderModel.get_all(limit=20, status=status)
    status_name = STATUSES.get(status, status)
    await show_orders_list(callback, orders, f"ЗАКАЗЫ СО СТАТУСОМ: {status_name}", status_filter=status)


async def show_orders_list(callback: CallbackQuery, orders: list, title: str, status_filter: str = None):
    """Отображение списка заказов."""
    if not orders:
        await callback.message.edit_text(
            f"📭 {title}\n\nНет заказов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_orders")]
            ])
        )
        await callback.answer()
        return
    
    text = f"📦 *{title}*\n\n"
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
        
        text += f"{status_emoji} #{o['id']} | {name} | {format_price(o['total_price'])} | {date}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📋 Заказ #{o['id']}",
            callback_data=f"order_view_{o['id']}"
        )])
    
    back_data = f"orders_status_{status_filter}" if status_filter else "admin_orders"
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data=back_data)])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("order_view_"))
async def order_view(callback: CallbackQuery):
    """Просмотр деталей заказа."""
    order_id = int(callback.data.replace("order_view_", ""))
    order = OrderModel.get_by_id(order_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    items = OrderModel.get_items(order_id)
    
    text = (
        f"📦 *ЗАКАЗ #{order_id}*\n\n"
        f"👤 *Клиент:* {order['first_name'] or 'Не указано'} (@{order['username'] or 'нет'})\n"
        f"🆔 *ID:* {order['user_id']}\n"
        f"📅 *Дата:* {format_datetime(order['created_at'])}\n"
        f"💰 *Сумма:* {format_price(order['total_price'])}\n"
        f"💳 *Метод оплаты:* {order['payment_method'] or 'не указан'}\n"
        f"🎟️ *Промокод:* {order['promo_code'] or 'нет'}\n"
        f"📊 *Статус:* {STATUSES.get(order['status'], order['status'])}\n\n"
        f"📦 *Товары:*\n"
    )
    
    for item in items:
        text += f"  • {item['item_name']} x{item['quantity']} = {format_price(item['price'] * item['quantity'])}\n"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ СТАТУС", callback_data=f"order_change_status_{order_id}")],
        [InlineKeyboardButton(text="✍️ НАПИСАТЬ КЛИЕНТУ", url=f"tg://user?id={order['user_id']}")],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="orders_list_all")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("order_change_status_"))
async def order_change_status(callback: CallbackQuery, state: FSMContext):
    """Начать изменение статуса."""
    order_id = int(callback.data.replace("order_change_status_", ""))
    await state.update_data(order_id=order_id)
    
    buttons = []
    for status, label in STATUSES.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"order_set_status_{order_id}_{status}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"order_view_{order_id}")])
    
    await callback.message.edit_text(
        f"✏️ *ИЗМЕНЕНИЕ СТАТУСА ЗАКАЗА #{order_id}*\n\nВыберите новый статус:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_set_status_"))
async def order_set_status(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Установить новый статус."""
    parts = callback.data.split("_")
    order_id = int(parts[3])
    new_status = parts[4]
    
    order = OrderModel.get_by_id(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    # Обновляем статус
    with db.cursor() as c:
        c.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    
    # Отправляем уведомление клиенту
    status_text = STATUSES.get(new_status, new_status)
    await bot.send_message(
        order['user_id'],
        f"📦 *СТАТУС ЗАКАЗА #{order_id} ИЗМЕНЁН*\n\nНовый статус: {status_text}\n\nСпасибо, что выбрали нас!"
    )
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ *Статус заказа #{order_id} изменён на {status_text}*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К ЗАКАЗУ", callback_data=f"order_view_{order_id}")]
        ])
    )
    await callback.answer()