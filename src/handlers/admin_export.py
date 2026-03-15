"""
Админ-панель: экспорт данных в CSV.
"""
import csv
import io
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel
from src.utils.helpers import format_price

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_export")
async def admin_export(callback: CallbackQuery):
    """Главное меню экспорта."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    text = (
        "📥 *ЭКСПОРТ ДАННЫХ*\n\n"
        "Выберите тип данных для выгрузки в CSV:"
    )

    buttons = [
        [InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="export_orders")],
        [InlineKeyboardButton(text="👥 ПОЛЬЗОВАТЕЛИ", callback_data="export_users")],
        [InlineKeyboardButton(text="💎 ТОВАРЫ", callback_data="export_products")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "export_orders")
async def export_orders(callback: CallbackQuery):
    """Экспорт заказов в CSV."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    await callback.message.edit_text("⏳ Генерирую файл с заказами...")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'ID заказа', 'ID пользователя', 'Имя', 'Username',
        'Сумма', 'Статус', 'Метод оплаты', 'Дата создания',
        'Промокод', 'Скидка', 'Бонусы использовано', 'Кэшбэк начислено',
        'Кол-во товаров'
    ])

    with db.cursor() as c:
        c.execute("""
            SELECT
                o.id, o.user_id, u.first_name, u.username,
                o.total_price, o.status, o.payment_method, o.created_at,
                o.promo_code, o.discount_rub, o.bonus_used, o.cashback_amount,
                (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as items_count
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.user_id
            ORDER BY o.created_at DESC
            LIMIT 5000
        """)

        for row in c.fetchall():
            writer.writerow([
                row['id'],
                row['user_id'],
                row['first_name'] or '',
                row['username'] or '',
                row['total_price'],
                row['status'],
                row['payment_method'] or '',
                row['created_at'][:19] if row['created_at'] else '',
                row['promo_code'] or '',
                row['discount_rub'] or 0,
                row['bonus_used'] or 0,
                row['cashback_amount'] or 0,
                row['items_count'] or 0
            ])

    output.seek(0)
    csv_data = output.getvalue().encode('utf-8-sig')
    filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    await callback.message.answer_document(
        document=BufferedInputFile(csv_data, filename=filename),
        caption="📦 *Заказы* (CSV)",
        parse_mode="Markdown"
    )
    await callback.message.delete()


@router.callback_query(F.data == "export_users")
async def export_users(callback: CallbackQuery):
    """Экспорт пользователей в CSV."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    await callback.message.edit_text("⏳ Генерирую файл с пользователями...")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'ID пользователя', 'Имя', 'Username', 'Дата регистрации',
        'День рождения', 'Приглашён пользователем',
        'Баланс бонусов', 'Всего заработано бонусов', 'Кол-во рефералов'
    ])

    with db.cursor() as c:
        c.execute("""
            SELECT
                u.user_id, u.first_name, u.username, u.created_at,
                u.birthday, u.referred_by,
                COALESCE(rb.balance, 0) as balance,
                COALESCE(rb.total_earned, 0) as total_earned,
                COALESCE(rb.referral_count, 0) as referral_count
            FROM users u
            LEFT JOIN referral_balance rb ON u.user_id = rb.user_id
            ORDER BY u.created_at DESC
            LIMIT 5000
        """)

        for row in c.fetchall():
            writer.writerow([
                row['user_id'],
                row['first_name'] or '',
                row['username'] or '',
                row['created_at'][:19] if row['created_at'] else '',
                row['birthday'] or '',
                row['referred_by'] or '',
                row['balance'],
                row['total_earned'],
                row['referral_count']
            ])

    output.seek(0)
    csv_data = output.getvalue().encode('utf-8-sig')
    filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    await callback.message.answer_document(
        document=BufferedInputFile(csv_data, filename=filename),
        caption="👥 *Пользователи* (CSV)",
        parse_mode="Markdown"
    )
    await callback.message.delete()


@router.callback_query(F.data == "export_products")
async def export_products(callback: CallbackQuery):
    """Экспорт товаров в CSV."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    await callback.message.edit_text("⏳ Генерирую файл с товарами...")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'ID', 'Название', 'Категория', 'Цена', 'Stars цена',
        'Описание', 'Дата создания'
    ])

    with db.cursor() as c:
        c.execute("""
            SELECT
                si.id, si.name, sc.name as category, si.price, si.stars_price,
                si.description, si.created_at
            FROM showcase_items si
            LEFT JOIN showcase_collections sc ON si.collection_id = sc.id
            ORDER BY si.created_at DESC
        """)

        for row in c.fetchall():
            writer.writerow([
                f"V{row['id']}",
                row['name'],
                row['category'] or '',
                row['price'],
                row['stars_price'] or 0,
                (row['description'] or '')[:100],
                row['created_at'][:19] if row['created_at'] else ''
            ])

        c.execute("""
            SELECT
                b.id, b.name, c.name as category, b.price, 0 as stars_price,
                b.description, b.created_at
            FROM bracelets b
            LEFT JOIN categories c ON b.category_id = c.id
            WHERE b.deleted = 0
            ORDER BY b.created_at DESC
        """)

        for row in c.fetchall():
            writer.writerow([
                f"B{row['id']}",
                row['name'],
                row['category'] or '',
                row['price'],
                0,
                (row['description'] or '')[:100],
                row['created_at'][:19] if row['created_at'] else ''
            ])

    output.seek(0)
    csv_data = output.getvalue().encode('utf-8-sig')
    filename = f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    await callback.message.answer_document(
        document=BufferedInputFile(csv_data, filename=filename),
        caption="💎 *Товары* (CSV)",
        parse_mode="Markdown"
    )
    await callback.message.delete()

