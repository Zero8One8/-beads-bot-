"""
Админ-панель: управление услугами и расписанием.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import UserModel, ServiceModel, ScheduleModel, ConsultationModel
from src.utils.helpers import format_price, format_datetime

logger = logging.getLogger(__name__)
router = Router()


class AdminServiceStates(StatesGroup):
    # Услуги
    service_create_name = State()
    service_create_desc = State()
    service_create_price = State()
    service_create_duration = State()
    service_edit = State()
    service_edit_field = State()
    
    # Расписание
    schedule_add_date = State()
    schedule_add_time = State()
    schedule_add_many = State()


@router.callback_query(F.data == "admin_services")
async def admin_services(callback: CallbackQuery):
    """Главное меню услуг."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    services = ServiceModel.get_all(active_only=False)
    pending = ConsultationModel.get_pending()  # нужно добавить этот метод
    
    text = (
        f"✨ *УПРАВЛЕНИЕ УСЛУГАМИ*\n\n"
        f"📋 *Услуг:* {len(services)}\n"
        f"📅 *Ожидают подтверждения:* {len(pending)}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК УСЛУГ", callback_data="admin_services_list")],
        [InlineKeyboardButton(text="➕ СОЗДАТЬ УСЛУГУ", callback_data="admin_service_create")],
        [InlineKeyboardButton(text="📅 УПРАВЛЕНИЕ РАСПИСАНИЕМ", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="📋 ЗАПИСИ КЛИЕНТОВ", callback_data="admin_consultations")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ======================================================
# УПРАВЛЕНИЕ УСЛУГАМИ
# ======================================================

@router.callback_query(F.data == "admin_services_list")
async def admin_services_list(callback: CallbackQuery):
    """Список услуг."""
    services = ServiceModel.get_all(active_only=False)
    
    if not services:
        await callback.message.edit_text(
            "📭 Услуг пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_service_create")],
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_services")]
            ])
        )
        await callback.answer()
        return
    
    text = "✨ *СПИСОК УСЛУГ*\n\n"
    buttons = []
    
    for s in services:
        status = "✅" if s['active'] else "❌"
        text += f"{status} *{s['name']}* — {format_price(s['price'])} ({s['duration']} мин)\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {s['name'][:20]}",
            callback_data=f"admin_service_view_{s['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_services")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_service_view_"))
async def admin_service_view(callback: CallbackQuery):
    """Просмотр деталей услуги."""
    service_id = int(callback.data.replace("admin_service_view_", ""))
    service = ServiceModel.get_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена")
        return
    
    status = "✅ Активна" if service['active'] else "❌ Неактивна"
    
    text = (
        f"✨ *{service['name']}*\n\n"
        f"📊 *Статус:* {status}\n"
        f"💰 *Цена:* {format_price(service['price'])}\n"
        f"⏱️ *Длительность:* {service['duration']} мин\n"
        f"📝 *Описание:*\n{service['description']}\n"
    )
    
    buttons = [
        [InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ", callback_data=f"admin_service_edit_{service_id}")],
        [InlineKeyboardButton(text="🔄 АКТИВИРОВАТЬ/ДЕАКТИВИРОВАТЬ", callback_data=f"admin_service_toggle_{service_id}")],
        [InlineKeyboardButton(text="❌ УДАЛИТЬ", callback_data=f"admin_service_delete_{service_id}")],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="admin_services_list")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_service_create")
async def admin_service_create(callback: CallbackQuery, state: FSMContext):
    """Создание услуги."""
    await state.set_state(AdminServiceStates.service_create_name)
    await callback.message.edit_text(
        "➕ *СОЗДАНИЕ УСЛУГИ*\n\nВведите название услуги:"
    )
    await callback.answer()


@router.message(AdminServiceStates.service_create_name)
async def admin_service_create_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AdminServiceStates.service_create_desc)
    await message.answer("📝 Введите описание услуги:")


@router.message(AdminServiceStates.service_create_desc)
async def admin_service_create_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AdminServiceStates.service_create_price)
    await message.answer("💰 Введите стоимость услуги в рублях (только число):")


@router.message(AdminServiceStates.service_create_price)
async def admin_service_create_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
    except:
        await message.answer("❌ Введите число")
        return
    
    await state.set_state(AdminServiceStates.service_create_duration)
    await message.answer("⏱️ Введите длительность услуги в минутах:")


