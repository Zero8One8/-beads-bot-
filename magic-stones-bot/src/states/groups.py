"""
Все FSM состояния бота.
"""
from aiogram.fsm.state import State, StatesGroup


class BaseInputStates(StatesGroup):
    waiting_name = State()
    waiting_emoji = State()
    waiting_description = State()
    waiting_price = State()
    waiting_photo = State()
    waiting_text = State()
    waiting_number = State()
    waiting_confirm = State()
    waiting_code = State()


class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()


class CustomOrderStates(StatesGroup):
    q1_purpose = State()
    q2_stones = State()
    q3_size = State()
    q4_notes = State()
    photo1 = State()
    photo2 = State()


class QuizStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


class TotemStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


class StoryStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()


class GiftStates(StatesGroup):
    waiting_amount = State()
    waiting_recipient = State()
    waiting_message = State()
    waiting_code = State()


class BookingStates(StatesGroup):
    selecting_service = State()
    selecting_date = State()
    selecting_time = State()
    entering_comment = State()
    confirming = State()


class AdminStates(StatesGroup):
    # Общие
    waiting_text = State()
    waiting_confirm = State()
    
    # Категории
    category_create_name = State()
    category_create_emoji = State()
    category_create_desc = State()
    category_edit = State()
    category_edit_field = State()
    
    # Браслеты
    bracelet_create_name = State()
    bracelet_create_price = State()
    bracelet_create_category = State()
    bracelet_create_desc = State()
    bracelet_create_photo = State()
    
    # Промокоды
    promo_create_type = State()
    promo_create_discount = State()
    promo_create_max_uses = State()
    promo_create_expires = State()
    promo_create_description = State()
    promo_create_code = State()
    promo_edit_field = State()
    promo_edit_value = State()
    
    # Расписание
    schedule_add_date = State()
    schedule_add_time = State()
    
    # Рассылки
    broadcast_text = State()
    broadcast_buttons = State()
    broadcast_button_text = State()
    broadcast_button_url = State()
    broadcast_audience = State()
    broadcast_confirm = State()
    
    # Диагностика (админ)
    diag_result = State()
    diag_service = State()
    
    # Клуб
    club_edit_info = State()
    club_extend_days = State()
    
    # Настройки
    settings_edit = State()
    settings_value = State()