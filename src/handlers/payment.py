"""
Модуль оплаты через Telegram Stars.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from src.database.db import db
from src.database.models import OrderModel, CartModel, UserModel, ClubModel
from src.keyboards.inline import get_main_keyboard
from src.services.notifications import AdminNotifier
from src.utils.helpers import format_price
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery):
    """Обязательный обработчик предпроверки платежа."""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext, bot):
    """Центральный обработчик всех успешных оплат."""
    payment = message.successful_payment
    payload = payment.invoice_payload
    user_id = message.from_user.id

    logger.info(f"Успешная оплата: {payload}, сумма: {payment.total_amount} Stars, user: {user_id}")

    if payload.startswith("order_"):
        await _process_order_payment(message, payload, payment, bot)

    elif payload.startswith("club_"):
        await _process_club_payment(message, payload, payment, bot)

    elif payload.startswith("diagnostic_"):
        await _process_diagnostic_payment(message, payment, state, bot)

    elif payload.startswith("service_"):
        await _process_service_payment(message, payload, payment, bot)

    elif payload.startswith("gift_"):
        await _process_gift_payment(message, payload, payment, bot)

    else:
        logger.warning(f"Неизвестный тип платежа: {payload}")
        await message.answer(
            "✅ Оплата получена!\n\nСвяжитесь с мастером для уточнения деталей.",
            reply_markup=get_main_keyboard()
        )

    await state.clear()


# ──────────────────────────────────────────────────────────────
# ОБРАБОТЧИКИ КНОПОК ОПЛАТЫ В КОРЗИНЕ
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "pay_stars")
async def pay_stars(callback: CallbackQuery, state: FSMContext, bot):
    """Оплата заказа через Stars."""
    from src.services.stars_payment import StarsPayment

    data = await state.get_data()
    user_id = callback.from_user.id
    final_total = data.get('final_total', 0)
    promo_code = data.get('promo_code')
    discount = data.get('discount_total', 0)

    if not final_total or final_total <= 0:
        await callback.answer("❌ Ошибка суммы заказа", show_alert=True)
        return

    total_orig, items = CartModel.get_total(user_id)
    if not items:
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return

    order_id = OrderModel.create(
        user_id=user_id,
        total=final_total,
        payment_method='stars',
        promo_code=promo_code
    )

    for item in items:
        OrderModel.add_item(
            order_id=order_id,
            user_id=user_id,
            item_id=item['bracelet_id'],
            item_name=item['name'],
            quantity=item['quantity'],
            price=item['price'] or 0
        )

    await StarsPayment.create_invoice(
        bot=bot,
        user_id=user_id,
        title=f"Заказ #{order_id}",
        description=f"{len(items)} товар(ов) на сумму {format_price(final_total)}",
        payload=f"order_{order_id}",
        amount_rub=final_total
    )

    await callback.answer("💳 Счёт создан!", show_alert=False)


@router.callback_query(F.data == "pay_bonus")
async def pay_bonus(callback: CallbackQuery, state: FSMContext):
    """Оплата бонусами полностью."""
    user_id = callback.from_user.id
    data = await state.get_data()
    final_total = data.get('final_total', 0)

    bonus_balance = UserModel.get_bonus_balance(user_id)
    if bonus_balance < final_total:
        await callback.answer("❌ Недостаточно бонусов", show_alert=True)
        return

    total_orig, items = CartModel.get_total(user_id)
    if not items:
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return

    promo_code = data.get('promo_code')
    discount = data.get('discount_total', 0)

    order_id = OrderModel.create(
        user_id=user_id,
        total=final_total,
        payment_method='bonus',
        promo_code=promo_code,
        bonus_used=final_total
    )

    for item in items:
        OrderModel.add_item(
            order_id=order_id,
            user_id=user_id,
            item_id=item['bracelet_id'],
            item_name=item['name'],
            quantity=item['quantity'],
            price=item['price'] or 0
        )

    with db.cursor() as c:
        c.execute("UPDATE referral_balance SET balance = balance - ? WHERE user_id = ?",
                  (final_total, user_id))
        c.execute("""INSERT INTO bonus_history (user_id, amount, operation, order_id, created_at)
                     VALUES (?, ?, 'used', ?, ?)""",
                  (user_id, -final_total, order_id, datetime.now()))

    CartModel.clear(user_id)
    await state.clear()

    await callback.message.edit_text(
        f"✅ *ЗАКАЗ #{order_id} ОПЛАЧЕН БОНУСАМИ!*\n\n"
        f"Мастер свяжется с вами для уточнения деталей.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    await AdminNotifier(callback.bot).new_order(order_id)
    await callback.answer()


@router.callback_query(F.data == "pay_partial_bonus")
async def pay_partial_bonus(callback: CallbackQuery, state: FSMContext, bot):
    """Частичная оплата бонусами + Stars."""
    from src.services.stars_payment import StarsPayment

    user_id = callback.from_user.id
    data = await state.get_data()
    final_total = data.get('final_total', 0)
    bonus_balance = UserModel.get_bonus_balance(user_id)

    remainder = max(0, final_total - bonus_balance)

    total_orig, items = CartModel.get_total(user_id)
    if not items:
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return

    promo_code = data.get('promo_code')
    discount = data.get('discount_total', 0)

    order_id = OrderModel.create(
        user_id=user_id,
        total=final_total,
        payment_method='stars+bonus',
        promo_code=promo_code,
        bonus_used=bonus_balance
    )

    for item in items:
        OrderModel.add_item(
            order_id=order_id,
            user_id=user_id,
            item_id=item['bracelet_id'],
            item_name=item['name'],
            quantity=item['quantity'],
            price=item['price'] or 0
        )

    await state.update_data(partial_order_id=order_id, partial_bonus=bonus_balance)

    await StarsPayment.create_invoice(
        bot=bot,
        user_id=user_id,
        title=f"Заказ #{order_id} (часть Stars)",
        description=f"Доплата {format_price(remainder)} ({format_price(bonus_balance)} спишется бонусами)",
        payload=f"order_{order_id}",
        amount_rub=remainder
    )

    await callback.answer("💳 Счёт создан!", show_alert=False)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Кнопка-заглушка (например, 'Уже в корзине')."""
    await callback.answer()