@router.message(AdminServiceStates.service_create_duration)
async def admin_service_create_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
    except:
        await message.answer("❌ Введите число")
        return
    
    data = await state.get_data()
    
    with db.cursor() as c:
        c.execute("""
            INSERT INTO services (name, description, price, duration, active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (data['name'], data['description'], data['price'], duration, datetime.now()))
        service_id = c.lastrowid
    
    await state.clear()
    await message.answer(
        f"✅ *УСЛУГА СОЗДАНА!*\n\nID: {service_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К УСЛУГАМ", callback_data="admin_services_list")]
        ])
    )


@router.callback_query(F.data.startswith("admin_service_toggle_"))
async def admin_service_toggle(callback: CallbackQuery):
    """Активация/деактивация услуги."""
    service_id = int(callback.data.replace("admin_service_toggle_", ""))
    service = ServiceModel.get_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена")
        return
    
    new_status = 0 if service['active'] else 1
    
    with db.cursor() as c:
        c.execute("UPDATE services SET active = ? WHERE id = ?", (new_status, service_id))
    
    status_text = "активирована" if new_status else "деактивирована"
    await callback.message.edit_text(
        f"✅ Услуга {status_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К УСЛУГЕ", callback_data=f"admin_service_view_{service_id}")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_service_delete_"))
async def admin_service_delete(callback: CallbackQuery):
    """Удаление услуги."""
    service_id = int(callback.data.replace("admin_service_delete_", ""))
    
    await callback.message.edit_text(
        f"⚠️ *ПОДТВЕРДИТЕ УДАЛЕНИЕ*\n\n"
        f"Удалить услугу?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"admin_service_confirm_delete_{service_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"admin_service_view_{service_id}")
            ]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_service_confirm_delete_"))
async def admin_service_confirm_delete(callback: CallbackQuery):
    service_id = int(callback.data.replace("admin_service_confirm_delete_", ""))
    
    with db.cursor() as c:
        c.execute("DELETE FROM services WHERE id = ?", (service_id,))
    
    await callback.message.edit_text(
        "✅ Услуга удалена",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К УСЛУГАМ", callback_data="admin_services_list")]
        ])
    )
    await callback.answer()


# ======================================================
# УПРАВЛЕНИЕ РАСПИСАНИЕМ
# ======================================================

@router.callback_query(F.data == "admin_schedule")
async def admin_schedule(callback: CallbackQuery):
    """Управление расписанием."""
    slots = ScheduleModel.get_available(days_ahead=7)
    
    text = (
        f"📅 *УПРАВЛЕНИЕ РАСПИСАНИЕМ*\n\n"
        f"Свободных слотов на 7 дней: {len(slots)}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 ПОСМОТРЕТЬ СЛОТЫ", callback_data="admin_slots_view")],
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ СЛОТЫ", callback_data="admin_slots_add")],
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ НА НЕДЕЛЮ", callback_data="admin_slots_add_week")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_services")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_slots_view")
async def admin_slots_view(callback: CallbackQuery):
    """Просмотр слотов."""
    slots = ScheduleModel.get_available(days_ahead=14)
    
    if not slots:
        await callback.message.edit_text(
            "📭 Нет свободных слотов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_schedule")]
            ])
        )
        await callback.answer()
        return
    
    # Группируем по датам
    by_date = {}
    for s in slots:
        date = s['slot_date']
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(s['time_slot'])
    
    text = "📅 *СВОБОДНЫЕ СЛОТЫ*\n\n"
    for date, times in sorted(by_date.items()):
        text += f"*{date}:* {', '.join(times[:5])}"
        if len(times) > 5:
            text += f" и ещё {len(times)-5}"
        text += "\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_schedule")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "admin_slots_add")
async def admin_slots_add(callback: CallbackQuery, state: FSMContext):
    """Добавление слота."""
    await state.set_state(AdminServiceStates.schedule_add_date)
    await callback.message.edit_text(
        "➕ *ДОБАВЛЕНИЕ СЛОТА*\n\n"
        "Введите дату в формате ГГГГ-ММ-ДД (например, 2026-03-10):"
    )
    await callback.answer()


@router.message(AdminServiceStates.schedule_add_date)
async def admin_slots_add_date(message: Message, state: FSMContext):
    try:
        date = message.text.strip()
        datetime.strptime(date, '%Y-%m-%d')
    except:
        await message.answer("❌ Неверный формат даты")
        return
    
    await state.update_data(slot_date=date)
    await state.set_state(AdminServiceStates.schedule_add_time)
    await message.answer("⏰ Введите время в формате ЧЧ:ММ (например, 14:00):")


@router.message(AdminServiceStates.schedule_add_time)
async def admin_slots_add_time(message: Message, state: FSMContext):
    data = await state.get_data()
    date = data['slot_date']
    time = message.text.strip()
    
    try:
        datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
    except:
        await message.answer("❌ Неверный формат времени")
        return
    
    with db.cursor() as c:
        c.execute("""
            INSERT OR IGNORE INTO schedule_slots (slot_date, time_slot, available)
            VALUES (?, ?, 1)
        """, (date, time))
    
    await state.clear()
    await message.answer(
        "✅ Слот добавлен!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ЕЩЁ", callback_data="admin_slots_add")],
            [InlineKeyboardButton(text="🔙 В РАСПИСАНИЕ", callback_data="admin_schedule")]
        ])
    )


@router.callback_query(F.data == "admin_slots_add_week")
async def admin_slots_add_week(callback: CallbackQuery):
    """Автоматическое добавление слотов на неделю."""
    start_date = datetime.now().date()
    added = 0
    
    for day_offset in range(1, 8):
        day = start_date + timedelta(days=day_offset)
        date_str = day.strftime('%Y-%m-%d')
        
        # Выходные - меньше слотов
        if day.weekday() >= 5:  # суббота, воскресенье
            times = ['10:00', '12:00', '14:00', '16:00']
        else:
            times = ['10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00']
        
        with db.cursor() as c:
            for t in times:
                c.execute("""
                    INSERT OR IGNORE INTO schedule_slots (slot_date, time_slot, available)
                    VALUES (?, ?, 1)
                """, (date_str, t))
                added += 1
    
    await callback.message.edit_text(
        f"✅ Добавлено {added} слотов на следующую неделю!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В РАСПИСАНИЕ", callback_data="admin_schedule")]
        ])
    )
    await callback.answer()


# ======================================================
# УПРАВЛЕНИЕ ЗАПИСЯМИ
# ======================================================

@router.callback_query(F.data == "admin_consultations")
async def admin_consultations(callback: CallbackQuery):
    """Список записей клиентов."""
    with db.cursor() as c:
        c.execute("""
            SELECT c.*, u.first_name, u.username, s.name as service_name, sl.slot_date, sl.time_slot
            FROM consultations c
            JOIN users u ON c.user_id = u.user_id
            JOIN services s ON c.service_id = s.id
            JOIN schedule_slots sl ON c.slot_id = sl.id
            ORDER BY c.created_at DESC
            LIMIT 20
        """)
        consultations = [dict(row) for row in c.fetchall()]
    
    if not consultations:
        await callback.message.edit_text(
            "📭 Нет записей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_services")]
            ])
        )
        await callback.answer()
        return
    
    text = "📋 *ЗАПИСИ КЛИЕНТОВ*\n\n"
    buttons = []
    
    for c in consultations:
        status_emoji = {
            'pending': '⏳',
            'confirmed': '✅',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(c['status'], '❓')
        
        text += f"{status_emoji} #{c['id']} | {c['first_name']} | {c['service_name']} | {c['slot_date']}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📋 Запись #{c['id']}",
            callback_data=f"admin_consult_view_{c['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_services")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_consult_view_"))
async def admin_consult_view(callback: CallbackQuery, bot: Bot):
    """Просмотр деталей записи."""
    consult_id = int(callback.data.replace("admin_consult_view_", ""))
    
    with db.cursor() as c:
        c.execute("""
            SELECT c.*, u.first_name, u.username, u.user_id, s.name as service_name, s.price, sl.slot_date, sl.time_slot
            FROM consultations c
            JOIN users u ON c.user_id = u.user_id
            JOIN services s ON c.service_id = s.id
            JOIN schedule_slots sl ON c.slot_id = sl.id
            WHERE c.id = ?
        """, (consult_id,))
        consult = c.fetchone()
    
    if not consult:
        await callback.answer("❌ Запись не найдена")
        return
    
    status_emoji = {
        'pending': '⏳ Ожидает',
        'confirmed': '✅ Подтверждена',
        'completed': '✔️ Выполнена',
        'cancelled': '❌ Отменена'
    }.get(consult['status'], consult['status'])
    
    text = (
        f"📋 *ЗАПИСЬ #{consult_id}*\n\n"
        f"👤 *Клиент:* {consult['first_name']} (@{consult['username']})\n"
        f"🆔 *ID:* {consult['user_id']}\n"
        f"✨ *Услуга:* {consult['service_name']} — {format_price(consult['price'])}\n"
        f"📅 *Дата:* {consult['slot_date']}\n"
        f"⏰ *Время:* {consult['time_slot']}\n"
        f"📊 *Статус:* {status_emoji}\n"
    )
    
    if consult['comment']:
        text += f"📝 *Комментарий:* {consult['comment']}\n"
    
    buttons = [
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"admin_consult_status_{consult_id}_confirmed")],
        [InlineKeyboardButton(text="✔️ ЗАВЕРШИТЬ", callback_data=f"admin_consult_status_{consult_id}_completed")],
        [InlineKeyboardButton(text="❌ ОТМЕНИТЬ", callback_data=f"admin_consult_status_{consult_id}_cancelled")],
        [InlineKeyboardButton(text="✍️ НАПИСАТЬ КЛИЕНТУ", url=f"tg://user?id={consult['user_id']}")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_consultations")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_consult_status_"))
async def admin_consult_status(callback: CallbackQuery, bot: Bot):
    """Изменение статуса записи."""
    parts = callback.data.split("_")
    consult_id = int(parts[3])
    new_status = parts[4]
    
    with db.cursor() as c:
        c.execute("UPDATE consultations SET status = ? WHERE id = ?", (new_status, consult_id))
        c.execute("SELECT user_id FROM consultations WHERE id = ?", (consult_id,))
        user_id = c.fetchone()['user_id']
    
    status_text = {
        'confirmed': 'подтверждена',
        'completed': 'завершена',
        'cancelled': 'отменена'
    }.get(new_status, new_status)
    
    # Уведомление клиенту
    await bot.send_message(
        user_id,
        f"📅 *СТАТУС ВАШЕЙ ЗАПИСИ ИЗМЕНЁН*\n\n"
        f"Новый статус: {status_text}"
    )
    
    await callback.message.edit_text(
        f"✅ Статус изменён на {new_status}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К ЗАПИСИ", callback_data=f"admin_consult_view_{consult_id}")]
        ])
    )
    await callback.answer()