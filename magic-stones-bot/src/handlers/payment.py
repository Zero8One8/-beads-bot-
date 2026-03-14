"""
Модуль оплаты через Telegram Stars.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment
from aiogram.fsm.context import FSMContext

from src.database.db import db
from src.database.models import OrderModel, CartModel, UserModel, ClubModel
from src.keyboards.inline import get_main_keyboard
from src.services.notifications import AdminNotifier
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery):
    """Обязательный обработчик предпроверки платежа."""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext, bot):
    """Обработка успешной оплаты."""
    payment = message.successful_payment
    payload = payment.invoice_payload
    user_id = message.from_user.id
    
    logger.info(f"Успешная оплата: {payload}, сумма: {payment.total_amount}⭐")
    
    # Определяем тип платежа по payload
    if payload.startswith("order_"):
        # Оплата заказа
        await process_order_payment(user_id, payload, payment, bot)
    elif payload.startswith("club_"):
        # Оплата подписки на клуб
        await process_club_payment(user_id, payload, payment, bot)
    elif payload.startswith("diagnostic_"):
        # Оплата диагностики
        await process_diagnostic_payment(user_id, payment, state, bot)
    elif payload.startswith("gift_"):
        # Оплата подарочного сертификата
        await message.answer("✅ Сертификат оплачен! Код будет отправлен отдельно.")
    elif payload.startswith("service_"):
        # Оплата услуги (обрабатывается в services.py)
        pass
    else:
        logger.warning(f"Неизвестный тип платежа: {payload}")
    
    await state.clear()


async def process_order_payment(user_id: int, payload: str, payment, bot):
    """Обработка оплаты заказа."""
    try:
        order_id = int(payload.replace("order_", ""))
    except:
        logger.error(f"Не удалось получить order_id из {payload}")
        return
    
    # Получаем заказ
    order = OrderModel.get_by_id(order_id)
    if not order:
        logger.error(f"Заказ {order_id} не найден")
        return
    
    # Обновляем статус заказа
    with db.cursor() as c:
        c.execute("""
            UPDATE orders SET status = 'paid', payment_details = ? WHERE id = ?
        """, (f"stars_charge:{payment.telegram_payment_charge_id}", order_id))
    
    # Сохраняем информацию о платеже Stars
    with db.cursor() as c:
        c.execute("""
            INSERT INTO stars_orders (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, order_id, f"Заказ #{order_id}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))
    
    # Уведомление админу
    await AdminNotifier(bot).new_order(order_id)
    
    # Уведомление пользователю
    await bot.send_message(
        user_id,
        f"✅ *ЗАКАЗ #{order_id} ОПЛАЧЕН!*\n\n"
        f"Мы уже начали его готовить. Мастер свяжется с вами для уточнения деталей.",
        reply_markup=get_main_keyboard()
    )


async def process_club_payment(user_id: int, payload: str, payment, bot):
    """Обработка оплаты подписки на клуб."""
    try:
        _, period, _ = payload.split("_")
    except:
        logger.error(f"Неверный формат club payload: {payload}")
        return
    
    duration = 30 if period == "month" else 365
    
    # Активируем подписку
    ClubModel.activate_paid(
        user_id=user_id,
        payment_id=payment.telegram_payment_charge_id,
        duration_days=duration
    )
    
    # Сохраняем информацию о платеже
    with db.cursor() as c:
        c.execute("""
            INSERT INTO stars_orders (user_id, order_id, item_name, stars_amount, charge_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 0, f"Подписка клуб {period}", payment.total_amount,
              payment.telegram_payment_charge_id, datetime.now()))
    
    await bot.send_message(
        user_id,
        "🎉 *ПОДПИСКА АКТИВИРОВАНА!*\n\n"
        "Добро пожаловать в «Портал силы»! Теперь вам доступны все материалы клуба.",
        reply_markup=get_main_keyboard()
    )


async def process_diagnostic_payment(user_id: int, payment, state, bot):
    """Обработка оплаты диагностики."""
    from src.handlers.diagnostic import diagnostic_paid
    await diagnostic_paid(user_id, state, bot)