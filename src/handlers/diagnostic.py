"""
Модуль диагностики - вход в целительские услуги.
Полностью перенесён из старого main.py.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel, DiagnosticModel
from src.keyboards.diagnostic import get_diagnostic_keyboard, get_diagnostic_admin_keyboard
from src.services.stars_payment import StarsPayment
from src.services.notifications import AdminNotifier
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()


@router.callback_query(F.data == "diagnostic")
async def diagnostic_start(callback: CallbackQuery, state: FSMContext):
    """Вход в диагностику."""
    user_id = callback.from_user.id
    
    # Проверяем, не проходил ли уже диагностику (можно пропускать, если хочет ещё)
    await callback.message.edit_text(
        "🔮 *ЭНЕРГЕТИЧЕСКАЯ ДИАГНОСТИКА*\n\n"
        "Это первый шаг к глубокой работе с вашим состоянием.\n"
        "На основе фото и ваших ощущений мастер определит:\n"
        "• Текущее состояние энергетики\n"
        "• Блоки и утечки\n"
        "• Рекомендации по услугам и камням\n\n"
        "💰 *Стоимость:* 3000⭐\n\n"
        "После оплаты вы сможете загрузить фото и оставить заметки.",
        reply_markup=get_diagnostic_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "diagnostic_pay")
async def diagnostic_pay(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Оплата диагностики через Stars."""
    await StarsPayment.create_invoice(
        bot=bot,
        user_id=callback.from_user.id,
        title="Энергетическая диагностика",
        description="Анализ состояния через камни и фото",
        payload=f"diagnostic_{callback.from_user.id}",
        amount_rub=3000
    )
    await callback.answer("💳 Счёт создан", show_alert=False)


