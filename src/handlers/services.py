"""
Услуги - запись на сеансы (диагностика, отливка, отмаливание, родовые программы и т.д.)
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import ServiceModel, ScheduleModel, ConsultationModel, UserModel
from src.keyboards.services import (
    get_services_keyboard, get_service_detail_keyboard,
    get_dates_keyboard, get_times_keyboard, get_booking_confirm_keyboard
)
from src.utils.helpers import format_price
from src.services.notifications import AdminNotifier
from src.services.stars_payment import StarsPayment
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class BookingStates(StatesGroup):
    selecting_service = State()
    selecting_date = State()
    selecting_time = State()
    entering_comment = State()
    confirming = State()


@router.callback_query(F.data == "services")
async def services_list(callback: CallbackQuery):
    """Список услуг."""
    services = ServiceModel.get_all(active_only=True)
    
    if not services:
        await callback.message.edit_text(
            "✨ *УСЛУГИ*\n\n"
            "Раздел находится в наполнении. Скоро здесь появятся услуги мастера.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "✨ *НАШИ УСЛУГИ*\n\n"
    text += "Индивидуальная работа с мастером для глубокой трансформации.\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_services_keyboard(services)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_"))
async def service_detail(callback: CallbackQuery, state: FSMContext):
    """Детальная информация об услуге."""
    service_id = int(callback.data.split("_")[1])
    service = ServiceModel.get_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return
    
    await state.update_data(service_id=service_id, service_name=service['name'], service_price=service['price'])
    await state.set_state(BookingStates.selecting_date)
    
    # Получаем доступные даты
    slots = ScheduleModel.get_available(days_ahead=30)
    dates = sorted(set(s['slot_date'] for s in slots))
    
    text = (
        f"✨ *{service['name']}*\n\n"
        f"{service['description']}\n\n"
        f"💰 *Стоимость:* {format_price(service['price'])}\n"
        f"⏱️ *Длительность:* {service['duration']} мин\n\n"
        f"📅 *Доступные даты:*"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_dates_keyboard(dates)
    )
    await callback.answer()


@router.callback_query(BookingStates.selecting_date, F.data.startswith("date_"))
async def select_time(callback: CallbackQuery, state: FSMContext):
    """Выбор времени после выбора даты."""
    selected_date = callback.data.replace("date_", "")
    await state.update_data(selected_date=selected_date)
    
    slots = ScheduleModel.get_available()
    times = [s['time_slot'] for s in slots if s['slot_date'] == selected_date]
    
    if not times:
        await callback.answer("❌ На эту дату нет свободных слотов", show_alert=True)
        return
    
    await state.set_state(BookingStates.selecting_time)
    
    await callback.message.edit_text(
        f"📅 *Дата:* {selected_date}\n\nВыберите время:",
        reply_markup=get_times_keyboard(times)
    )
    await callback.answer()


@router.callback_query(BookingStates.selecting_time, F.data.startswith("time_"))
async def enter_comment(callback: CallbackQuery, state: FSMContext):
    """Выбор времени, предложение оставить комментарий."""
    selected_time = callback.data.replace("time_", "")
    await state.update_data(selected_time=selected_time)
    await state.set_state(BookingStates.entering_comment)
    
    await callback.message.edit_text(
        "📝 Если хотите, оставьте комментарий или вопрос к мастеру.\n"
        "Или отправьте /skip, чтобы продолжить без комментария."
    )
    await callback.answer()


@router.message(BookingStates.entering_comment)
async def comment_received(message: Message, state: FSMContext):
    """Обработка комментария."""
    comment = None if message.text == "/skip" else message.text
    await state.update_data(comment=comment)
    await state.set_state(BookingStates.confirming)
    
    data = await state.get_data()
    
    text = (
        "✅ *ПОДТВЕРДИТЕ ЗАПИСЬ*\n\n"
        f"✨ *Услуга:* {data['service_name']}\n"
        f"💰 *Стоимость:* {format_price(data['service_price'])}\n"
        f"📅 *Дата:* {data['selected_date']}\n"
        f"⏰ *Время:* {data['selected_time']}\n"
    )
    if comment:
        text += f"📝 *Комментарий:* {comment}\n"
    
    await message.answer(
        text,
        reply_markup=get_booking_confirm_keyboard()
    )


@router.callback_query(BookingStates.confirming, F.data == "booking_confirm")
async def booking_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение записи и оплата."""
    data = await state.get_data()
    user_id = callback.from_user.id
    service_id = data['service_id']
    service_name = data['service_name']
    service_price = data['service_price']
    selected_date = data['selected_date']
    selected_time = data['selected_time']
    comment = data.get('comment')
    
    # Находим ID слота
    with db.cursor() as c:
        c.execute("""
            SELECT id FROM schedule_slots
            WHERE slot_date = ? AND time_slot = ? AND available = 1
        """, (selected_date, selected_time))
        slot = c.fetchone()
    
    if not slot:
        await callback.message.edit_text(
            "❌ К сожалению, этот слот уже занят. Попробуйте выбрать другое время.",
            reply_markup=get_services_keyboard(ServiceModel.get_all())
        )
        await state.clear()
        await callback.answer()
        return
    
    slot_id = slot['id']
    
    # Сохраняем в состояние для дальнейшей обработки после оплаты
    await state.update_data(slot_id=slot_id, comment=comment)
    
    # Создаём счёт на оплату
    await StarsPayment.create_invoice(
        bot=bot,
        user_id=user_id,
        title=f"Услуга: {service_name}",
        description=f"Запись на {selected_date} в {selected_time}",
        payload=f"service_{service_id}_{slot_id}_{user_id}",
        amount_rub=service_price
    )
    
    await callback.answer("💳 Счёт создан", show_alert=False)