# ──────────────────────────────────────────────────────────────
# ВНУТРЕННИЕ ФУНКЦИИ ОБРАБОТКИ ПЛАТЕЖЕЙ
# ──────────────────────────────────────────────────────────────

async def _process_order_payment(message: Message, payload: str, payment, bot):
    """Обработка оплаты заказа."""
    try:
        order_id = int(payload.replace("order_", ""))
    except (ValueError, AttributeError):
        logger.error(f"Неверный order payload: {payload}")
        return

    user_id = message.from_user.id

    with db.cursor() as c:
        c.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
        c.execute("""
            INSERT OR IGNORE INTO stars_orders
                (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, order_id, f"Заказ #{order_id}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))

    # Списываем частичные бонусы если были
    order = OrderModel.get_by_id(order_id)
    if order and order.get('bonus_used') and order['bonus_used'] > 0:
        with db.cursor() as c:
            c.execute("UPDATE referral_balance SET balance = balance - ? WHERE user_id = ?",
                      (order['bonus_used'], user_id))
            c.execute("""INSERT INTO bonus_history (user_id, amount, operation, order_id, created_at)
                         VALUES (?, ?, 'used', ?, ?)""",
                      (user_id, -order['bonus_used'], order_id, datetime.now()))

    CartModel.clear(user_id)

    await AdminNotifier(bot).new_order(order_id)
    await message.answer(
        f"✅ *ЗАКАЗ #{order_id} ОПЛАЧЕН!*\n\n"
        "Мастер свяжется с вами для уточнения деталей.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def _process_club_payment(message: Message, payload: str, payment, bot):
    """Обработка оплаты подписки на клуб."""
    user_id = message.from_user.id
    parts = payload.split("_")

    if len(parts) < 2:
        logger.error(f"Неверный club payload: {payload}")
        return

    period = parts[1]
    duration = 30 if period == "month" else 365

    ClubModel.activate_paid(
        user_id=user_id,
        payment_id=payment.telegram_payment_charge_id,
        duration_days=duration
    )

    with db.cursor() as c:
        c.execute("""
            INSERT OR IGNORE INTO stars_orders
                (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 0, f"Подписка клуб {period}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))

    await message.answer(
        "🎉 *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
        "Добро пожаловать в «Портал силы»! Теперь вам доступны все материалы клуба.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 МАТЕРИАЛЫ КЛУБА", callback_data="club_content")],
            [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
        ])
    )


async def _process_diagnostic_payment(message: Message, payment, state: FSMContext, bot):
    """Обработка оплаты диагностики — запускаем флоу загрузки фото."""
    from aiogram.fsm.state import State, StatesGroup

    user_id = message.from_user.id

    with db.cursor() as c:
        c.execute("""
            INSERT OR IGNORE INTO stars_orders
                (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 0, "Диагностика", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))

    from src.handlers.diagnostic import DiagnosticStates
    await state.set_state(DiagnosticStates.waiting_photo1)

    await message.answer(
        "✅ *Оплата получена!*\n\n"
        "📸 *ШАГ 1 ИЗ 3: ЗАГРУЗИТЕ ФОТО*\n\n"
        "Сделайте фотографию лица (крупный план).",
        parse_mode="Markdown"
    )


async def _process_service_payment(message: Message, payload: str, payment, bot):
    """Обработка оплаты услуги."""
    user_id = message.from_user.id

    with db.cursor() as c:
        c.execute("""
            INSERT OR IGNORE INTO stars_orders
                (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 0, f"Услуга {payload}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))

        c.execute("""
            UPDATE consultations SET status = 'paid'
            WHERE user_id = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))

    await message.answer(
        "✅ *ОПЛАТА УСЛУГИ ПОЛУЧЕНА!*\n\n"
        "Мастер свяжется с вами для подтверждения записи.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def _process_gift_payment(message: Message, payload: str, payment, bot):
    """Обработка оплаты подарочного сертификата."""
    import random
    import string
    from datetime import timedelta

    user_id = message.from_user.id
    amount = payment.total_amount

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    expires_at = datetime.now() + timedelta(days=365)

    with db.cursor() as c:
        c.execute("""
            INSERT INTO gift_certificates
                (code, amount, buyer_id, status, created_at, expires_at)
            VALUES (?, ?, ?, 'active', ?, ?)
        """, (code, amount, user_id, datetime.now(), expires_at))

        c.execute("""
            INSERT OR IGNORE INTO stars_orders
                (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 0, f"Сертификат {code}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))

    await message.answer(
        f"🎁 *СЕРТИФИКАТ ОПЛАЧЕН!*\n\n"
        f"Код сертификата: `{code}`\n"
        f"Номинал: {amount} Stars\n"
        f"Срок действия: 1 год\n\n"
        f"Передайте этот код получателю. Он активирует его в боте через кнопку «Активировать сертификат».",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