@router.message(F.successful_payment)
async def diagnostic_paid(message: Message, state: FSMContext, bot: Bot):
    """Обработка успешной оплаты диагностики."""
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("diagnostic_"):
        user_id = int(payload.replace("diagnostic_", ""))
        if user_id != message.from_user.id:
            return
        
        await state.set_state(DiagnosticStates.waiting_photo1)
        
        # Сохраняем информацию о платеже
        with db.cursor() as c:
            c.execute("""
                INSERT INTO stars_orders (user_id, order_id, item_name, stars_amount, charge_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, 0, "Диагностика", message.successful_payment.total_amount,
                  message.successful_payment.telegram_payment_charge_id, datetime.now()))
        
        await message.answer(
            "📸 *ШАГ 1 ИЗ 3: ЗАГРУЗИТЕ ФОТО*\n\n"
            "Сделайте фотографию лица (крупный план)."
        )


@router.message(DiagnosticStates.waiting_photo1, F.photo)
async def diagnostic_photo1(message: Message, state: FSMContext):
    """Получение первого фото."""
    photo_id = message.photo[-1].file_id
    await state.update_data(photo1=photo_id)
    await state.set_state(DiagnosticStates.waiting_photo2)
    
    await message.answer(
        "📸 *ШАГ 2 ИЗ 3: ЗАГРУЗИТЕ ФОТО*\n\n"
        "Сделайте фотографию в полный рост.\n"
        "Или отправьте /skip, если нет возможности."
    )


@router.message(DiagnosticStates.waiting_photo2)
async def diagnostic_photo2(message: Message, state: FSMContext):
    """Получение второго фото (опционально)."""
    if message.photo:
        photo_id = message.photo[-1].file_id
        await state.update_data(photo2=photo_id)
    elif message.text == "/skip":
        await state.update_data(photo2=None)
    else:
        await message.answer("Пожалуйста, загрузите фото или отправьте /skip")
        return
    
    await state.set_state(DiagnosticStates.waiting_notes)
    await message.answer(
        "📝 *ШАГ 3 ИЗ 3: ОПИШИТЕ ВАШИ ОЩУЩЕНИЯ*\n\n"
        "Расскажите, что вас беспокоит, какие вопросы хотите решить.\n"
        "Чем подробнее, тем точнее будет диагностика."
    )


@router.message(DiagnosticStates.waiting_notes)
async def diagnostic_notes(message: Message, state: FSMContext, bot: Bot):
    """Сохранение заметок и отправка админу."""
    notes = message.text
    data = await state.get_data()
    user_id = message.from_user.id
    
    # Сохраняем в БД
    diag_id = DiagnosticModel.create(
        user_id=user_id,
        notes=notes,
        photo1=data['photo1'],
        photo2=data.get('photo2')
    )
    
    await state.clear()
    await message.answer(
        "✅ *ДИАГНОСТИКА ОТПРАВЛЕНА!*\n\n"
        "Мастер обработает её в течение 24 часов и пришлёт результат.\n"
        "Вы получите уведомление в этом чате."
    )
    
    # Уведомление админу
    await notify_admin_diagnostic(bot, user_id, diag_id, notes, data['photo1'], data.get('photo2'))


async def notify_admin_diagnostic(bot: Bot, user_id: int, diag_id: int, notes: str, photo1: str, photo2: str = None):
    """Уведомление админа о новой диагностике (из старого кода)."""
    user = UserModel.get(user_id)
    name = user['first_name'] or user['username'] or str(user_id)
    uname = f"@{user['username']}" if user.get('username') else "нет"
    
    text = (
        f"🩺 *НОВАЯ ДИАГНОСТИКА #{diag_id}*\n\n"
        f"👤 *Клиент:* {name} ({uname})\n"
        f"🆔 *ID:* {user_id}\n\n"
        f"📝 *Заметки:* {notes}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="📝 Ввести результат", callback_data=f"diag_result_{diag_id}")]
    ])
    
    await bot.send_message(Config.ADMIN_ID, text, reply_markup=kb)
    await bot.send_photo(Config.ADMIN_ID, photo1, caption="📸 Фото 1")
    if photo2:
        await bot.send_photo(Config.ADMIN_ID, photo2, caption="📸 Фото 2")


@router.callback_query(F.data.startswith("diag_result_"))
async def diagnostic_result_input(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Админ вводит результат диагностики."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    diag_id = int(callback.data.replace("diag_result_", ""))
    await state.update_data(diag_id=diag_id)
    await state.set_state("admin_diagnostic_result")
    
    await callback.message.edit_text(
        f"📝 *ВВЕДИТЕ РЕЗУЛЬТАТ ДИАГНОСТИКИ #{diag_id}*\n\n"
        f"Опишите результаты, рекомендации по услугам и камням.\n"
        f"Это сообщение будет отправлено клиенту."
    )
    await callback.answer()


@router.message(StateFilter("admin_diagnostic_result"))
async def diagnostic_result_save(message: Message, state: FSMContext, bot: Bot):
    """Сохранение результата и отправка клиенту."""
    data = await state.get_data()
    diag_id = data['diag_id']
    result_text = message.text
    
    # Получаем информацию о диагностике
    with db.cursor() as c:
        c.execute("SELECT user_id FROM diagnostics WHERE id = ?", (diag_id,))
        row = c.fetchone()
        if not row:
            await message.answer("❌ Диагностика не найдена")
            await state.clear()
            return
        user_id = row['user_id']
    
    # Обновляем статус
    DiagnosticModel.set_result(diag_id, result_text)
    
    # Отправляем клиенту
    await bot.send_message(
        user_id,
        f"🔮 *РЕЗУЛЬТАТ ВАШЕЙ ДИАГНОСТИКИ*\n\n{result_text}\n\n"
        f"Мастер готов предложить вам дальнейшие шаги. "
        f"Перейдите в раздел УСЛУГИ для записи.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ УСЛУГИ", callback_data="services")]
        ])
    )
    
    await state.clear()
    await message.answer("✅ Результат отправлен клиенту!")