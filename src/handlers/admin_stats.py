"""
Админ-панель: статистика и аналитика.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import UserModel
from src.services.analytics import Analytics
from src.utils.helpers import format_price, format_number

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Главное меню статистики."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    text = (
        "📊 *СТАТИСТИКА И АНАЛИТИКА*\n\n"
        "Выберите раздел для просмотра:"
    )
    
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
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "stats_users")
async def stats_users(callback: CallbackQuery):
    """Статистика пользователей."""
    stats = Analytics.get_user_stats(30)
    
    text = (
        "👥 *СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ*\n\n"
        f"📊 *Всего пользователей:* {format_number(stats['total'])}\n"
        f"🆕 *Новых за 30 дней:* {format_number(stats['new'])}\n"
        f"🔥 *Активных за 30 дней:* {format_number(stats['active'])}\n\n"
        "*Последние 7 дней:*\n"
    )
    
    for day in stats['daily_new'][-7:]:
        text += f"  • {day['date']}: +{day['count']} новых\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_users")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_orders")
async def stats_orders(callback: CallbackQuery):
    """Статистика заказов."""
    stats = Analytics.get_order_stats(30)
    
    text = (
        "📦 *СТАТИСТИКА ЗАКАЗОВ*\n\n"
        f"📊 *Всего заказов:* {format_number(stats['total_orders'])}\n"
        f"💰 *Общая выручка:* {format_price(stats['total_revenue'])}\n\n"
        f"*За последние 30 дней:*\n"
        f"  • Заказов: {format_number(stats['period_orders'])}\n"
        f"  • Выручка: {format_price(stats['period_revenue'])}\n"
        f"  • Средний чек: {format_price(stats['avg_check'])}\n\n"
        "*Последние 7 дней:*\n"
    )
    
    for day in stats['daily'][-7:]:
        text += f"  • {day['date']}: {day['count']} заказов, {format_price(day['revenue'])}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_orders")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_products")
async def stats_products(callback: CallbackQuery):
    """Популярные товары."""
    products = Analytics.get_popular_products(10)
    
    text = "💎 *ПОПУЛЯРНЫЕ ТОВАРЫ*\n\n"
    
    if not products:
        text += "Пока нет продаж."
    else:
        for i, p in enumerate(products, 1):
            text += (
                f"{i}. *{p['item_name']}*\n"
                f"   • Продаж: {p['sales_count']}\n"
                f"   • Выручка: {format_price(p['total_revenue'])}\n\n"
            )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_products")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_stones")
async def stats_stones(callback: CallbackQuery):
    """Популярные камни."""
    stones = Analytics.get_popular_stones(10)
    
    text = "🔮 *ПОПУЛЯРНЫЕ КАМНИ*\n\n"
    
    if not stones:
        text += "Пока нет данных."
    else:
        for i, s in enumerate(stones, 1):
            text += f"{i}. {s['emoji']} *{s['stone_name']}* — {s['mentions']} упоминаний\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_stones")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_funnel")
async def stats_funnel(callback: CallbackQuery):
    """Воронка продаж."""
    funnel = Analytics.get_funnel_stats(30)
    
    start = funnel.get('start', 0)
    if start == 0:
        text = "❌ Недостаточно данных для воронки."
    else:
        view_showcase = funnel.get('view_showcase', 0)
        add_to_cart = funnel.get('add_to_cart', 0)
        checkout = funnel.get('checkout', 0)
        payment = funnel.get('payment_success', 0)
        
        text = (
            "📊 *ВОРОНКА ПРОДАЖ (30 дней)*\n\n"
            f"👋 *Начало:* {start} чел.\n"
            f"💎 *Просмотр витрины:* {view_showcase} чел. ({view_showcase/start*100:.1f}%)\n"
            f"🛒 *Добавление в корзину:* {add_to_cart} чел. ({add_to_cart/start*100:.1f}%)\n"
            f"💳 *Оформление заказа:* {checkout} чел. ({checkout/start*100:.1f}%)\n"
            f"✅ *Оплата:* {payment} чел. ({payment/start*100:.1f}%)\n\n"
            f"📈 *Общая конверсия:* {payment/start*100:.1f}%"
        )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_funnel")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_cashback")
async def stats_cashback(callback: CallbackQuery):
    """Статистика бонусной системы."""
    stats = Analytics.get_cashback_stats()
    
    text = (
        "💰 *БОНУСНАЯ СИСТЕМА*\n\n"
        f"💎 *Всего начислено бонусов:* {format_price(stats['total_earned'])}\n"
        f"🔄 *Использовано бонусов:* {format_price(stats['total_used'])}\n"
        f"📦 *Текущий баланс пользователей:* {format_price(stats['total_balance'])}\n"
        f"👥 *Пользователей с бонусами:* {stats['users_with_balance']}\n"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="stats_cashback")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "stats_forecast")
async def stats_forecast(callback: CallbackQuery):
    """Прогноз продаж."""
    # Простой прогноз на основе линейной регрессии
    with db.cursor() as c:
        c.execute("""
            SELECT DATE(created_at) as date, SUM(total_price) as revenue
            FROM orders
            WHERE status = 'paid' AND created_at > datetime('now', '-90 days')
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        history = [dict(row) for row in c.fetchall()]
    
    if len(history) < 7:
        text = "❌ Недостаточно данных для прогноза (нужно минимум 7 дней)."
    else:
        # Простейшая линейная регрессия
        dates = list(range(len(history)))
        revenues = [h['revenue'] or 0 for h in history]
        
        n = len(dates)
        sum_x = sum(dates)
        sum_y = sum(revenues)
        sum_xy = sum(x * y for x, y in zip(dates, revenues))
        sum_xx = sum(x * x for x in dates)
        
        if n * sum_xx - sum_x * sum_x == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
        
        intercept = (sum_y - slope * sum_x) / n
        
        text = "📈 *ПРОГНОЗ ПРОДАЖ НА 30 ДНЕЙ*\n\n"
        last_date = datetime.now()
        
        total_forecast = 0
        for i in range(1, 31):
            pred = slope * (len(history) + i) + intercept
            if pred < 0:
                pred = 0
            total_forecast += pred
            day_date = (last_date + timedelta(days=i)).strftime('%d.%m')
            text += f"  • {day_date}: {format_price(pred)}\n"
            if i % 7 == 0:
                text += "\n"
        
        text += f"\n*Прогноз на месяц:* {format_price(total_forecast)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_stats")]
        ])
    )
    await callback.answer()