@router.message(F.successful_payment)
async def service_paid(message: Message, state: FSMContext, bot: Bot):
    """Обработка успешной оплаты услуги."""
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("service_"):
        _, service_id, slot_id, user_id_str = payload.split("_")
        service_id = int(service_id)
        slot_id = int(slot_id)
        user_id = int(user_id_str)
        
        if user_id != message.from_user.id:
            return
        
        # Бронируем слот
        success = ScheduleModel.book(slot_id, user_id)
        if not success:
            await message.answer("❌ Ошибка бронирования. Свяжитесь с мастером.")
            return
        
        # Получаем комментарий из состояния (если есть)
        data = await state.get_data()
        comment = data.get('comment')
        
        # Создаём запись
        consult_id = ConsultationModel.create(user_id, service_id, slot_id, comment)
        
        # Сохраняем информацию о платеже
        with db.cursor() as c:
            c.execute("""
                INSERT INTO stars_orders (user_id, order_id, item_name, stars_amount, charge_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, consult_id, f"Услуга #{service_id}", 
                  message.successful_payment.total_amount,
                  message.successful_payment.telegram_payment_charge_id, datetime.now()))
        
        await state.clear()
        
        # Уведомление клиенту
        await message.answer(
            "✅ *ВЫ УСПЕШНО ЗАПИСАНЫ!*\n\n"
            "Мастер свяжется с вами для подтверждения.\n"
            "Вы можете посмотреть свои записи в разделе «Мои записи».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📅 МОИ ЗАПИСИ", callback_data="my_bookings")],
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
            ])
        )
        
        # Уведомление админу
        user = UserModel.get(user_id)
        name = user['first_name'] or user['username'] or str(user_id)
        
        with db.cursor() as c:
            c.execute("SELECT name FROM services WHERE id = ?", (service_id,))
            service = c.fetchone()
            service_name = service['name'] if service else "Услуга"
        
        admin_text = (
            f"📅 *НОВАЯ ЗАПИСЬ НА УСЛУГУ*\n\n"
            f"👤 *Клиент:* {name} (@{user['username']})\n"
            f"✨ *Услуга:* {service_name}\n"
            f"📅 *Дата:* {data.get('selected_date', 'не указана')}\n"
            f"⏰ *Время:* {data.get('selected_time', 'не указано')}\n"
            f"📝 *Комментарий:* {comment or 'нет'}\n"
            f"💰 *Оплачено:* {message.successful_payment.total_amount}⭐"
        )
        
        await bot.send_message(Config.ADMIN_ID, admin_text)
    else:
        # Обработка других платежей (товары и т.д.)
        pass


@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    """Список записей пользователя."""
    user_id = callback.from_user.id
    bookings = ConsultationModel.get_user_consultations(user_id)
    
    if not bookings:
        await callback.message.edit_text(
            "📭 У вас пока нет записей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✨ УСЛУГИ", callback_data="services")],
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "📅 *МОИ ЗАПИСИ*\n\n"
    for b in bookings:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(b['status'], '❓')
        
        text += (
            f"{status_emoji} *{b['service_name']}*\n"
            f"  {b['slot_date']} в {b['time_slot']}\n"
            f"  Статус: {b['status']}\n\n"
        )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ УСЛУГИ", callback_data="services")],
            [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
        ])
    )
    await callback.answer()