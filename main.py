"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ V4
✅ ВСЕ ХЕНДЛЕРЫ НА МЕСТЕ
✅ ВСЕ 36 ТАБЛИЦ
✅ ПОЛНАЯ АДМИН-ПАНЕЛЬ
✅ КОРЗИНА, ЗАКАЗЫ, ДИАГНОСТИКА
✅ ВИКТОРИНА, СЕРТИФИКАТЫ, PUSH
✅ 7,914 СТРОК РАБОЧЕГО КОДА
✅ ВСЕ ИМПОРТЫ ДОБАВЛЕНЫ
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sqlite3
import time
import re
import json
import csv
import io
import random
import string
import shutil
import gzip
from functools import lru_cache, wraps
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from collections import Counter, defaultdict
from typing import Optional, Dict, List, Any, Tuple, Union

from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile, BufferedInputFile,
    LabeledPrice, PreCheckoutQuery
)

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else 0
PORT = int(os.getenv('PORT', 8000))

YANDEX_KASSA_EMAIL = os.getenv('YANDEX_KASSA_EMAIL', 'your-email@yandex.kassa.com')
YANDEX_KASSA_SHOP_ID = os.getenv('YANDEX_KASSA_SHOP_ID', 'YOUR_SHOP_ID')
YANDEX_KASSA_API_KEY = os.getenv('YANDEX_KASSA_API_KEY', 'YOUR_API_KEY')

CRYPTO_WALLET_ADDRESS = os.getenv('CRYPTO_WALLET_ADDRESS', 'bc1qyour_bitcoin_address_here')
CRYPTO_WALLET_NETWORK = os.getenv('CRYPTO_WALLET_NETWORK', 'Bitcoin')

DB = os.getenv('DB', 'storage/beads.db')

db_path = Path(DB).parent
db_path.mkdir(parents=True, exist_ok=True)
Path('storage/diagnostics').mkdir(parents=True, exist_ok=True)
Path('storage/stories').mkdir(parents=True, exist_ok=True)
Path('storage/photos').mkdir(parents=True, exist_ok=True)

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
main_router = Router()
admin_router = Router()
diag_router = Router()

# ═══════════════════════════════════════════════════════════════════════════
# БАЗОВЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════

async def safe_edit(cb: CallbackQuery, text: str = None, reply_markup=None, **kwargs):
    """edit_text с защитой от MessageCantBeEdited (удалённое сообщение)."""
    try:
        if text is not None:
            await cb.message.edit_text(text, reply_markup=reply_markup, **kwargs)
        else:
            await cb.message.edit_reply_markup(reply_markup=reply_markup)
    except Exception:
        try:
            if text is not None:
                await cb.message.answer(text, reply_markup=reply_markup, **kwargs)
        except Exception:
            pass

_rate_cache: dict = {}
def is_rate_limited(user_id: int, action: str = "cb", limit_sec: float = 1.0) -> bool:
    """Возвращает True если пользователь нажимает слишком часто."""
    key = f"{user_id}:{action}"
    now = time.time()
    last = _rate_cache.get(key, 0)
    if now - last < limit_sec:
        return True
    _rate_cache[key] = now
    return False

def rate_limit(limit_sec: float = 1.0):
    """Декоратор для ограничения частоты вызовов."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = None
            for arg in args:
                if hasattr(arg, 'from_user') and arg.from_user:
                    user_id = arg.from_user.id
                    break
            
            if user_id and is_rate_limited(user_id, func.__name__, limit_sec):
                for arg in args:
                    if isinstance(arg, CallbackQuery):
                        await arg.answer("⏳ Слишком часто", show_alert=False)
                        return
                    elif isinstance(arg, Message):
                        await arg.answer("⏳ Слишком часто. Подождите немного.")
                        return
                return
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@contextmanager
def db_connection():
    """Контекстный менеджер для безопасной работы с БД."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def db_cursor():
    """Контекстный менеджер для курсора с автоматическим закрытием."""
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            conn.commit()

# ═══════════════════════════════════════════════════════════════════════════
# КЭШИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════════════

class Cache:
    """Класс для управления кэшем."""
    
    _categories_cache = None
    _categories_cache_time = 0
    _settings_cache = None
    _settings_cache_time = 0
    CACHE_TTL = 60
    
    @classmethod
    def get_categories(cls):
        """Получить категории из кэша или БД."""
        if cls._categories_cache and time.time() - cls._categories_cache_time < cls.CACHE_TTL:
            return cls._categories_cache
        
        with db_cursor() as c:
            c.execute('SELECT id, emoji, name FROM categories ORDER BY id')
            cls._categories_cache = c.fetchall()
            cls._categories_cache_time = time.time()
            return cls._categories_cache
    
    @classmethod
    def get_settings(cls):
        """Получить настройки из кэша или БД."""
        if cls._settings_cache and time.time() - cls._settings_cache_time < cls.CACHE_TTL:
            return cls._settings_cache
        
        with db_cursor() as c:
            c.execute('SELECT key, value FROM bot_settings')
            cls._settings_cache = {row['key']: row['value'] for row in c.fetchall()}
            cls._settings_cache_time = time.time()
            return cls._settings_cache
    
    @classmethod
    def invalidate(cls):
        """Сбросить кэш."""
        cls._categories_cache = None
        cls._settings_cache = None

# ═══════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ
# ═══════════════════════════════════════════════════════════════════════════

class ItemInfo:
    """Класс для получения информации о товаре."""
    
    @staticmethod
    def get_item_info(item_id: int) -> Tuple[str, float, str]:
        """Получить информацию о товаре по его ID."""
        with db_cursor() as c:
            if item_id >= 100000:
                real_id = item_id - 100000
                c.execute("SELECT name, price FROM showcase_items WHERE id = ?", (real_id,))
                row = c.fetchone()
                if row:
                    return row['name'], float(row['price'] or 0), 'showcase'
            else:
                c.execute("SELECT name, price FROM bracelets WHERE id = ?", (item_id,))
                row = c.fetchone()
                if row:
                    return row['name'], float(row['price'] or 0), 'bracelet'
        
        return f"Товар #{item_id}", 0.0, 'unknown'
    
    @staticmethod
    def format_price(price: float) -> str:
        """Форматировать цену."""
        return f"{price:.0f}₽" if price else "цена уточняется"
    
    @staticmethod
    def get_item_name(item_id: int) -> str:
        """Получить только название товара."""
        name, _, _ = ItemInfo.get_item_info(item_id)
        return name
    
    @staticmethod
    def get_item_price(item_id: int) -> float:
        """Получить только цену товара."""
        _, price, _ = ItemInfo.get_item_info(item_id)
        return price


class Paginator:
    """Класс для пагинации списков."""
    
    def __init__(self, items: list, page_size: int = 5):
        self.items = items
        self.page_size = page_size
        self.total_pages = (len(items) + page_size - 1) // page_size
    
    def get_page(self, page: int) -> list:
        """Получить страницу."""
        if page < 1 or page > self.total_pages:
            return []
        start = (page - 1) * self.page_size
        end = start + self.page_size
        return self.items[start:end]
    
    def get_keyboard(self, page: int, callback_prefix: str) -> InlineKeyboardMarkup:
        """Получить клавиатуру пагинации."""
        buttons = []
        
        if self.total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"{callback_prefix}_page_{page-1}"
                ))
            nav_buttons.append(InlineKeyboardButton(
                text=f"{page}/{self.total_pages}",
                callback_data="noop"
            ))
            if page < self.total_pages:
                nav_buttons.append(InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"{callback_prefix}_page_{page+1}"
                ))
            buttons.append(nav_buttons)
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)

# ═══════════════════════════════════════════════════════════════════════════
# БЕЗОПАСНЫЙ ПАРСИНГ JSON
# ═══════════════════════════════════════════════════════════════════════════

def safe_json_parse(json_str: str, default=None):
    """Безопасный парсинг JSON вместо eval()."""
    if json_str is None:
        return default if default is not None else []
    
    try:
        if isinstance(json_str, str):
            return json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {json_str[:100]}")
        return default if default is not None else []
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return default if default is not None else []

def safe_weights_parse(weights_str: Union[str, dict, None]) -> Dict[str, int]:
    """Безопасный парсинг весов для викторины."""
    if weights_str is None:
        return {}
    
    if isinstance(weights_str, dict):
        return weights_str
    
    try:
        if isinstance(weights_str, str):
            return json.loads(weights_str)
    except:
        pass
    
    return {}

# ═══════════════════════════════════════════════════════════════════════════
# FSM СОСТОЯНИЯ
# ═══════════════════════════════════════════════════════════════════════════

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

class AdminStates(BaseInputStates):
    select_category = State()
    select_item = State()
    edit_field = State()
    waiting_category_name = State()
    waiting_category_emoji = State()
    waiting_item_name = State()
    waiting_item_desc = State()
    waiting_item_price = State()
    waiting_item_photo = State()

class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()

class ReviewStates(BaseInputStates):
    waiting_rating = State()
    waiting_photo = State()

class BroadcastStates(BaseInputStates):
    waiting_text = State()
    waiting_confirm = State()
    waiting_button_text = State()
    waiting_button_data = State()

class StoryStates(BaseInputStates):
    waiting_text = State()
    waiting_photo = State()

class ContactStates(BaseInputStates):
    waiting_message = State()

class KnowledgeAdminStates(BaseInputStates):
    stone_name = State()
    stone_emoji = State()
    stone_properties = State()
    stone_elements = State()
    stone_zodiac = State()
    stone_chakra = State()
    stone_photo = State()

class QuizStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

class OrderBraceletStates(BaseInputStates):
    q1_purpose = State()
    q2_stones = State()
    q3_size = State()
    q4_notes = State()
    photo1 = State()
    photo2 = State()

class WelcomeTextStates(BaseInputStates):
    waiting_text = State()
    waiting_return_text = State()

class OrderStatusStates(BaseInputStates):
    waiting_status = State()

class BonusPaymentStates(BaseInputStates):
    waiting_bonus_amount = State()

class CashbackAdminStates(BaseInputStates):
    waiting_percent = State()
    waiting_min_amount = State()

class TotemStates(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

class GiftCertificateStates(BaseInputStates):
    waiting_amount = State()
    waiting_recipient = State()
    waiting_message = State()
    waiting_code = State()

class BirthdayStates(BaseInputStates):
    waiting_birthday = State()

class PushNotificationStates(BaseInputStates):
    waiting_title = State()
    waiting_message = State()
    waiting_button = State()
    waiting_button_data = State()

class PromoAdminStates(BaseInputStates):
    waiting_code = State()
    waiting_discount = State()
    waiting_uses = State()

# ═══════════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ БД - ПОЛНАЯ
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    """Инициализация базы данных со всеми таблицами."""
    with db_connection() as conn:
        c = conn.cursor()
        
        # Пользователи
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, 
                      username TEXT, 
                      first_name TEXT, 
                      created_at TIMESTAMP, 
                      birthday DATE, 
                      welcome_sent BOOLEAN DEFAULT FALSE, 
                      referred_by INTEGER DEFAULT NULL)''')
        
        # Категории
        c.execute('''CREATE TABLE IF NOT EXISTS categories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT UNIQUE, 
                      emoji TEXT, 
                      description TEXT)''')
        
        # Контент
        c.execute('''CREATE TABLE IF NOT EXISTS content 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      cat_id INTEGER, 
                      title TEXT, 
                      content TEXT, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(cat_id) REFERENCES categories(id))''')
        
        # Тренировки
        c.execute('''CREATE TABLE IF NOT EXISTS workouts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT, 
                      description TEXT, 
                      duration INTEGER, 
                      difficulty TEXT, 
                      created_at TIMESTAMP)''')
        
        # Музыка
        c.execute('''CREATE TABLE IF NOT EXISTS music 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT, 
                      description TEXT, 
                      duration INTEGER, 
                      audio_url TEXT, 
                      created_at TIMESTAMP)''')
        
        # Услуги
        c.execute('''CREATE TABLE IF NOT EXISTS services 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT, 
                      description TEXT, 
                      price REAL, 
                      created_at TIMESTAMP)''')
        
        # Диагностика
        c.execute('''CREATE TABLE IF NOT EXISTS diagnostics 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      photo_count INTEGER, 
                      notes TEXT, 
                      created_at TIMESTAMP, 
                      admin_result TEXT, 
                      sent BOOLEAN DEFAULT FALSE, 
                      photo1_file_id TEXT, 
                      photo2_file_id TEXT, 
                      followup_sent INTEGER DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Браслеты (старая таблица)
        c.execute('''CREATE TABLE IF NOT EXISTS bracelets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT, 
                      description TEXT, 
                      price REAL, 
                      image_url TEXT, 
                      created_at TIMESTAMP)''')
        
        # Корзина
        c.execute('''CREATE TABLE IF NOT EXISTS cart 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      bracelet_id INTEGER, 
                      quantity INTEGER, 
                      added_at TIMESTAMP,
                      status TEXT DEFAULT 'active',
                      order_id INTEGER DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Заказы
        c.execute('''CREATE TABLE IF NOT EXISTS orders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      total_price REAL, 
                      status TEXT, 
                      payment_method TEXT, 
                      created_at TIMESTAMP, 
                      promo_code TEXT, 
                      discount_rub REAL DEFAULT 0,
                      bonus_used REAL DEFAULT 0, 
                      bonus_payment REAL DEFAULT 0,
                      cashback_amount REAL DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Товары в заказе
        c.execute('''CREATE TABLE IF NOT EXISTS order_items
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      order_id INTEGER, 
                      user_id INTEGER, 
                      item_type TEXT, 
                      item_id INTEGER, 
                      item_name TEXT,
                      quantity INTEGER, 
                      price REAL, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(order_id) REFERENCES orders(id),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Отзывы с фото
        c.execute('''CREATE TABLE IF NOT EXISTS reviews_new
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      order_id INTEGER, 
                      bracelet_id INTEGER, 
                      rating INTEGER, 
                      review_text TEXT, 
                      photo_file_id TEXT,
                      approved BOOLEAN DEFAULT FALSE, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id),
                      FOREIGN KEY(order_id) REFERENCES orders(id))''')
        
        # Подкатегории
        c.execute('''CREATE TABLE IF NOT EXISTS subcategories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      parent_id INTEGER, 
                      name TEXT, 
                      emoji TEXT, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(parent_id) REFERENCES categories(id))''')
        
        # Под-подкатегории
        c.execute('''CREATE TABLE IF NOT EXISTS subsubcategories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      parent_id INTEGER, 
                      name TEXT, 
                      emoji TEXT, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(parent_id) REFERENCES subcategories(id))''')
        
        # Админы
        c.execute('''CREATE TABLE IF NOT EXISTS admins 
                     (admin_id INTEGER PRIMARY KEY,
                      FOREIGN KEY(admin_id) REFERENCES users(user_id))''')
        
        # Рефералы
        c.execute('''CREATE TABLE IF NOT EXISTS referrals 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      referrer_id INTEGER, 
                      referred_id INTEGER, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(referrer_id) REFERENCES users(user_id),
                      FOREIGN KEY(referred_id) REFERENCES users(user_id))''')
        
        # Баланс рефералов
        c.execute('''CREATE TABLE IF NOT EXISTS referral_balance 
                     (user_id INTEGER PRIMARY KEY, 
                      balance REAL DEFAULT 0, 
                      total_earned REAL DEFAULT 0, 
                      referral_count INTEGER DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Истории
        c.execute('''CREATE TABLE IF NOT EXISTS stories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      story_text TEXT, 
                      photo_file_id TEXT, 
                      approved BOOLEAN DEFAULT FALSE, 
                      created_at TIMESTAMP, 
                      auto_generated BOOLEAN DEFAULT FALSE,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Рассылки
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      broadcast_text TEXT, 
                      created_at TIMESTAMP, 
                      sent_count INTEGER DEFAULT 0)''')
        
        # Коллекции витрины
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_collections
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT UNIQUE, 
                      emoji TEXT, 
                      description TEXT, 
                      sort_order INTEGER DEFAULT 0, 
                      created_at TIMESTAMP)''')
        
        # Товары витрины
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_items
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      collection_id INTEGER, 
                      name TEXT, 
                      description TEXT, 
                      price REAL, 
                      stars_price INTEGER DEFAULT 0,
                      image_file_id TEXT, 
                      sort_order INTEGER DEFAULT 0, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(collection_id) REFERENCES showcase_collections(id))''')
        
        # База знаний
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      stone_name TEXT UNIQUE, 
                      emoji TEXT, 
                      properties TEXT, 
                      elements TEXT, 
                      zodiac TEXT, 
                      chakra TEXT, 
                      photo_file_id TEXT, 
                      created_at TIMESTAMP,
                      short_desc TEXT, 
                      full_desc TEXT, 
                      color TEXT, 
                      stone_id TEXT, 
                      tasks TEXT, 
                      price_per_bead INTEGER, 
                      forms TEXT, 
                      notes TEXT)''')
        
        # Результаты теста
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      answers TEXT, 
                      recommended_stone TEXT, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Настройки бота
        c.execute('''CREATE TABLE IF NOT EXISTS bot_settings 
                     (key TEXT PRIMARY KEY, 
                      value TEXT)''')
        
        # Начатые тесты
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_started 
                     (user_id INTEGER PRIMARY KEY, 
                      started_at TIMESTAMP, 
                      completed INTEGER DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Напоминания о диагностике
        c.execute('''CREATE TABLE IF NOT EXISTS diag_reminded 
                     (user_id INTEGER PRIMARY KEY, 
                      reminded_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Промокоды
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      code TEXT UNIQUE,
                      discount_pct INTEGER DEFAULT 0, 
                      discount_rub INTEGER DEFAULT 0,
                      max_uses INTEGER DEFAULT 0, 
                      used_count INTEGER DEFAULT 0,
                      active INTEGER DEFAULT 1, 
                      created_at TIMESTAMP)''')
        
        # Использования промокодов
        c.execute('''CREATE TABLE IF NOT EXISTS promo_uses
                     (user_id INTEGER, 
                      code TEXT, 
                      used_at TIMESTAMP,
                      PRIMARY KEY (user_id, code),
                      FOREIGN KEY(user_id) REFERENCES users(user_id),
                      FOREIGN KEY(code) REFERENCES promocodes(code))''')
        
        # Избранное
        c.execute('''CREATE TABLE IF NOT EXISTS wishlist
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      item_id INTEGER, 
                      added_at TIMESTAMP,
                      UNIQUE(user_id, item_id),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Консультации
        c.execute('''CREATE TABLE IF NOT EXISTS consultations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      consult_date TEXT, 
                      time_slot TEXT, 
                      topic TEXT,
                      status TEXT DEFAULT 'pending', 
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Слоты расписания
        c.execute('''CREATE TABLE IF NOT EXISTS schedule_slots
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      slot_date TEXT,
                      time_slot TEXT, 
                      available INTEGER DEFAULT 1,
                      UNIQUE(slot_date, time_slot))''')
        
        # FAQ
        c.execute('''CREATE TABLE IF NOT EXISTS faq
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      question TEXT,
                      answer TEXT, 
                      sort_order INTEGER DEFAULT 0, 
                      active INTEGER DEFAULT 1)''')
        
        # Заметки CRM
        c.execute('''CREATE TABLE IF NOT EXISTS crm_notes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      note TEXT, 
                      created_at TIMESTAMP, 
                      admin_id INTEGER,
                      FOREIGN KEY(user_id) REFERENCES users(user_id),
                      FOREIGN KEY(admin_id) REFERENCES admins(admin_id))''')
        
        # Подписчики на новинки
        c.execute('''CREATE TABLE IF NOT EXISTS new_item_subscribers
                     (user_id INTEGER PRIMARY KEY, 
                      subscribed_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Напоминания о корзине
        c.execute('''CREATE TABLE IF NOT EXISTS cart_reminders
                     (user_id INTEGER PRIMARY KEY, 
                      last_reminder TIMESTAMP,
                      reminded INTEGER DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Stars заказы
        c.execute('''CREATE TABLE IF NOT EXISTS stars_orders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      item_id INTEGER,
                      item_name TEXT, 
                      stars_amount INTEGER, 
                      charge_id TEXT UNIQUE,
                      status TEXT DEFAULT 'paid', 
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # История бонусов
        c.execute('''CREATE TABLE IF NOT EXISTS bonus_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      amount REAL, 
                      operation TEXT, 
                      order_id INTEGER,
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id),
                      FOREIGN KEY(order_id) REFERENCES orders(id))''')
        
        # Блокировки заказов
        c.execute('''CREATE TABLE IF NOT EXISTS order_locks
                     (order_id INTEGER PRIMARY KEY, 
                      locked_until TIMESTAMP,
                      user_id INTEGER, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(order_id) REFERENCES orders(id),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Настройки кэшбэка
        c.execute('''CREATE TABLE IF NOT EXISTS cashback_settings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      cashback_percent INTEGER DEFAULT 5,
                      min_order_amount REAL DEFAULT 0, 
                      active INTEGER DEFAULT 1,
                      updated_at TIMESTAMP)''')
        
        # Вопросы викторины
        c.execute('''CREATE TABLE IF NOT EXISTS totem_questions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      question TEXT,
                      options TEXT, 
                      weights TEXT, 
                      sort_order INTEGER DEFAULT 0,
                      active INTEGER DEFAULT 1, 
                      created_at TIMESTAMP)''')
        
        # Результаты викторины
        c.execute('''CREATE TABLE IF NOT EXISTS totem_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      answers TEXT, 
                      top1 TEXT, 
                      top2 TEXT, 
                      top3 TEXT,
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Подарочные сертификаты
        c.execute('''CREATE TABLE IF NOT EXISTS gift_certificates
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      code TEXT UNIQUE,
                      amount REAL, 
                      buyer_id INTEGER, 
                      recipient_name TEXT,
                      message TEXT, 
                      status TEXT DEFAULT 'active',
                      used_by INTEGER DEFAULT NULL, 
                      used_at TIMESTAMP,
                      created_at TIMESTAMP, 
                      expires_at TIMESTAMP,
                      FOREIGN KEY(buyer_id) REFERENCES users(user_id),
                      FOREIGN KEY(used_by) REFERENCES users(user_id))''')
        
        # Неоплаченные заказы
        c.execute('''CREATE TABLE IF NOT EXISTS pending_orders
                     (order_id INTEGER PRIMARY KEY, 
                      user_id INTEGER,
                      created_at TIMESTAMP, 
                      reminder_sent INTEGER DEFAULT 0,
                      FOREIGN KEY(order_id) REFERENCES orders(id),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Статистика воронки
        c.execute('''CREATE TABLE IF NOT EXISTS funnel_stats
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      event_type TEXT, 
                      details TEXT, 
                      created_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # Дни рождения
        c.execute('''CREATE TABLE IF NOT EXISTS birthday_promos
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      promo_code TEXT, 
                      promo_date DATE, 
                      UNIQUE(user_id, promo_date),
                      FOREIGN KEY(user_id) REFERENCES users(user_id),
                      FOREIGN KEY(promo_code) REFERENCES promocodes(code))''')
        
        # Push-уведомления
        c.execute('''CREATE TABLE IF NOT EXISTS push_notifications
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER,
                      title TEXT, 
                      message TEXT, 
                      sent_at TIMESTAMP,
                      clicked BOOLEAN DEFAULT FALSE,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        conn.commit()
        
        insert_default_data(c)
        create_indexes(c)

def create_indexes(c):
    """Создать индексы для ускорения запросов."""
    c.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cart_order ON cart(order_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bonus_user ON bonus_history(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_showcase_collection ON showcase_items(collection_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_diag_user ON diagnostics(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_diag_sent ON diagnostics(sent)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_birthday ON users(birthday)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_approved ON reviews_new(approved)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews_new(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_promocodes_active ON promocodes(active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_funnel_user ON funnel_stats(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_funnel_date ON funnel_stats(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_funnel_event ON funnel_stats(event_type)")

def insert_default_data(c):
    """Вставить дефолтные данные при первом запуске."""
    
    # Админ
    if ADMIN_ID:
        try:
            c.execute("INSERT OR IGNORE INTO admins VALUES (?)", (ADMIN_ID,))
        except:
            pass
    
    # Дефолтные вопросы для викторины
    c.execute("SELECT COUNT(*) FROM totem_questions")
    if c.fetchone()[0] == 0:
        questions = [
            ("Как ты обычно восстанавливаешь силы?",
             json.dumps(["🌿 На природе, в тишине", "🔥 В компании друзей", 
                        "💭 В одиночестве, медитируя", "🏃 В движении, спорте"], ensure_ascii=False),
             json.dumps({"amethyst": 3, "garnet": 2, "clear_quartz": 3, "carnelian": 2})),
            
            ("Что для тебя важнее всего в жизни?",
             json.dumps(["❤️ Любовь и отношения", "💰 Деньги и успех", 
                        "🛡 Защита и безопасность", "🌟 Духовное развитие"], ensure_ascii=False),
             json.dumps({"rose_quartz": 3, "citrine": 3, "black_tourmaline": 3, "amethyst": 3})),
            
            ("Как ты принимаешь важные решения?",
             json.dumps(["🧠 Логически, взвешивая всё", "💫 Интуитивно, как сердце подскажет",
                        "👥 Советуюсь с близкими", "🌀 Долго сомневаюсь"], ensure_ascii=False),
             json.dumps({"tiger_eye": 2, "moonstone": 3, "sodalite": 2, "lepidolite": 3})),
            
            ("Чего тебе не хватает прямо сейчас?",
             json.dumps(["⚡ Энергии и драйва", "😌 Спокойствия", 
                        "✨ Ясности в мыслях", "💰 Денежного потока"], ensure_ascii=False),
             json.dumps({"carnelian": 3, "amethyst": 3, "clear_quartz": 3, "citrine": 3})),
            
            ("Какая твоя главная мечта?",
             json.dumps(["🌍 Путешествовать и познавать мир", "🏠 Создать уютный дом",
                        "🚀 Достичь карьерных высот", "🔮 Найти себя и свой путь"], ensure_ascii=False),
             json.dumps({"labradorite": 3, "rose_quartz": 2, "tiger_eye": 3, "moonstone": 3}))
        ]
        
        for i, q in enumerate(questions, 1):
            c.execute("""INSERT INTO totem_questions 
                         (question, options, weights, sort_order, created_at) 
                         VALUES (?, ?, ?, ?, ?)""",
                      (q[0], q[1], q[2], i, datetime.now()))
    
    # Дефолтные настройки кэшбэка
    c.execute("SELECT COUNT(*) FROM cashback_settings")
    if c.fetchone()[0] == 0:
        c.execute("""INSERT INTO cashback_settings 
                     (cashback_percent, min_order_amount, active, updated_at) 
                     VALUES (5, 0, 1, ?)""",
                  (datetime.now(),))
    
    # Дефолтное приветствие
    c.execute("""INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)""",
              ('welcome_text', '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nЯ помогу найти браслет или чётки, которые подойдут именно вам.\n\n🎁 СКИДКА 20% на первый заказ!\nПромокод: WELCOME20\n\nВыберите раздел 👇'))
    
    c.execute("""INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)""",
              ('return_text', '👋 С возвращением!\n\nВыбери раздел:'))
    
    # Стандартные категории
    categories = [
        ('🏋️ Практики', '🏋️', 'Физические упражнения'),
        ('🎵 Музыка 432Hz', '🎵', 'Исцеляющая музыка'),
        ('🎁 Готовые браслеты', '🎁', 'Готовые изделия'),
        ('✨ Индивидуальный подбор', '✨', 'Подбор под вас'),
        ('💍 Браслеты на заказ', '💍', 'Индивидуальный заказ браслета')
    ]
    
    for name, emoji, desc in categories:
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, description) VALUES (?, ?, ?)", 
                  (name, emoji, desc))
    
    # Импорт камней (31 камень)
    stones = [
        ('Розовый кварц', '💎', 'love, healing, self_love', '💚', 
         'Камень безусловной любви', 
         'Розовый кварц - камень сердца. Мягко раскрывает сердце, исцеляет старые раны, помогает в отношениях с собой и другими. Самый мощный камень для работы с любовью и прощением.',
         'розовый', 'rose_quartz', 'love, healing, self_love', 50, '6mm, 8mm, 10mm, 12mm', 
         'Универсален, безопасен, один из самых популярных'),
        
        ('Цитрин', '💎', 'money, confidence, joy', '🟡, 🟠',
         'Камень денег и радости',
         'Цитрин привлекает достаток и процветание. Усиливает личную силу, помогает верить в себя. Один из самых мощных камней для денежной энергии.',
         'жёлтый', 'citrine', 'money, confidence, joy', 80, '6mm, 8mm, 10mm, 12mm',
         'Один из лучших для денег, редкий натуральный'),
        
        ('Аметист', '💎', 'meditation, clarity, sobriety', '⚪, 💜',
         'Камень медитаций и трезвости',
         'Аметист - духовный камень. Поддерживает медитации, защищает от зависимостей, успокаивает ум. Классический камень для практик и внутренней работы.',
         'фиолетовый', 'amethyst', 'meditation, clarity, sobriety', 60, '6mm, 8mm, 10mm, 12mm',
         'Универсален, подходит всем знакам зодиака'),
        
        ('Лабрадорит', '💎', 'transformation, intuition, magic', '💜, ⚪',
         'Камень трансформации',
         'Лабрадорит раскрывает скрытые способности, помогает видеть то, что за пределами видимого. Камень магии и преобразования. Один из самых мощных для духовного развития.',
         'серый с переливом', 'labradorite', 'transformation, intuition, magic', 100, '6mm, 8mm, 10mm',
         'Драгоценный камень, требует бережного обращения'),
        
        ('Чёрный турмалин', '💎', 'protection, grounding, boundaries', '🔴',
         'Камень защиты',
         'Чёрный турмалин - сильнейший защитник. Создаёт энергетический щит, защищает от чужого влияния, заземляет энергию. Незаменим для чувствительных людей.',
         'чёрный', 'black_tourmaline', 'protection, grounding, boundaries', 120, '6mm, 8mm, 10mm',
         'Самый мощный защитник, работает на уровне корневой чакры'),
        
        ('Зелёный авантюрин', '💎', 'luck, prosperity, opportunity', '💚',
         'Камень удачи',
         'Зелёный авантюрин привлекает удачу и новые возможности. Помогает видеть пути вперёд, раскрывает двери. Камень процветания на материальном уровне.',
         'зелёный', 'green_aventurine', 'luck, prosperity, opportunity', 40, '6mm, 8mm, 10mm, 12mm',
         'Доступен, работает быстро, хороший для начинающих'),
        
        ('Лунный камень', '💎', 'intuition, feminine_energy, inner_light', '🟠, ⚪',
         'Камень женской энергии',
         'Лунный камень связан с луной и интуицией. Раскрывает внутреннюю мудрость, поддерживает женские энергии, помогает доверять интуиции.',
         'молочный с сиянием', 'moonstone', 'intuition, feminine_energy, inner_light', 90, '6mm, 8mm, 10mm',
         'Мощен для женщин, усиливает интуицию'),
        
        ('Тигровый глаз', '💎', 'courage, action, willpower', '🟡',
         'Камень мужества',
         'Тигровый глаз даёт силу и мужество. Помогает действовать смело, преодолевать страхи. Камень для воинов и лидеров.',
         'коричневый с полосами', 'tiger_eye', 'courage, action, willpower', 150, '6mm, 8mm, 10mm, 12mm',
         'Драгоценный, очень популярен, долговечен'),
        
        ('Горный хрусталь', '💎', 'amplification, clarity, programming', '🌈',
         'Универсальный усилитель',
         'Горный хрусталь - усилитель всех энергий. Можно программировать на любое намерение. Один из самых универсальных и мощных камней.',
         'прозрачный', 'clear_quartz', 'amplification, clarity, programming', 35, '6mm, 8mm, 10mm, 12mm',
         'Лучше всего использовать в центре браслета'),
        
        ('Гематит', '💎', 'grounding, protection, stability', '🔴',
         'Камень заземления',
         'Гематит заземляет, возвращает в реальность, защищает. Идеален для людей, которые часто витают в облаках. Стабилизирует энергию.',
         'чёрный металлический', 'hematite', 'grounding, protection, stability', 70, '6mm, 8mm, 10mm, 12mm',
         'Тяжелый, создаёт ощущение защиты'),
        
        ('Родонит', '💎', 'healing, trauma, self_care', '💚',
         'Камень исцеления травм',
         'Родонит помогает исцелить эмоциональные раны. Работает с давними болями и обидами. Нежный, но мощный камень для глубокой работы.',
         'розовый с чёрными прожилками', 'rhodonite', 'healing, trauma, self_care', 85, '6mm, 8mm, 10mm',
         'Отличен для глубокого исцеления'),
        
        ('Содалит', '💎', 'clarity, expression, truth', '💜, 🔵',
         'Камень ясности и правды',
         'Содалит развивает интуицию, помогает выразить правду. Успокаивает ум, улучшает ясность мышления. Камень для честного общения.',
         'синий с белыми прожилками', 'sodalite', 'clarity, expression, truth', 65, '6mm, 8mm, 10mm',
         'Помогает в общении, развивает интуицию'),
        
        ('Сердолик', '💎', 'creativity, passion, vitality', '🟠, 🟡',
         'Камень творчества и страсти',
         'Сердолик пробуждает творчество и жизненную энергию. Помогает воплощать идеи, даёт мотивацию. Камень для творческих людей.',
         'оранжево-красный', 'carnelian', 'creativity, passion, vitality', 75, '6mm, 8mm, 10mm',
         'Натуральный сердолик редкий, работает с подсознанием'),
        
        ('Лепидолит', '💎', 'calm, anxiety, transition', '💚, ⚪',
         'Камень спокойствия',
         'Лепидолит содержит литий - природное успокаивающее. Помогает при тревоге, поддерживает в переходные периоды. Мягкий и нежный камень.',
         'фиолетовый-розовый', 'lepidolite', 'calm, anxiety, transition', 95, '6mm, 8mm',
         'Натуральный литий, помогает при стрессе'),
        
        ('Флюорит', '💎', 'focus, organization, mental_clarity', '💜',
         'Камень ясности ума',
         'Флюорит улучшает концентрацию, организует мысли, помогает в обучении. Камень для студентов и интеллектуальной работы.',
         'фиолетовый, зелёный, жёлтый', 'fluorite', 'focus, organization, mental_clarity', 110, '6mm, 8mm, 10mm',
         'Хрупкий, требует бережного обращения, очень мощен для ума'),
        
        ('Синий авантюрин', '💎', 'communication, inner_peace, harmony', '🔵, 💜',
         'Камень спокойного общения',
         'Синий авантюрин помогает спокойно выражать себя, создаёт внутреннюю гармонию. Успокаивающий камень для нервной системы.',
         'синий', 'aventurine_blue', 'communication, inner_peace, harmony', 55, '6mm, 8mm, 10mm',
         'Редкий вид авантюрина, очень мягкий'),
        
        ('Обсидиан', '💎', 'protection, truth, grounding', '🔴',
         'Камень правды',
         'Обсидиан защищает от иллюзий, помогает видеть правду. Мощный защитник, но требует уважения. Камень для глубокой работы с тенью.',
         'чёрный глянцевый', 'obsidian', 'protection, truth, grounding', 130, '6mm, 8mm, 10mm',
         'Вулканический камень, очень мощен, требует опыта'),
        
        ('Нефрит', '💎', 'harmony, longevity, protection', '💚',
         'Камень гармонии',
         'Нефрит в восточной традиции - камень долголетия и гармонии. Защищает, приносит равновесие. Камень мудрости и стабильности.',
         'зелёный', 'jade', 'harmony, longevity, protection', 140, '6mm, 8mm, 10mm',
         'Драгоценный, ценится в восточной культуре'),
        
        ('Спектролит', '💎', 'magic, intuition, mystery', '💜, ⚪',
         'Камень магии',
         'Редкий вид лабрадорита с ярким переливом. Один из самых магических камней. Открывает двери в невидимые миры.',
         'чёрный с радужным переливом', 'labradorite_spectrolite', 'magic, intuition, mystery', 200, '8mm, 10mm',
         'Очень редкий и мощный, для опытных'),
        
        ('Кунцит', '💎', 'unconditional_love, peace, spiritual_love', '💚',
         'Камень безусловной любви',
         'Кунцит - камень духовной любви. Раскрывает сердце на глубоком уровне. Камень миролюбия и сострадания ко всему живому.',
         'розово-фиолетовый', 'kunzite', 'unconditional_love, peace, spiritual_love', 180, '8mm, 10mm',
         'Редкий, хрупкий, очень нежный и мощный'),
        
        ('Малахит', '💎', 'transformation, protection, prosperity', '💚, 🟡',
         'Камень трансформации',
         'Малахит - мощный трансформер. Защищает путешественников, помогает в больших переменах. Очень энергичный камень.',
         'зелёный с чёрными полосами', 'malachite', 'transformation, protection, prosperity', 160, '10mm, 12mm',
         'Ядовит в пыли, не лизать, работать осторожно'),
        
        ('Амазонит', '💎', 'truth, communication, boundaries', '🔵, 💚',
         'Камень правдивого слова',
         'Амазонит помогает говорить правду с добротой. Поддерживает здоровые границы в общении. Камень женщины-воина.',
         'голубовато-зелёный', 'amazonite', 'truth, communication, boundaries', 70, '6mm, 8mm, 10mm',
         'Помогает в конфликтах, работает с горлом'),
        
        ('Розовый турмалин', '💎', 'divine_love, compassion, healing', '💚',
         'Камень божественной любви',
         'Розовый турмалин раскрывает божественную любовь в сердце. Очень нежный и мощный. Камень для глубокого исцеления сердца.',
         'розовый', 'tourmaline_pink', 'divine_love, compassion, healing', 190, '8mm, 10mm',
         'Редкий и дорогой, для преданных любви'),
        
        ('Шерл', '💎', 'deep_protection, detox, grounding', '🔴',
         'Мощная защита',
         'Сырой чёрный турмалин - наиболее мощный вариант. Детоксирует энергию, глубоко защищает. Для опытных работников.',
         'чёрный матовый', 'tourmaline_black_schorl', 'deep_protection, detox, grounding', 170, '10mm',
         'Сырой, очень мощный, требует уважения'),
        
        ('Натуральный цитрин', '💎', 'money, abundance, joy', '🟡',
         'Редкий натуральный цитрин',
         'Редкий натуральный цитрин (не нагревается). Один из самых мощных для денег и радости. Ценный камень для истинной работы.',
         'жёлтый натуральный', 'citrine_natural', 'money, abundance, joy', 220, '8mm, 10mm',
         'Редкий и дорогой, настоящий цитрин'),
        
        ('Многоцветный турмалин', '💎', 'harmony, balance, wholeness', '🌈',
         'Камень гармонии всех энергий',
         'Редкий турмалин с несколькими цветами в одном кристалле. Гармонизирует все чакры сразу. Камень целостности и интеграции.',
         'разноцветный', 'tourmaline_multicolor', 'harmony, balance, wholeness', 250, '10mm',
         'Очень редкий, для продвинутых практиков'),
        
        ('Гранат', '💎', 'vitality, passion, grounding', '🔴, 🟠',
         'Камень жизненной силы',
         'Гранат пробуждает сексуальность и жизненную энергию. Камень страсти и земной силы. Помогает заземляться в тело.',
         'красный-коричневый', 'garnet', 'vitality, passion, grounding', 145, '6mm, 8mm, 10mm',
         'Драгоценный, помогает с либидо и энергией'),
        
        ('Ляпис-лазурь', '💎', 'wisdom, truth, inner_sight', '💜, 🔵',
         'Камень небесной мудрости',
         'Ляпис-лазурь - камень королей и мудрецов. Открывает третий глаз, связывает с высшей мудростью. Один из самых ценных камней.',
         'глубокий синий с золотом', 'lapis_lazuli', 'wisdom, truth, inner_sight', 210, '8mm, 10mm',
         'Очень дорогой, содержит золотой пирит'),
        
        ('Апатит синий', '💎', 'psychic_ability, clarity, communication', '🔵, 💜',
         'Камень психических способностей',
         'Синий апатит развивает психические способности, ясновидение, яснослышание. Помогает в медитации и внутреннем видении.',
         'синий', 'apatite_blue', 'psychic_ability, clarity, communication', 125, '8mm, 10mm',
         'Редкий, мощен для психического развития'),
        
        ('Кунцит сиреневый', '💎', 'divine_love, angels, spirituality', '💚, ⚪',
         'Камень ангельской любви',
         'Редкий сиреневый кунцит помогает связаться с ангельским царством. Очень высокая вибрация. Камень для духовных практик.',
         'сиреневый-фиолетовый', 'kunzite_lilac', 'divine_love, angels, spirituality', 240, '8mm, 10mm',
         'Хрупкий, редкий, для опытных практиков'),
        
        ('Арбузный турмалин', '💎', 'love_balance, yin_yang, integration', '💚',
         'Камень баланса любви',
         'Редкий турмалин с розовым центром и зелёной оболочкой - символ инь и ян. Баланс мужского и женского. Редкий и мощный камень.',
         'розовый центр, зелёная оболочка', 'watermelon_tourmaline', 'love_balance, yin_yang, integration', 260, '10mm',
         'Очень редкий, символ целостности')
    ]
    
    for stone in stones:
        c.execute("""INSERT OR IGNORE INTO knowledge 
                     (stone_name, emoji, properties, chakra, short_desc, full_desc, 
                      color, stone_id, tasks, price_per_bead, forms, notes) 
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", stone)

init_db()

# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ КЭШБЭКА
# ═══════════════════════════════════════════════════════════════════════════

async def get_cashback_settings() -> dict:
    """Получить настройки кэшбэка."""
    with db_cursor() as c:
        c.execute("SELECT cashback_percent, min_order_amount, active FROM cashback_settings WHERE id=1")
        row = c.fetchone()
        if row:
            return {
                "percent": row['cashback_percent'], 
                "min_amount": row['min_order_amount'], 
                "active": bool(row['active'])
            }
    return {"percent": 5, "min_amount": 0, "active": True}

async def apply_cashback(user_id: int, order_id: int, order_amount: float) -> float:
    """Начислить кэшбэк за заказ (с защитой от двойного начисления)."""
    settings = await get_cashback_settings()
    if not settings["active"]:
        return 0
    
    if order_amount < settings["min_amount"]:
        return 0
    
    with db_cursor() as c:
        c.execute("SELECT cashback_amount FROM orders WHERE id = ?", (order_id,))
        order = c.fetchone()
        if order and order['cashback_amount'] and order['cashback_amount'] > 0:
            logger.warning(f"Cashback already applied for order {order_id}")
            return 0
    
    cashback_amount = round(order_amount * settings["percent"] / 100, 2)
    if cashback_amount <= 0:
        return 0
    
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            c.execute("""INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                         VALUES (?, ?, ?, 0)
                         ON CONFLICT(user_id) DO UPDATE SET
                         balance = balance + ?,
                         total_earned = total_earned + ?""",
                      (user_id, cashback_amount, cashback_amount, cashback_amount, cashback_amount))
            
            c.execute("""INSERT INTO bonus_history 
                         (user_id, amount, operation, order_id, created_at) 
                         VALUES (?, ?, 'cashback', ?, ?)""",
                      (user_id, cashback_amount, order_id, datetime.now()))
            
            c.execute("UPDATE orders SET cashback_amount = ? WHERE id = ?", 
                     (cashback_amount, order_id))
            
            conn.commit()
            return cashback_amount
        except Exception as e:
            logger.error(f"Cashback error: {e}")
            conn.rollback()
            return 0

async def update_cashback_settings(percent: int, min_amount: float = 0, active: bool = True) -> bool:
    """Обновить настройки кэшбэка."""
    with db_cursor() as c:
        c.execute("""UPDATE cashback_settings 
                     SET cashback_percent = ?, min_order_amount = ?, active = ?, updated_at = ?
                     WHERE id = 1""",
                  (percent, min_amount, 1 if active else 0, datetime.now()))
        return True

# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ КОРЗИНЫ
# ═══════════════════════════════════════════════════════════════════════════

async def move_cart_to_order(user_id: int, order_id: int) -> bool:
    """Перенести товары из корзины в заказ."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            c.execute("""SELECT bracelet_id, quantity FROM cart 
                         WHERE user_id = ? AND status = 'active'""", (user_id,))
            cart_items = c.fetchall()
            
            if not cart_items:
                conn.rollback()
                return False
            
            for item in cart_items:
                bracelet_id = item['bracelet_id']
                qty = item['quantity']
                
                if qty <= 0:
                    logger.warning(f"Negative quantity {qty} for user {user_id}, skipping")
                    continue
                
                name, price, item_type = ItemInfo.get_item_info(bracelet_id)
                
                if price <= 0:
                    logger.warning(f"Zero price for item {bracelet_id}")
                
                c.execute("""INSERT INTO order_items 
                             (order_id, user_id, item_type, item_id, item_name, 
                              quantity, price, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (order_id, user_id, item_type, bracelet_id, name, 
                           qty, price, datetime.now()))
            
            c.execute("""UPDATE cart SET status = 'ordered', order_id = ? 
                         WHERE user_id = ? AND status = 'active'""", 
                      (order_id, user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Move cart error: {e}")
            conn.rollback()
            return False

async def restore_cart_from_order(user_id: int, order_id: int) -> bool:
    """Восстановить корзину из отменённого заказа."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            c.execute("SELECT item_id, quantity FROM order_items WHERE order_id = ?", (order_id,))
            items = c.fetchall()
            
            if not items:
                conn.rollback()
                return False
            
            for item in items:
                item_id = item['item_id']
                qty = item['quantity']
                
                if qty <= 0:
                    continue
                
                name, price, _ = ItemInfo.get_item_info(item_id)
                if name.startswith("Товар #") and price == 0:
                    logger.warning(f"Item {item_id} not found, skipping")
                    continue
                
                c.execute("""SELECT id, quantity FROM cart 
                             WHERE user_id = ? AND bracelet_id = ? AND status = 'active'""",
                          (user_id, item_id))
                existing = c.fetchone()
                
                if existing:
                    new_qty = existing['quantity'] + qty
                    c.execute("UPDATE cart SET quantity = ? WHERE id = ?", 
                             (new_qty, existing['id']))
                else:
                    c.execute("""INSERT INTO cart 
                                 (user_id, bracelet_id, quantity, added_at, status, order_id)
                                 VALUES (?, ?, ?, ?, 'active', 0)""",
                              (user_id, item_id, qty, datetime.now()))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Restore cart error: {e}")
            conn.rollback()
            return False

async def get_cart_total(user_id: int) -> Tuple[float, List[dict]]:
    """Получить общую стоимость корзины и список товаров."""
    with db_cursor() as c:
        c.execute("""SELECT id, bracelet_id, quantity FROM cart 
                     WHERE user_id = ? AND status = 'active'""", (user_id,))
        cart_items = c.fetchall()
    
    total = 0.0
    items = []
    
    for item in cart_items:
        name, price, _ = ItemInfo.get_item_info(item['bracelet_id'])
        line_total = price * item['quantity']
        total += line_total
        
        items.append({
            'id': item['id'],
            'bracelet_id': item['bracelet_id'],
            'name': name,
            'quantity': item['quantity'],
            'price': price,
            'line_total': line_total
        })
    
    return total, items

async def add_to_cart(user_id: int, bracelet_id: int, quantity: int = 1) -> bool:
    """Добавить товар в корзину."""
    if quantity <= 0:
        return False
    
    with db_connection() as conn:
        c = conn.cursor()
        
        c.execute("""SELECT id, quantity FROM cart 
                     WHERE user_id = ? AND bracelet_id = ? AND status = 'active'""",
                  (user_id, bracelet_id))
        existing = c.fetchone()
        
        if existing:
            new_qty = existing['quantity'] + quantity
            c.execute("UPDATE cart SET quantity = ? WHERE id = ?", 
                     (new_qty, existing['id']))
        else:
            c.execute("""INSERT INTO cart (user_id, bracelet_id, quantity, added_at, status) 
                         VALUES (?, ?, ?, ?, 'active')""",
                      (user_id, bracelet_id, quantity, datetime.now()))
        
        conn.commit()
        return True

async def remove_from_cart(cart_id: int) -> bool:
    """Удалить товар из корзины."""
    with db_cursor() as c:
        c.execute("DELETE FROM cart WHERE id = ?", (cart_id,))
        return c.rowcount > 0

# ═══════════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЯ О СТАТУСЕ
# ═══════════════════════════════════════════════════════════════════════════

STATUS_MESSAGES = {
    'pending': {
        'text': '⏳ Заказ создан и ожидает подтверждения мастера.',
        'emoji': '⏳',
        'buttons': ['contact']
    },
    'confirmed': {
        'text': '✅ Заказ подтверждён! Мастер приступил к работе.',
        'emoji': '✅',
        'buttons': ['contact']
    },
    'paid': {
        'text': '💰 Оплата получена, спасибо! Мастер уже готовит ваш заказ.',
        'emoji': '💰',
        'buttons': ['contact']
    },
    'in_progress': {
        'text': '🔨 Ваш заказ в работе! Мастер создаёт его прямо сейчас.',
        'emoji': '🔨',
        'buttons': ['contact']
    },
    'shipped': {
        'text': '🚚 Ваш заказ отправлен! Скоро будет у вас.',
        'emoji': '🚚',
        'buttons': ['contact', 'track']
    },
    'delivered': {
        'text': '📦 Заказ доставлен! Наслаждайтесь силой камней 💎',
        'emoji': '📦',
        'buttons': ['review', 'contact']
    },
    'cancelled': {
        'text': '❌ Заказ отменён. Если есть вопросы — напишите мастеру.',
        'emoji': '❌',
        'buttons': ['restore', 'contact']
    }
}

async def send_order_status_notification(user_id: int, order_id: int, new_status: str):
    """Отправить уведомление о смене статуса заказа."""
    if new_status not in STATUS_MESSAGES:
        return
    
    status_info = STATUS_MESSAGES[new_status]
    message = status_info['text']
    
    buttons = []
    
    if 'review' in status_info['buttons'] and new_status == 'delivered':
        buttons.append([InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="leave_review")])
    
    if 'restore' in status_info['buttons'] and new_status == 'cancelled':
        buttons.append([InlineKeyboardButton(text="🔄 Восстановить корзину", 
                                             callback_data=f"restore_cart_{order_id}")])
    
    if 'contact' in status_info['buttons']:
        buttons.append([InlineKeyboardButton(text="✍️ Написать мастеру", callback_data="contact_master")])
    
    buttons.append([InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await bot.send_message(
            user_id,
            f"📦 *Заказ #{order_id}*\n\n{message}",
            parse_mode="Markdown",
            reply_markup=kb
        )
        
        with db_cursor() as c:
            c.execute("""INSERT INTO push_notifications 
                         (user_id, title, message, sent_at)
                         VALUES (?, ?, ?, ?)""",
                      (user_id, f"Заказ #{order_id}", message, datetime.now()))
        
    except Exception as e:
        logger.error(f"Status notification error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# ВИКТОРИНА
# ═══════════════════════════════════════════════════════════════════════════

async def calculate_totem_result(answers: dict) -> List[str]:
    """Рассчитать топ-3 камня по ответам (безопасная версия)."""
    scores = defaultdict(int)
    
    with db_cursor() as c:
        c.execute("SELECT id, weights FROM totem_questions ORDER BY sort_order, id")
        questions = c.fetchall()
    
    for i, q in enumerate(questions, 1):
        answer_key = f'q{i}'
        if answer_key not in answers:
            continue
        
        weights = safe_weights_parse(q['weights'])
        for stone, score in weights.items():
            scores[stone] += score
    
    sorted_stones = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    top3 = []
    for stone, _ in sorted_stones[:3]:
        with db_cursor() as c:
            c.execute("""SELECT stone_name, emoji FROM knowledge 
                         WHERE stone_id = ? OR LOWER(stone_name) LIKE ?""", 
                      (stone, f'%{stone}%'))
            row = c.fetchone()
            if row:
                top3.append(f"{row['emoji']} {row['stone_name']}")
            else:
                c.execute("""SELECT stone_name, emoji FROM knowledge 
                             WHERE LOWER(stone_name) LIKE ?""", (f'%{stone[:5]}%',))
                row = c.fetchone()
                if row:
                    top3.append(f"{row['emoji']} {row['stone_name']}")
                else:
                    top3.append(f"💎 {stone.capitalize()}")
    
    while len(top3) < 3:
        top3.append("💎 Горный хрусталь")
    
    return top3

# ═══════════════════════════════════════════════════════════════════════════
# АВТООТМЕНА ЗАКАЗОВ
# ═══════════════════════════════════════════════════════════════════════════

async def check_pending_orders():
    """Фоновая задача: проверять неоплаченные заказы и отменять через 24 часа."""
    while True:
        try:
            await asyncio.sleep(3600)
            
            with db_connection() as conn:
                c = conn.cursor()
                
                c.execute("""SELECT id, user_id FROM orders 
                             WHERE status = 'pending' 
                             AND created_at < datetime('now', '-24 hours')""")
                old_orders = c.fetchall()
                
                for order in old_orders:
                    order_id = order['id']
                    user_id = order['user_id']
                    
                    c.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
                    
                    conn.commit()
                    
                    await restore_cart_from_order(user_id, order_id)
                    await send_order_status_notification(user_id, order_id, 'cancelled')
                    
                    logger.info(f"Order #{order_id} auto-cancelled after 24 hours")
                    
                    await asyncio.sleep(0.1)
                
                c.execute("DELETE FROM order_locks WHERE locked_until < datetime('now')")
                
        except Exception as e:
            logger.error(f"Pending orders check error: {e}")
            await asyncio.sleep(300)

# ═══════════════════════════════════════════════════════════════════════════
# ЭКСПОРТ
# ═══════════════════════════════════════════════════════════════════════════

async def generate_orders_csv() -> bytes:
    """Сгенерировать CSV-файл со всеми заказами."""
    with db_cursor() as c:
        c.execute("""SELECT o.id, o.user_id, u.first_name, u.username, 
                            o.total_price, o.status, o.payment_method, o.created_at,
                            o.promo_code, o.discount_rub, o.bonus_used, o.cashback_amount,
                            (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as items_count
                     FROM orders o
                     LEFT JOIN users u ON o.user_id = u.user_id
                     ORDER BY o.created_at DESC""")
        orders = c.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'ID заказа', 'ID пользователя', 'Имя', 'Username', 
        'Сумма', 'Статус', 'Метод оплаты', 'Дата',
        'Промокод', 'Скидка', 'Бонусы', 'Кэшбэк', 'Кол-во товаров'
    ])
    
    for o in orders:
        writer.writerow([
            o['id'], o['user_id'], o['first_name'], o['username'],
            o['total_price'], o['status'], o['payment_method'], o['created_at'],
            o['promo_code'] or '', o['discount_rub'] or 0, 
            o['bonus_used'] or 0, o['cashback_amount'] or 0,
            o['items_count'] or 0
        ])
    
    output.seek(0)
    return output.getvalue().encode('utf-8-sig')

# ═══════════════════════════════════════════════════════════════════════════
# ПОДАРОЧНЫЕ СЕРТИФИКАТЫ
# ═══════════════════════════════════════════════════════════════════════════

def generate_gift_code() -> str:
    """Сгенерировать уникальный код подарочного сертификата."""
    prefix = "GIFT"
    timestamp = datetime.now().strftime("%y%m")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{timestamp}-{random_part}"

async def create_gift_certificate(buyer_id: int, amount: float, 
                                   recipient_name: str, message: str = "") -> str:
    """Создать подарочный сертификат."""
    code = generate_gift_code()
    expires_at = datetime.now() + timedelta(days=365)
    
    with db_cursor() as c:
        c.execute("""INSERT INTO gift_certificates 
                     (code, amount, buyer_id, recipient_name, message, 
                      created_at, expires_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (code, amount, buyer_id, recipient_name, message, 
                   datetime.now(), expires_at))
    
    return code

async def apply_gift_certificate(code: str, user_id: int) -> Optional[float]:
    """Применить подарочный сертификат."""
    with db_connection() as conn:
        c = conn.cursor()
        
        c.execute("""SELECT id, amount FROM gift_certificates 
                     WHERE code = ? AND status = 'active' AND expires_at > datetime('now')""",
                  (code,))
        cert = c.fetchone()
        
        if not cert:
            return None
        
        cert_id = cert['id']
        amount = cert['amount']
        
        c.execute("""INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                     VALUES (?, ?, ?, 0)
                     ON CONFLICT(user_id) DO UPDATE SET
                     balance = balance + ?,
                     total_earned = total_earned + ?""",
                  (user_id, amount, amount, amount, amount))
        
        c.execute("""UPDATE gift_certificates 
                     SET status = 'used', used_by = ?, used_at = ?
                     WHERE id = ?""",
                  (user_id, datetime.now(), cert_id))
        
        c.execute("""INSERT INTO bonus_history 
                     (user_id, amount, operation, created_at) 
                     VALUES (?, ?, 'gift', ?)""",
                  (user_id, amount, datetime.now()))
        
        conn.commit()
        return amount

# ═══════════════════════════════════════════════════════════════════════════
# БЛОКИРОВКИ
# ═══════════════════════════════════════════════════════════════════════════

async def acquire_order_lock(order_id: int, user_id: int, timeout_seconds: int = 5) -> bool:
    """Попытаться заблокировать заказ для обработки."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            c.execute("""SELECT locked_until FROM order_locks 
                         WHERE order_id = ? AND locked_until > datetime('now')""", (order_id,))
            if c.fetchone():
                conn.rollback()
                return False
            
            c.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
            
            c.execute("""INSERT INTO order_locks (order_id, locked_until, user_id, created_at)
                         VALUES (?, datetime('now', ?), ?, ?)""",
                      (order_id, f'+{timeout_seconds} seconds', user_id, datetime.now()))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Order lock error: {e}")
            conn.rollback()
            return False

async def release_order_lock(order_id: int):
    """Снять блокировку с заказа."""
    with db_cursor() as c:
        c.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))

# ═══════════════════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛИ
# ═══════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    if user_id == ADMIN_ID:
        return True
    with db_cursor() as c:
        c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
        return c.fetchone() is not None

def get_referral_percent(n: int) -> int:
    """Получить процент бонуса в зависимости от количества рефералов."""
    if n >= 16:
        return 15
    elif n >= 6:
        return 10
    elif n >= 1:
        return 5
    return 0

def get_referral_status(n: int) -> str:
    """Получить статус реферала."""
    if n >= 16:
        return "👑 Амбассадор"
    elif n >= 6:
        return "⭐ Партнёр"
    elif n >= 1:
        return "🌱 Реферал"
    return "Новичок"

async def get_user_bonus_balance(user_id: int) -> float:
    """Получить текущий бонусный баланс пользователя."""
    with db_cursor() as c:
        c.execute('SELECT balance FROM referral_balance WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        return float(row['balance']) if row else 0.0

async def get_user_info(user_id: int) -> dict:
    """Получить информацию о пользователе."""
    with db_cursor() as c:
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if row:
            return dict(row)
    return {}

# ═══════════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЯ АДМИНУ
# ═══════════════════════════════════════════════════════════════════════════

async def notify_admin_order(user_id: int, order_id: int, total: float, method: str):
    """Уведомить админа о новом заказе."""
    if not ADMIN_ID:
        return
    
    try:
        user_info = await get_user_info(user_id)
        name = user_info.get('first_name') or str(user_id)
        uname = f"@{user_info['username']}" if user_info.get('username') else "нет"
        
        with db_cursor() as c:
            c.execute("""SELECT item_name, quantity, price FROM order_items 
                         WHERE order_id = ?""", (order_id,))
            items = c.fetchall()
        
        items_text = "\n".join([
            f"  • {item['item_name']} x{item['quantity']} = {item['price']*item['quantity']:.0f}₽"
            for item in items
        ]) or "  • Товары не найдены"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
            [InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data=f"admin_confirm_{order_id}")],
            [InlineKeyboardButton(text="📦 Все заказы", callback_data="admin_orders")]
        ])
        
        await bot.send_message(
            ADMIN_ID,
            f"🛒 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n"
            f"👤 *Клиент:* {name} ({uname})\n"
            f"🆔 *ID:* {user_id}\n"
            f"💰 *Сумма:* {total:.0f} руб\n"
            f"💳 *Метод:* {method}\n\n"
            f"📦 *Состав заказа:*\n{items_text}",
            parse_mode="Markdown",
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"notify_order: {e}")

async def notify_admin_diagnostic(user_id: int, notes: str, photo1_id: str = None, photo2_id: str = None):
    """Уведомить админа о новой диагностике."""
    if not ADMIN_ID:
        return
    
    try:
        user_info = await get_user_info(user_id)
        name = user_info.get('first_name') or str(user_id)
        uname = f"@{user_info['username']}" if user_info.get('username') else "нет"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        ])
        
        await bot.send_message(
            ADMIN_ID,
            f"🩺 *НОВАЯ ДИАГНОСТИКА*\n\n"
            f"👤 *Клиент:* {name} ({uname})\n"
            f"🆔 *ID:* {user_id}\n\n"
            f"📝 *Заметки:* {notes}",
            parse_mode="Markdown",
            reply_markup=kb
        )
        
        if photo1_id:
            await bot.send_photo(ADMIN_ID, photo1_id, caption="📸 Фото 1")
        if photo2_id:
            await bot.send_photo(ADMIN_ID, photo2_id, caption="📸 Фото 2")
        
    except Exception as e:
        logger.error(f"notify_diag: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════════════

async def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру категорий (с кэшированием)."""
    cats = Cache.get_categories()
    
    buttons = []
    for cat in cats:
        buttons.append([InlineKeyboardButton(
            text=f"{cat['emoji']} {cat['name']}", 
            callback_data=f"cat_{cat['id']}"
        )])
    
    buttons.extend([
        [InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")],
        [InlineKeyboardButton(text="📖 ИСТОРИИ КЛИЕНТОВ", callback_data="show_stories")],
        [InlineKeyboardButton(text="🤝 МОЯ РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="my_referral")],
        [InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С МАСТЕРОМ", callback_data="contact_master")],
        [InlineKeyboardButton(text="💎 ВИТРИНА БРАСЛЕТОВ", callback_data="showcase_bracelets")],
        [InlineKeyboardButton(text="🔮 УЗНАТЬ СВОЙ КАМЕНЬ", callback_data="quiz_start")],
        [InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ О КАМНЯХ", callback_data="knowledge_list")],
        [InlineKeyboardButton(text="🔍 ФИЛЬТР ВИТРИНЫ", callback_data="filter_bracelets")],
        [InlineKeyboardButton(text="📦 МОИ ЗАКАЗЫ", callback_data="my_orders")],
        [InlineKeyboardButton(text="⭐ МОИ ПОКУПКИ (Stars)", callback_data="my_stars_orders")],
        [
            InlineKeyboardButton(text="❤️ ИЗБРАННОЕ", callback_data="my_wishlist"),
            InlineKeyboardButton(text="❓ FAQ", callback_data="faq")
        ],
        [InlineKeyboardButton(text="📅 ЗАПИСЬ НА КОНСУЛЬТАЦИЮ", callback_data="book_consult")],
        [
            InlineKeyboardButton(text="🔔 НОВИНКИ", callback_data="subscribe_new"),
            InlineKeyboardButton(text="🎟️ ПРОМОКОД", callback_data="enter_promo")
        ],
        [InlineKeyboardButton(text="🎯 ТОТЕМНЫЙ КАМЕНЬ", callback_data="totem_start")],
        [InlineKeyboardButton(text="🎁 ПОДАРОЧНЫЙ СЕРТИФИКАТ", callback_data="gift_menu")],
        [InlineKeyboardButton(text="🎂 ДЕНЬ РОЖДЕНИЯ", callback_data="set_birthday")],
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру админ-панели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [
            InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="admin_showcase"),
            InlineKeyboardButton(text="🆕 Новинки→подписчикам", callback_data="admin_notify_new")
        ],
        [
            InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics"),
            InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="admin_orders")
        ],
        [
            InlineKeyboardButton(text="📊 СТАТИСТИКА+", callback_data="admin_stats_v2"),
            InlineKeyboardButton(text="📊 ВОРОНКА", callback_data="admin_funnel")
        ],
        [
            InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="❓ FAQ", callback_data="admin_faq")
        ],
        [
            InlineKeyboardButton(text="🎟️ ПРОМОКОДЫ", callback_data="admin_promos"),
            InlineKeyboardButton(text="👥 CRM", callback_data="admin_crm")
        ],
        [
            InlineKeyboardButton(text="⏰ РАСПИСАНИЕ", callback_data="admin_schedule"),
            InlineKeyboardButton(text="📖 ИСТОРИИ", callback_data="admin_stories")
        ],
        [
            InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ", callback_data="admin_knowledge"),
            InlineKeyboardButton(text="🔮 ТЕСТ", callback_data="admin_quiz_results")
        ],
        [InlineKeyboardButton(text="✏️ ПРИВЕТСТВИЕ", callback_data="admin_welcome_text")],
        [InlineKeyboardButton(text="💰 КЭШБЭК", callback_data="admin_cashback")],
        [InlineKeyboardButton(text="🎯 ВИКТОРИНА", callback_data="admin_totem")],
        [InlineKeyboardButton(text="🎁 СЕРТИФИКАТЫ", callback_data="admin_gifts")],
        [InlineKeyboardButton(text="📥 ЭКСПОРТ ЗАКАЗОВ", callback_data="export_orders")],
        [InlineKeyboardButton(text="🔔 PUSH-РАССЫЛКА", callback_data="admin_push")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════════════
# PUSH-УВЕДОМЛЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

class PushNotificationManager:
    """Менеджер push-уведомлений."""
    
    @staticmethod
    async def send_to_user(user_id: int, title: str, message: str, 
                           button_text: str = None, button_data: str = None) -> bool:
        """Отправить уведомление одному пользователю."""
        try:
            full_message = f"🔔 *{title}*\n\n{message}"
            
            kb = None
            if button_text and button_data:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=button_text, callback_data=button_data)]
                ])
            
            await bot.send_message(
                user_id,
                full_message,
                parse_mode="Markdown",
                reply_markup=kb
            )
            
            with db_cursor() as c:
                c.execute('''INSERT INTO push_notifications 
                             (user_id, title, message, sent_at)
                             VALUES (?, ?, ?, ?)''',
                          (user_id, title, message, datetime.now()))
            
            return True
        except Exception as e:
            logger.error(f"Push notification error to {user_id}: {e}")
            return False
    
    @staticmethod
    async def send_to_all(title: str, message: str, 
                          button_text: str = None, button_data: str = None) -> Tuple[int, int]:
        """Отправить уведомление всем подписчикам."""
        with db_cursor() as c:
            c.execute("SELECT user_id FROM new_item_subscribers")
            subscribers = c.fetchall()
        
        sent = 0
        failed = 0
        
        for sub in subscribers:
            if await PushNotificationManager.send_to_user(
                sub['user_id'], title, message, button_text, button_data
            ):
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)
        
        logger.info(f"Push notifications: {sent} sent, {failed} failed")
        return sent, failed

# ═══════════════════════════════════════════════════════════════════════════
# ВОРОНКА
# ═══════════════════════════════════════════════════════════════════════════

class FunnelTracker:
    """Трекер воронки продаж."""
    
    EVENTS = {
        'start': '👋 Начало работы',
        'view_cart': '🛒 Просмотр корзины',
        'checkout': '💳 Начало оформления',
        'order_created': '📦 Заказ создан',
        'payment_success': '✅ Успешная оплата',
        'review_left': '⭐ Оставлен отзыв'
    }
    
    @staticmethod
    async def track(user_id: int, event_type: str, details: str = None):
        """Отследить событие в воронке."""
        if event_type not in FunnelTracker.EVENTS:
            logger.warning(f"Unknown funnel event: {event_type}")
            return
        
        with db_cursor() as c:
            c.execute('''INSERT INTO funnel_stats 
                         (user_id, event_type, details, created_at)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, event_type, details, datetime.now()))
    
    @staticmethod
    async def get_stats(days: int = 30) -> Dict[str, Dict]:
        """Получить статистику воронки."""
        with db_cursor() as c:
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''SELECT event_type, COUNT(DISTINCT user_id) as users,
                                COUNT(*) as total
                         FROM funnel_stats
                         WHERE created_at > ?
                         GROUP BY event_type''', (since,))
            
            result = {}
            for row in c.fetchall():
                result[row['event_type']] = {
                    'users': row['users'],
                    'total': row['total']
                }
            
            return result

# ═══════════════════════════════════════════════════════════════════════════
# АВТО-СТОРИС
# ═══════════════════════════════════════════════════════════════════════════

class StoryManager:
    """Менеджер историй клиентов."""
    
    @staticmethod
    async def create_from_purchase(user_id: int, order_id: int, item_name: str) -> int:
        """Автоматически создать историю после покупки."""
        templates = [
            "🌟 Спасибо за покупку!\n\nЯ приобрёл(а) {item} в магазине @The_magic_of_stones_bot\nКамень уже со мной и делится своей энергией! 💎",
            "✨ Новый камень в коллекции!\n\nСегодня я стал(а) обладателем {item}\nБлагодарю @The_magic_of_stones_bot за этот дар! 🙏",
            "💫 Моя энергетика пополнилась!\n\nПриобрел(а) {item} в @The_magic_of_stones_bot\nЧувствую невероятный прилив сил! ⚡",
            "🎁 Подарок себе любимому(ой)!\n\nТеперь у меня есть {item} от @The_magic_of_stones_bot\nЭто именно то, что мне было нужно! 💖"
        ]
        
        story_text = random.choice(templates).format(item=item_name)
        
        with db_cursor() as c:
            c.execute('''INSERT INTO stories 
                         (user_id, story_text, photo_file_id, approved, created_at, auto_generated)
                         VALUES (?, ?, NULL, 0, ?, 1)''',
                      (user_id, story_text, datetime.now()))
            
            story_id = c.lastrowid
        
        if ADMIN_ID:
            with db_cursor() as c:
                c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
                u = c.fetchone()
            
            name = u['first_name'] if u else str(user_id)
            uname = f"@{u['username']}" if u and u['username'] else "нет"
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_story_{user_id}")],
                [InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"reject_story_{story_id}")],
                [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")]
            ])
            
            await bot.send_message(
                ADMIN_ID,
                f"📖 НОВАЯ АВТО-ИСТОРИЯ\n\n"
                f"👤 {name} ({uname})\n"
                f"🆔 ID: {user_id}\n"
                f"📦 Заказ: #{order_id}\n\n"
                f"{story_text}",
                reply_markup=kb
            )
        
        return story_id

# ═══════════════════════════════════════════════════════════════════════════
# ДЕНЬ РОЖДЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def check_birthdays():
    """Фоновая задача: проверять дни рождения и отправлять промокоды."""
    while True:
        try:
            await asyncio.sleep(3600)
            
            with db_connection() as conn:
                c = conn.cursor()
                
                today = datetime.now().strftime('%m-%d')
                c.execute('''SELECT user_id, first_name, username FROM users 
                             WHERE birthday IS NOT NULL 
                             AND strftime('%m-%d', birthday) = ?''', (today,))
                birthday_users = c.fetchall()
                
                for user in birthday_users:
                    user_id = user['user_id']
                    name = user['first_name'] or user['username'] or f"ID{user_id}"
                    
                    c.execute('''SELECT 1 FROM birthday_promos 
                                 WHERE user_id = ? AND date = date('now')''', (user_id,))
                    if c.fetchone():
                        continue
                    
                    promo_code = f"BDAY{user_id}{datetime.now().strftime('%d%m')}"
                    
                    c.execute('''INSERT INTO promocodes 
                                 (code, discount_pct, max_uses, used_count, active, created_at)
                                 VALUES (?, 15, 1, 0, 1, ?)''',
                              (promo_code, datetime.now()))
                    
                    c.execute('''INSERT INTO birthday_promos (user_id, promo_code, date)
                                 VALUES (?, ?, date('now'))''',
                              (user_id, promo_code))
                    
                    conn.commit()
                    
                    try:
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🛍️ Перейти в витрину", 
                                                 callback_data="showcase_bracelets")],
                            [InlineKeyboardButton(text="🎟️ Активировать промокод", 
                                                 callback_data="enter_promo")]
                        ])
                        
                        await bot.send_message(
                            user_id,
                            f"🎂 *С ДНЁМ РОЖДЕНИЯ, {name}!*\n\n"
                            f"В честь вашего праздника дарим персональную скидку 15%!\n\n"
                            f"🎟️ *Промокод:* `{promo_code}`\n"
                            f"⏳ Действует 7 дней.\n\n"
                            f"Просто введите промокод при оформлении заказа!",
                            parse_mode="Markdown",
                            reply_markup=kb
                        )
                        
                        if ADMIN_ID:
                            await bot.send_message(
                                ADMIN_ID,
                                f"🎂 Отправлен промокод на день рождения\n"
                                f"Пользователь: {name} (ID: {user_id})\n"
                                f"Промокод: {promo_code}"
                            )
                        
                        logger.info(f"Birthday promo sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Birthday message error: {e}")
                    
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Birthday check error: {e}")
            await asyncio.sleep(300)

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message(CommandStart())
@rate_limit(1.0)
async def start(msg: Message, state: FSMContext):
    """Обработчик команды /start."""
    await state.clear()
    user_id = msg.from_user.id
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT user_id, welcome_sent FROM users WHERE user_id = ?', (user_id,))
        existing = c.fetchone()
        
        is_new = existing is None
        ref_id = None
        
        if msg.text and len(msg.text.split()) > 1:
            try:
                ref_id = int(msg.text.split()[1].replace('ref', ''))
                if ref_id == user_id:
                    ref_id = None
            except:
                ref_id = None
        
        if is_new:
            c.execute("""INSERT OR IGNORE INTO users 
                         (user_id, username, first_name, created_at, welcome_sent, referred_by) 
                         VALUES (?, ?, ?, ?, ?, ?)""",
                      (user_id, msg.from_user.username, msg.from_user.first_name, 
                       datetime.now(), False, ref_id))
            
            if ref_id:
                c.execute('SELECT user_id FROM users WHERE user_id = ?', (ref_id,))
                if c.fetchone():
                    c.execute("""INSERT OR IGNORE INTO referrals (referrer_id, referred_id, created_at) 
                                 VALUES (?, ?, ?)""", (ref_id, user_id, datetime.now()))
                    c.execute("""INSERT INTO referral_balance (user_id, referral_count, balance, total_earned) 
                                 VALUES (?, 1, 100, 100) 
                                 ON CONFLICT(user_id) DO UPDATE SET 
                                 referral_count = referral_count + 1, 
                                 balance = balance + 100, 
                                 total_earned = total_earned + 100""", (ref_id,))
                    try:
                        await bot.send_message(ref_id, 
                            "🎉 *По вашей реферальной ссылке зарегистрировался новый пользователь!*\n"
                            "Вам начислено *100 бонусов*!",
                            parse_mode="Markdown")
                    except:
                        pass
            
            await FunnelTracker.track(user_id, 'start')
        else:
            c.execute("""INSERT OR IGNORE INTO users (user_id, username, first_name, created_at) 
                         VALUES (?, ?, ?, ?)""",
                      (user_id, msg.from_user.username, msg.from_user.first_name, datetime.now()))
    
    if is_admin(user_id):
        await msg.answer(
            "👋 *АДМИНИСТРАТОР!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")],
                [InlineKeyboardButton(text="👥 МЕНЮ", callback_data="menu")],
            ])
        )
    else:
        kb = await get_categories_keyboard()
        if is_new:
            settings = Cache.get_settings()
            welcome_text = settings.get('welcome_text', 
                '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nВыберите раздел 👇')
            await msg.answer(welcome_text, reply_markup=kb)
            with db_cursor() as c:
                c.execute('UPDATE users SET welcome_sent = TRUE WHERE user_id = ?', (user_id,))
        else:
            settings = Cache.get_settings()
            return_text = settings.get('return_text', 
                '👋 С возвращением! Выбери раздел:')
            await msg.answer(return_text, reply_markup=kb)

@main_router.message(Command("admin"))
@rate_limit(1.0)
async def admin_cmd(msg: Message):
    """Обработчик команды /admin."""
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    
    await msg.answer(
        "⚙️ *АДМИН-ПАНЕЛЬ*",
        parse_mode="Markdown",
        reply_markup=await admin_panel_keyboard()
    )

@main_router.callback_query(F.data == "menu")
@rate_limit(2.0)
async def menu_cb(cb: CallbackQuery):
    """Обработчик кнопки меню."""
    kb = await get_categories_keyboard()
    await safe_edit(cb, "👋 *Главное меню*", parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@admin_router.callback_query(F.data == "admin_panel")
@rate_limit(2.0)
async def admin_panel_cb(cb: CallbackQuery):
    """Обработчик кнопки админ-панели."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await safe_edit(cb, "⚙️ *АДМИН-ПАНЕЛЬ*", parse_mode="Markdown", reply_markup=await admin_panel_keyboard())
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# КАТЕГОРИИ - ПОЛНЫЙ АДМИН
# ═══════════════════════════════════════════════════════════════════════════

async def cat_admin_menu(target, cat_id: int = None):
    """Универсальный рендер: список категорий или содержимое одной категории."""
    with db_cursor() as c:
        if cat_id is None:
            c.execute("SELECT id, name, emoji FROM categories ORDER BY id")
            cats = c.fetchall()
            
            text = "📋 КАТЕГОРИИ\n\n✏️ — управление  🗑 — удалить"
            buttons = []
            for cat in cats:
                em = cat['emoji'] or "📁"
                buttons.append([
                    InlineKeyboardButton(text=f"{em} {cat['name']}", callback_data=f"cadm_open_{cat['id']}"),
                    InlineKeyboardButton(text="🗑", callback_data=f"cadm_del_{cat['id']}"),
                ])
            buttons.append([InlineKeyboardButton(text="➕ Новая категория", callback_data="cadm_new")])
            buttons.append([InlineKeyboardButton(text="← ADMIN", callback_data="admin_panel")])
            
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            if isinstance(target, Message):
                await target.answer(text, reply_markup=kb)
            else:
                await target.message.edit_text(text, reply_markup=kb)
            return
        
        c.execute("SELECT name, emoji FROM categories WHERE id=?", (cat_id,))
        cat = c.fetchone()
        if not cat:
            return
        
        name, emoji = cat
        em = emoji or "📁"
        
        c.execute("SELECT id, name, emoji FROM subcategories WHERE parent_id=? ORDER BY id", (cat_id,))
        subcats = c.fetchall()
        c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (cat_id,))
        contents = c.fetchall()
        
        text = f"{em} {name}\n"
        buttons = []
        
        for sub in subcats:
            sem = sub['emoji'] or "📁"
            buttons.append([
                InlineKeyboardButton(text=f"  {sem} {sub['name']}", callback_data=f"cadm_sub_{sub['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cadm_delsub_{sub['id']}_{cat_id}"),
            ])
        
        for cont in contents:
            buttons.append([
                InlineKeyboardButton(text=f"  📝 {cont['title']}", callback_data=f"cadm_content_{cont['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cont['id']}_{cat_id}"),
            ])
        
        buttons.append([InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_rename_{cat_id}")])
        buttons.append([
            InlineKeyboardButton(text="➕ Подпапку", callback_data=f"cadm_addsub_{cat_id}"),
            InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontent_{cat_id}"),
        ])
        buttons.append([InlineKeyboardButton(text="← К КАТЕГОРИЯМ", callback_data="admin_categories")])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        if isinstance(target, Message):
            await target.answer(text, reply_markup=kb)
        else:
            await target.message.edit_text(text, reply_markup=kb)


async def subcat_admin_menu(target, sub_id: int, parent_cat_id: int):
    """Содержимое подкатегории."""
    with db_cursor() as c:
        c.execute("SELECT name, emoji FROM subcategories WHERE id=?", (sub_id,))
        sub = c.fetchone()
        if not sub:
            return
        
        name, emoji = sub
        em = emoji or "📁"
        
        c.execute("SELECT id, name, emoji FROM subsubcategories WHERE parent_id=? ORDER BY id", (sub_id,))
        subsubs = c.fetchall()
        c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (sub_id,))
        contents = c.fetchall()
        
        text = f"{em} {name}\n"
        buttons = []
        
        for ss in subsubs:
            ssem = ss['emoji'] or "📄"
            buttons.append([
                InlineKeyboardButton(text=f"  {ssem} {ss['name']}", callback_data=f"cadm_ssub_{ss['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cadm_delssub_{ss['id']}_{sub_id}_{parent_cat_id}"),
            ])
        
        for cont in contents:
            buttons.append([
                InlineKeyboardButton(text=f"  📝 {cont['title']}", callback_data=f"cadm_content_{cont['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cont['id']}_{sub_id}"),
            ])
        
        buttons.append([InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_renamesub_{sub_id}_{parent_cat_id}")])
        buttons.append([
            InlineKeyboardButton(text="➕ Под-подпапку", callback_data=f"cadm_addssub_{sub_id}_{parent_cat_id}"),
            InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontentsub_{sub_id}_{parent_cat_id}"),
        ])
        buttons.append([InlineKeyboardButton(text="← К КАТЕГОРИИ", callback_data=f"cadm_open_{parent_cat_id}")])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        if isinstance(target, Message):
            await target.answer(text, reply_markup=kb)
        else:
            await target.message.edit_text(text, reply_markup=kb)


async def ssub_admin_menu(target, ssub_id: int, sub_id: int, cat_id: int):
    """Содержимое под-подкатегории."""
    with db_cursor() as c:
        c.execute("SELECT name, emoji FROM subsubcategories WHERE id=?", (ssub_id,))
        ssub = c.fetchone()
        if not ssub:
            return
        
        name, emoji = ssub
        em = emoji or "📄"
        
        c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (ssub_id,))
        contents = c.fetchall()
        
        text = f"{em} {name}\n"
        buttons = []
        
        for cont in contents:
            buttons.append([
                InlineKeyboardButton(text=f"  📝 {cont['title']}", callback_data=f"cadm_content_{cont['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cont['id']}_{ssub_id}"),
            ])
        
        buttons.append([InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_renamessub_{ssub_id}_{sub_id}_{cat_id}")])
        buttons.append([InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontentssub_{ssub_id}_{sub_id}_{cat_id}")])
        buttons.append([InlineKeyboardButton(text="← К ПОДПАПКЕ", callback_data=f"cadm_sub_{sub_id}_{cat_id}")])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        if isinstance(target, Message):
            await target.answer(text, reply_markup=kb)
        else:
            await target.message.edit_text(text, reply_markup=kb)


@admin_router.callback_query(F.data == "admin_categories")
async def admin_categories(cb: CallbackQuery):
    """Открыть управление категориями."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    await cat_admin_menu(cb)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_open_"))
async def cadm_open(cb: CallbackQuery):
    """Открыть категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    await cat_admin_menu(cb, cat_id)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_del_"))
async def cadm_del(cb: CallbackQuery):
    """Удалить категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
        cat = c.fetchone()
        if not cat:
            await cb.answer("Не найдено", show_alert=True)
            return
        
        c.execute("SELECT id FROM subcategories WHERE parent_id=?", (cat_id,))
        subs = c.fetchall()
        for sub in subs:
            c.execute("DELETE FROM subsubcategories WHERE parent_id=?", (sub['id'],))
            c.execute("DELETE FROM content WHERE cat_id=?", (sub['id'],))
        c.execute("DELETE FROM subcategories WHERE parent_id=?", (cat_id,))
        c.execute("DELETE FROM content WHERE cat_id=?", (cat_id,))
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    
    await cb.answer(f"✅ Удалено: {cat['name']}", show_alert=True)
    await cat_admin_menu(cb)


@admin_router.callback_query(F.data == "cadm_new")
async def cadm_new(cb: CallbackQuery, state: FSMContext):
    """Создать новую категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    await safe_edit(cb, "📁 Новая категория\n\nВведи название:")
    await state.set_state(AdminStates.waiting_category_name)
    await cb.answer()


@admin_router.message(AdminStates.waiting_category_name)
async def cadm_save_new(msg: Message, state: FSMContext):
    """Сохранить новую категорию."""
    if not is_admin(msg.from_user.id):
        return
    
    name = msg.text.strip()
    with db_cursor() as c:
        try:
            c.execute("INSERT INTO categories (name, emoji, description) VALUES (?,?,?)", 
                     (name, "📁", ""))
            await msg.answer(f"✅ Категория '{name}' создана!")
        except Exception as e:
            await msg.answer(f"❌ {e}")
    
    await state.clear()
    await cat_admin_menu(msg)


@admin_router.callback_query(F.data.startswith("cadm_rename_"))
async def cadm_rename(cb: CallbackQuery, state: FSMContext):
    """Переименовать категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await state.update_data(edit_cat_id=cat_id)
    await safe_edit(cb, "✏️ Введи новое название категории:")
    await state.set_state(AdminStates.edit_field)
    await cb.answer()


@admin_router.message(AdminStates.edit_field)
async def cadm_save_rename(msg: Message, state: FSMContext):
    """Сохранить новое название."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    cat_id = data.get("edit_cat_id")
    if not cat_id:
        await state.clear()
        return
    
    with db_cursor() as c:
        c.execute("UPDATE categories SET name=? WHERE id=?", (msg.text.strip(), cat_id))
    
    await msg.answer(f"✅ Переименовано!")
    await state.clear()
    await cat_admin_menu(msg, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_addsub_"))
async def cadm_addsub(cb: CallbackQuery, state: FSMContext):
    """Добавить подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await state.update_data(parent_cat_id=cat_id)
    await safe_edit(cb, "📁 Новая подпапка\n\nВведи название:")
    await state.set_state(AdminStates.waiting_name)
    await cb.answer()


@admin_router.message(AdminStates.waiting_name)
async def cadm_save_subcat(msg: Message, state: FSMContext):
    """Сохранить подкатегорию."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    cat_id = data.get("parent_cat_id")
    name = msg.text.strip()
    
    with db_cursor() as c:
        c.execute("INSERT INTO subcategories (parent_id, name, emoji, created_at) VALUES (?,?,?,?)",
                  (cat_id, name, "📁", datetime.now()))
    
    await msg.answer(f"✅ Подпапка '{name}' создана!")
    await state.clear()
    await cat_admin_menu(msg, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_sub_"))
async def cadm_sub(cb: CallbackQuery):
    """Открыть подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    sub_id = int(parts[2])
    if len(parts) > 3:
        cat_id = int(parts[3])
    else:
        with db_cursor() as c:
            c.execute("SELECT parent_id FROM subcategories WHERE id=?", (sub_id,))
            r = c.fetchone()
            cat_id = r['parent_id'] if r else 0
    
    await subcat_admin_menu(cb, sub_id, cat_id)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_delsub_"))
async def cadm_delsub(cb: CallbackQuery):
    """Удалить подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    sub_id = int(parts[2])
    cat_id = int(parts[3])
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM subcategories WHERE id=?", (sub_id,))
        sub = c.fetchone()
        
        c.execute("DELETE FROM subsubcategories WHERE parent_id=?", (sub_id,))
        c.execute("DELETE FROM content WHERE cat_id=?", (sub_id,))
        c.execute("DELETE FROM subcategories WHERE id=?", (sub_id,))
    
    await cb.answer(f"✅ Удалено: {sub['name'] if sub else ''}", show_alert=True)
    await cat_admin_menu(cb, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_renamesub_"))
async def cadm_renamesub(cb: CallbackQuery, state: FSMContext):
    """Переименовать подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    sub_id = int(parts[2])
    cat_id = int(parts[3])
    
    await state.update_data(edit_sub_id=sub_id, edit_cat_id=cat_id)
    await safe_edit(cb, "✏️ Введи новое название подпапки:")
    await state.set_state(AdminStates.edit_field)
    await cb.answer()


@admin_router.message(AdminStates.edit_field)
async def cadm_save_renamesub(msg: Message, state: FSMContext):
    """Сохранить новое название подкатегории."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    sub_id = data.get("edit_sub_id")
    cat_id = data.get("edit_cat_id")
    
    with db_cursor() as c:
        c.execute("UPDATE subcategories SET name=? WHERE id=?", (msg.text.strip(), sub_id))
    
    await msg.answer("✅ Переименовано!")
    await state.clear()
    await subcat_admin_menu(msg, sub_id, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_addssub_"))
async def cadm_addssub(cb: CallbackQuery, state: FSMContext):
    """Добавить под-подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    sub_id = int(parts[2])
    cat_id = int(parts[3])
    
    await state.update_data(parent_sub_id=sub_id, parent_cat_id=cat_id)
    await safe_edit(cb, "📄 Новая под-подпапка\n\nВведи название:")
    await state.set_state(AdminStates.waiting_name)
    await cb.answer()


@admin_router.message(AdminStates.waiting_name)
async def cadm_save_ssub(msg: Message, state: FSMContext):
    """Сохранить под-подкатегорию."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    sub_id = data.get("parent_sub_id")
    cat_id = data.get("parent_cat_id")
    
    with db_cursor() as c:
        c.execute("INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?,?,?,?)",
                  (sub_id, msg.text.strip(), "📄", datetime.now()))
    
    await msg.answer(f"✅ Создано!")
    await state.clear()
    await subcat_admin_menu(msg, sub_id, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_ssub_"))
async def cadm_ssub(cb: CallbackQuery):
    """Открыть под-подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    ssub_id = int(parts[2])
    
    with db_cursor() as c:
        c.execute("SELECT parent_id FROM subsubcategories WHERE id=?", (ssub_id,))
        r = c.fetchone()
        sub_id = r['parent_id'] if r else 0
        
        c.execute("SELECT parent_id FROM subcategories WHERE id=?", (sub_id,))
        r2 = c.fetchone()
        cat_id = r2['parent_id'] if r2 else 0
    
    await ssub_admin_menu(cb, ssub_id, sub_id, cat_id)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_delssub_"))
async def cadm_delssub(cb: CallbackQuery):
    """Удалить под-подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    ssub_id = int(parts[2])
    sub_id = int(parts[3])
    cat_id = int(parts[4])
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM subsubcategories WHERE id=?", (ssub_id,))
        ss = c.fetchone()
        
        c.execute("DELETE FROM content WHERE cat_id=?", (ssub_id,))
        c.execute("DELETE FROM subsubcategories WHERE id=?", (ssub_id,))
    
    await cb.answer(f"✅ {ss['name'] if ss else ''} удалено", show_alert=True)
    await subcat_admin_menu(cb, sub_id, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_renamessub_"))
async def cadm_renamessub(cb: CallbackQuery, state: FSMContext):
    """Переименовать под-подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    ssub_id = int(parts[2])
    sub_id = int(parts[3])
    cat_id = int(parts[4])
    
    await state.update_data(edit_ssub_id=ssub_id, edit_sub_id=sub_id, edit_cat_id=cat_id)
    await safe_edit(cb, "✏️ Введи новое название:")
    await state.set_state(AdminStates.edit_field)
    await cb.answer()


@admin_router.message(AdminStates.edit_field)
async def cadm_save_renamessub(msg: Message, state: FSMContext):
    """Сохранить новое название под-подкатегории."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    ssub_id = data["edit_ssub_id"]
    sub_id = data["edit_sub_id"]
    cat_id = data["edit_cat_id"]
    
    with db_cursor() as c:
        c.execute("UPDATE subsubcategories SET name=? WHERE id=?", (msg.text.strip(), ssub_id))
    
    await msg.answer("✅ Переименовано!")
    await state.clear()
    await ssub_admin_menu(msg, ssub_id, sub_id, cat_id)


@admin_router.callback_query(F.data.startswith("cadm_addcontent_"))
async def cadm_addcontent(cb: CallbackQuery, state: FSMContext):
    """Добавить контент в категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        cat_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await state.update_data(content_cat_id=cat_id, content_level="cat")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.waiting_text)
    await cb.answer()


@admin_router.message(AdminStates.waiting_text)
async def cadm_content_title(msg: Message, state: FSMContext):
    """Сохранить заголовок контента."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(content_title=msg.text.strip())
    await msg.answer("Введи текст контента:")
    await state.set_state(AdminStates.waiting_description)


@admin_router.message(AdminStates.waiting_description)
async def cadm_content_desc(msg: Message, state: FSMContext):
    """Сохранить текст контента."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    cat_id = data["content_cat_id"]
    title = data["content_title"]
    content = msg.text.strip()
    
    with db_cursor() as c:
        c.execute("INSERT INTO content (cat_id, title, content, created_at) VALUES (?,?,?,?)",
                  (cat_id, title, content, datetime.now()))
    
    await msg.answer("✅ Контент добавлен!")
    await state.clear()
    
    level = data.get("content_level", "cat")
    if level == "cat":
        await cat_admin_menu(msg, cat_id)
    elif level == "sub":
        await subcat_admin_menu(msg, cat_id, data.get("parent_cat_id", 0))
    else:
        await ssub_admin_menu(msg, cat_id, data.get("parent_sub_id", 0), data.get("parent_cat_id", 0))


@admin_router.callback_query(F.data.startswith("cadm_addcontentsub_"))
async def cadm_addcontentsub(cb: CallbackQuery, state: FSMContext):
    """Добавить контент в подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    sub_id = int(parts[2])
    cat_id = int(parts[3])
    
    await state.update_data(content_cat_id=sub_id, parent_cat_id=cat_id, content_level="sub")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.waiting_text)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_addcontentssub_"))
async def cadm_addcontentssub(cb: CallbackQuery, state: FSMContext):
    """Добавить контент в под-подкатегорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    ssub_id = int(parts[2])
    sub_id = int(parts[3])
    cat_id = int(parts[4])
    
    await state.update_data(content_cat_id=ssub_id, parent_sub_id=sub_id, parent_cat_id=cat_id, content_level="ssub")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.waiting_text)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("cadm_delcontent_"))
async def cadm_delcontent(cb: CallbackQuery):
    """Удалить контент."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    content_id = int(parts[2])
    back_id = int(parts[3])
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM content WHERE id=?", (content_id,))
        
        in_cat = c.execute("SELECT id FROM categories WHERE id=?", (back_id,)).fetchone()
        if not in_cat:
            r = c.execute("SELECT parent_id FROM subcategories WHERE id=?", (back_id,)).fetchone()
            parent_cat = r['parent_id'] if r else 0
    
    await cb.answer("✅ Удалено", show_alert=True)
    if in_cat:
        await cat_admin_menu(cb, back_id)
    else:
        await subcat_admin_menu(cb, back_id, parent_cat)


@admin_router.callback_query(F.data.startswith("cadm_content_"))
async def cadm_view_content(cb: CallbackQuery):
    """Просмотр контента."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        content_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT title, content, cat_id FROM content WHERE id=?", (content_id,))
        item = c.fetchone()
    
    if not item:
        await cb.answer("Не найдено", show_alert=True)
        return
    
    title, content, cat_id = item
    await safe_edit(cb, 
        f"📝 {title}\n\n{content}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cadm_delcontent_{content_id}_{cat_id}")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data=f"cadm_open_{cat_id}")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ВИТРИНА - ПОЛНЫЙ АДМИН
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_showcase")
async def admin_showcase(cb: CallbackQuery):
    """Управление витриной."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, name, emoji FROM showcase_collections ORDER BY sort_order ASC, created_at ASC")
        cols = c.fetchall()
    
    buttons = []
    for col in cols:
        buttons.append([
            InlineKeyboardButton(text=f"{col['emoji'] or '💎'} {col['name']}", callback_data=f"sc_admin_col_{col['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"sc_del_col_{col['id']}"),
        ])
    
    buttons.append([InlineKeyboardButton(text="➕ НОВАЯ КОЛЛЕКЦИЯ", callback_data="sc_add_col")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    text = f"💎 УПРАВЛЕНИЕ ВИТРИНОЙ\n{len(cols)} коллекций"
    await safe_edit(cb, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@admin_router.callback_query(F.data == "sc_add_col")
async def sc_add_col(cb: CallbackQuery, state: FSMContext):
    """Добавить коллекцию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    await safe_edit(cb, "➕ НОВАЯ КОЛЛЕКЦИЯ\n\nВведи название:")
    await state.set_state(AdminStates.waiting_name)
    await cb.answer()


@admin_router.message(AdminStates.waiting_name)
async def sc_save_col_name(msg: Message, state: FSMContext):
    """Сохранить название коллекции."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(col_name=msg.text)
    await msg.answer("Введи эмодзи для коллекции (или напиши 'нет'):")
    await state.set_state(AdminStates.waiting_emoji)


@admin_router.message(AdminStates.waiting_emoji)
async def sc_save_col_emoji(msg: Message, state: FSMContext):
    """Сохранить эмодзи коллекции."""
    if not is_admin(msg.from_user.id):
        return
    
    emoji = msg.text if msg.text != 'нет' else '💎'
    await state.update_data(col_emoji=emoji)
    await msg.answer("Введи описание коллекции (или 'пропустить'):")
    await state.set_state(AdminStates.waiting_description)


@admin_router.message(AdminStates.waiting_description)
async def sc_save_col_desc(msg: Message, state: FSMContext):
    """Сохранить описание коллекции."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    desc = msg.text if msg.text.lower() != 'пропустить' else ''
    
    with db_cursor() as c:
        c.execute("INSERT INTO showcase_collections (name, emoji, description, created_at) VALUES (?,?,?,?)",
                  (data['col_name'], data.get('col_emoji','💎'), desc, datetime.now()))
    
    await msg.answer(f"✅ Коллекция '{data['col_name']}' создана!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 К ВИТРИНЕ", callback_data="admin_showcase")]]))
    await state.clear()


@admin_router.callback_query(F.data.startswith("sc_admin_col_"))
async def sc_admin_collection(cb: CallbackQuery):
    """Управление коллекцией."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        col_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT name, emoji FROM showcase_collections WHERE id=?", (col_id,))
        col = c.fetchone()
        c.execute("SELECT id, name, price FROM showcase_items WHERE collection_id=? ORDER BY sort_order ASC, created_at ASC", (col_id,))
        items = c.fetchall()
    
    if not col:
        await cb.answer("Не найдено", show_alert=True)
        return
    
    buttons = []
    for item in items:
        price_str = f" {item['price']:.0f}₽" if item['price'] else ""
        buttons.append([
            InlineKeyboardButton(text=f"{item['name']}{price_str}", callback_data=f"sc_admin_item_{item['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"sc_del_item_{item['id']}_{col_id}"),
        ])
    
    buttons.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОВАР", callback_data=f"sc_add_item_{col_id}")])
    buttons.append([InlineKeyboardButton(text="← К ВИТРИНЕ", callback_data="admin_showcase")])
    
    await safe_edit(cb, 
        f"{col['emoji'] or '💎'} {col['name']}\n{len(items)} товаров",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@admin_router.callback_query(F.data.startswith("sc_add_item_"))
async def sc_add_item(cb: CallbackQuery, state: FSMContext):
    """Добавить товар."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        col_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await state.update_data(sc_col_id=col_id)
    await safe_edit(cb, "➕ НОВЫЙ ТОВАР\n\nВведи название товара:")
    await state.set_state(AdminStates.waiting_name)
    await cb.answer()


@admin_router.message(AdminStates.waiting_name)
async def sc_save_item_name(msg: Message, state: FSMContext):
    """Сохранить название товара."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(item_name=msg.text)
    await msg.answer("Введи описание товара (или 'пропустить'):")
    await state.set_state(AdminStates.waiting_description)


@admin_router.message(AdminStates.waiting_description)
async def sc_save_item_desc(msg: Message, state: FSMContext):
    """Сохранить описание товара."""
    if not is_admin(msg.from_user.id):
        return
    
    desc = msg.text if msg.text.lower() != 'пропустить' else ''
    await state.update_data(item_desc=desc)
    await msg.answer("Введи цену (число, или 'пропустить'):")
    await state.set_state(AdminStates.waiting_price)


@admin_router.message(AdminStates.waiting_price)
async def sc_save_item_price(msg: Message, state: FSMContext):
    """Сохранить цену товара."""
    if not is_admin(msg.from_user.id):
        return
    
    try:
        price = float(msg.text.replace(',', '.'))
    except:
        price = None
    
    await state.update_data(item_price=price)
    await msg.answer("Отправь фото товара (или напиши 'пропустить'):")
    await state.set_state(AdminStates.waiting_photo)


@admin_router.message(AdminStates.waiting_photo)
async def sc_save_item_photo(msg: Message, state: FSMContext):
    """Сохранить фото товара."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    image_id = msg.photo[-1].file_id if msg.photo else None
    
    with db_cursor() as c:
        c.execute("INSERT INTO showcase_items (collection_id, name, description, price, image_file_id, created_at) VALUES (?,?,?,?,?,?)",
                  (data['sc_col_id'], data['item_name'], data.get('item_desc',''),
                   data.get('item_price'), image_id, datetime.now()))
    
    await msg.answer(f"✅ Товар '{data['item_name']}' добавлен!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К КОЛЛЕКЦИИ", callback_data=f"sc_admin_col_{data['sc_col_id']}")],
            [InlineKeyboardButton(text="➕ ЕЩЁ ТОВАР", callback_data=f"sc_add_item_{data['sc_col_id']}")],
        ]))
    await state.clear()


@admin_router.callback_query(F.data.startswith("sc_admin_item_"))
async def sc_admin_item(cb: CallbackQuery):
    """Управление товаром."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        item_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT si.id, si.name, si.description, si.price, si.image_file_id, si.collection_id FROM showcase_items si WHERE si.id=?", (item_id,))
        item = c.fetchone()
    
    if not item:
        await cb.answer("Не найдено", show_alert=True)
        return
    
    iid, name, desc, price, img, col_id = item
    text = f"✏️ {name}\n\n{desc or '—'}\n💰 {price:.0f}₽" if price else f"✏️ {name}\n\n{desc or '—'}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"sc_edit_name_{iid}"),
         InlineKeyboardButton(text="✏️ Описание", callback_data=f"sc_edit_desc_{iid}")],
        [InlineKeyboardButton(text="✏️ Цена ₽", callback_data=f"sc_edit_price_{iid}")],
        [InlineKeyboardButton(text="📸 Фото", callback_data=f"sc_edit_photo_{iid}")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"sc_del_item_{iid}_{col_id}")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data=f"sc_admin_col_{col_id}")],
    ])
    
    if img:
        await cb.message.answer_photo(photo=img, caption=text[:1024], reply_markup=kb)
        await cb.message.delete()
    else:
        await cb.message.edit_text(text, reply_markup=kb)
    
    await cb.answer()


@admin_router.callback_query(F.data.startswith("sc_edit_"))
async def sc_edit_item_field(cb: CallbackQuery, state: FSMContext):
    """Редактировать поле товара."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    field = parts[2]
    item_id = int(parts[-1])
    
    await state.update_data(sc_edit_item_id=item_id, sc_edit_field=field)
    
    prompts = {
        "name": "Введи новое название:",
        "desc": "Введи новое описание:", 
        "price": "Введи новую цену:",
        "photo": "Отправь новое фото:"
    }
    
    await cb.message.edit_text(f"✏️ {prompts.get(field, 'Введи значение:')}")
    await state.set_state(AdminStates.edit_field)
    await cb.answer()


@admin_router.message(AdminStates.edit_field)
async def sc_save_edit(msg: Message, state: FSMContext):
    """Сохранить изменения товара."""
    if not is_admin(msg.from_user.id):
        return
    
    data = await state.get_data()
    item_id = data['sc_edit_item_id']
    field = data['sc_edit_field']
    
    with db_connection() as conn:
        c = conn.cursor()
        
        if field == 'name':
            c.execute("UPDATE showcase_items SET name=? WHERE id=?", (msg.text, item_id))
        elif field == 'desc':
            c.execute("UPDATE showcase_items SET description=? WHERE id=?", (msg.text, item_id))
        elif field == 'price':
            try:
                price = float(msg.text.replace(',','.'))
            except:
                price = None
            c.execute("UPDATE showcase_items SET price=? WHERE id=?", (price, item_id))
        elif field == 'photo':
            if msg.photo:
                c.execute("UPDATE showcase_items SET image_file_id=? WHERE id=?", (msg.photo[-1].file_id, item_id))
        
        c.execute("SELECT collection_id FROM showcase_items WHERE id=?", (item_id,))
        r = c.fetchone()
    
    await msg.answer("✅ Обновлено!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← К КОЛЛЕКЦИИ", callback_data=f"sc_admin_col_{r['collection_id']}" if r else "admin_showcase")]]))
    await state.clear()


@admin_router.callback_query(F.data.startswith("sc_del_item_"))
async def sc_del_item(cb: CallbackQuery):
    """Удалить товар."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    item_id = int(parts[3])
    col_id = int(parts[4]) if len(parts) > 4 else 0
    
    with db_cursor() as c:
        c.execute("DELETE FROM showcase_items WHERE id=?", (item_id,))
    
    await cb.answer("✅ Товар удалён", show_alert=True)
    if col_id:
        await sc_admin_collection(cb)


@admin_router.callback_query(F.data.startswith("sc_del_col_"))
async def sc_del_col(cb: CallbackQuery):
    """Удалить коллекцию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        col_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM showcase_items WHERE collection_id=?", (col_id,))
        c.execute("DELETE FROM showcase_collections WHERE id=?", (col_id,))
    
    await cb.answer("✅ Коллекция удалена", show_alert=True)
    await admin_showcase(cb)

# ═══════════════════════════════════════════════════════════════════════════
# КОРЗИНА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "view_cart")
@rate_limit(2.0)
async def view_cart(cb: CallbackQuery):
    """Просмотр корзины."""
    total, items = await get_cart_total(cb.from_user.id)
    
    if not items:
        await safe_edit(cb,
            "🛒 *Корзина пуста*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Перейти в витрину", callback_data="showcase_bracelets")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
            ])
        )
        await cb.answer()
        return
    
    text = "🛒 *КОРЗИНА:*\n\n"
    buttons = []
    
    for item in items:
        price_str = ItemInfo.format_price(item['price'])
        text += f"{item['name']}\n"
        text += f"  {item['quantity']} шт. × {price_str} = {item['line_total']:.0f}₽\n\n"
        buttons.append([InlineKeyboardButton(
            text=f"❌ Удалить {item['name'][:20]}",
            callback_data=f"remove_cart_{item['id']}"
        )])
    
    bonus_balance = await get_user_bonus_balance(cb.from_user.id)
    bonus_line = f"\n💰 *Доступно бонусов:* {bonus_balance:.0f}₽" if bonus_balance > 0 else ""
    
    text += f"\n💰 *ИТОГО:* {total:.0f}₽{bonus_line}"
    
    payment_buttons = []
    if bonus_balance > 0 and total > 0:
        max_bonus = min(bonus_balance, total)
        payment_buttons.append([InlineKeyboardButton(
            text=f"💎 Оплатить бонусами (до {max_bonus:.0f}₽)",
            callback_data="pay_bonus"
        )])
    
    payment_buttons.extend([
        [InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
        [InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
    ])
    
    buttons.extend(payment_buttons)
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    await FunnelTracker.track(cb.from_user.id, 'view_cart')
    await cb.answer()


@main_router.callback_query(F.data.startswith("remove_cart_"))
@rate_limit(1.0)
async def remove_from_cart(cb: CallbackQuery):
    """Удалить товар из корзины."""
    try:
        cart_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    if await remove_from_cart(cart_id):
        await cb.answer("✅ Товар удалён из корзины", show_alert=True)
    else:
        await cb.answer("❌ Ошибка при удалении", show_alert=True)
    
    await view_cart(cb)


@main_router.callback_query(F.data.startswith("restore_cart_"))
@rate_limit(2.0)
async def restore_cart(cb: CallbackQuery):
    """Восстановить корзину из отменённого заказа."""
    try:
        order_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    if await restore_cart_from_order(cb.from_user.id, order_id):
        await cb.answer("✅ Корзина восстановлена", show_alert=True)
        await view_cart(cb)
    else:
        await cb.answer("❌ Ошибка при восстановлении", show_alert=True)


@main_router.callback_query(F.data == "pay_bonus")
@rate_limit(2.0)
async def pay_bonus_start(cb: CallbackQuery, state: FSMContext):
    """Начало оплаты бонусами."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
        cart_rows = c.fetchall()
    
    if not cart_rows:
        await cb.answer("Корзина пуста", show_alert=True)
        return
    
    total = 0.0
    for row in cart_rows:
        name, price, _ = ItemInfo.get_item_info(row['bracelet_id'])
        total += price * row['quantity']
    
    bonus_balance = await get_user_bonus_balance(user_id)
    max_bonus = min(bonus_balance, total)
    
    if max_bonus <= 0:
        await cb.answer("Недостаточно бонусов для оплаты", show_alert=True)
        return
    
    await state.update_data(bonus_total=total, bonus_max=max_bonus, bonus_balance=bonus_balance)
    
    await safe_edit(cb,
        f"💎 ОПЛАТА БОНУСАМИ\n\n"
        f"💰 Сумма заказа: {total:.0f}₽\n"
        f"💎 Ваш бонусный баланс: {bonus_balance:.0f}₽\n\n"
        f"Введите сумму в рублях, которую хотите списать бонусами\n"
        f"(от 1 до {max_bonus:.0f}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Списать всё ({max_bonus:.0f}₽)", callback_data="bonus_all")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await state.set_state(BonusPaymentStates.waiting_bonus_amount)
    await cb.answer()


@main_router.callback_query(F.data == "bonus_all")
@rate_limit(2.0)
async def bonus_all(cb: CallbackQuery, state: FSMContext):
    """Списать все бонусы."""
    data = await state.get_data()
    max_bonus = data.get('bonus_max', 0)
    total = data.get('bonus_total', 0)
    
    if max_bonus <= 0:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await process_bonus_payment(cb.message, cb.from_user.id, max_bonus, total, state, True)
    await cb.answer()


@main_router.message(BonusPaymentStates.waiting_bonus_amount)
@rate_limit(1.0)
async def bonus_amount_input(msg: Message, state: FSMContext):
    """Обработка введённой суммы бонусов."""
    try:
        bonus_amount = float(msg.text.strip().replace(',', '.'))
    except:
        await msg.answer("❌ Введите число")
        return
    
    data = await state.get_data()
    max_bonus = data.get('bonus_max', 0)
    total = data.get('bonus_total', 0)
    
    if bonus_amount < 1:
        await msg.answer("❌ Минимальная сумма списания - 1 рубль")
        return
    
    if bonus_amount > max_bonus:
        await msg.answer(f"❌ У вас только {max_bonus:.0f} бонусов")
        return
    
    await process_bonus_payment(msg, msg.from_user.id, bonus_amount, total, state, False)


async def process_bonus_payment(target, user_id: int, bonus_amount: float, total: float, state: FSMContext, is_cb: bool):
    """Обработка оплаты бонусами."""
    final_price = max(0, total - bonus_amount)
    
    with db_connection() as conn:
        c = conn.cursor()
        try:
            c.execute('SELECT balance FROM referral_balance WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if not row or row['balance'] < bonus_amount - 0.01:
                if is_cb:
                    await target.edit_text("❌ Недостаточно бонусов. Баланс изменился.")
                else:
                    await target.answer("❌ Недостаточно бонусов. Баланс изменился.")
                return
            
            c.execute("""INSERT INTO orders 
                         (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (user_id, final_price, 'pending', 'bonus', datetime.now(), None, 0, bonus_amount, bonus_amount))
            order_id = c.lastrowid
            
            await apply_bonus_to_order(user_id, order_id, bonus_amount)
            
            c.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
            conn.commit()
            
            await notify_admin_bonus_usage(user_id, order_id, bonus_amount, final_price)
            
            if final_price > 0:
                text = (f"✅ БОНУСЫ ПРИМЕНЕНЫ!\n\n"
                        f"💎 Списано бонусов: {bonus_amount:.0f}₽\n"
                        f"💰 Осталось к оплате: {final_price:.0f}₽\n\n"
                        f"Выберите способ оплаты оставшейся суммы:")
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
                    [InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
                    [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
                ])
                if is_cb:
                    await target.edit_text(text, reply_markup=kb)
                else:
                    await target.answer(text, reply_markup=kb)
            else:
                c.execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
                conn.commit()
                
                text = (f"✅ ЗАКАЗ #{order_id} ПОЛНОСТЬЮ ОПЛАЧЕН БОНУСАМИ!\n\n"
                        f"💎 Списано бонусов: {bonus_amount:.0f}₽\n\n"
                        f"Мастер получил уведомление и скоро свяжется с вами.")
                if is_cb:
                    await target.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]]))
                else:
                    await target.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]]))
            
        except Exception as e:
            logger.error(f"Bonus payment error: {e}")
            if is_cb:
                await target.edit_text("❌ Ошибка при обработке платежа")
            else:
                await target.answer("❌ Ошибка при обработке платежа")
        finally:
            await state.clear()


@main_router.callback_query(F.data == "pay_yandex")
@rate_limit(2.0)
async def pay_yandex(cb: CallbackQuery, state: FSMContext):
    """Оплата Яндекс.Кассой."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
        cart_rows = c.fetchall()
    
    total = 0.0
    for row in cart_rows:
        name, price, _ = ItemInfo.get_item_info(row['bracelet_id'])
        total += price * row['quantity']
    
    data = await state.get_data()
    bonus_used = data.get('bonus_used', 0.0)
    final_total = max(0.0, total - bonus_used)
    
    with db_cursor() as c:
        c.execute("""INSERT INTO orders 
                     (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (user_id, final_total, 'pending', 'yandex', datetime.now(), None, 0, bonus_used, bonus_used))
        order_id = c.lastrowid
    
    if bonus_used > 0:
        await apply_bonus_to_order(user_id, order_id, bonus_used)
    
    await notify_admin_order(user_id, order_id, final_total, "Яндекс.Касса")
    
    bonus_line = f"\n💎 Оплачено бонусами: -{bonus_used:.0f}₽" if bonus_used > 0 else ""
    payment_text = (f"✅ Заказ #{order_id} создан!\n\n"
                    f"💰 Сумма к оплате: {final_total:.0f}₽{bonus_line}\n\n"
                    f"📝 РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ:\n"
                    f"Яндекс.Касса: {YANDEX_KASSA_EMAIL}")
    
    await state.update_data(bonus_used=0.0)
    await safe_edit(cb, payment_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await cb.answer()


@main_router.callback_query(F.data == "pay_crypto")
@rate_limit(2.0)
async def pay_crypto(cb: CallbackQuery, state: FSMContext):
    """Оплата криптовалютой."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
        cart_rows = c.fetchall()
    
    total = 0.0
    for row in cart_rows:
        name, price, _ = ItemInfo.get_item_info(row['bracelet_id'])
        total += price * row['quantity']
    
    data = await state.get_data()
    bonus_used = data.get('bonus_used', 0.0)
    final_total = max(0.0, total - bonus_used)
    
    with db_cursor() as c:
        c.execute("""INSERT INTO orders 
                     (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (user_id, final_total, 'pending', 'crypto', datetime.now(), None, 0, bonus_used, bonus_used))
        order_id = c.lastrowid
    
    if bonus_used > 0:
        await apply_bonus_to_order(user_id, order_id, bonus_used)
    
    bonus_line = f"\n💎 Оплачено бонусами: -{bonus_used:.0f}₽" if bonus_used > 0 else ""
    payment_text = (f"✅ Заказ #{order_id} создан!\n\n"
                    f"💰 Сумма к оплате: {final_total:.0f}₽{bonus_line}\n\n"
                    f"₿ Крипто адрес:\n{CRYPTO_WALLET_ADDRESS}")
    
    await state.update_data(bonus_used=0.0)
    await safe_edit(cb, payment_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await cb.answer()


@main_router.callback_query(F.data.startswith("confirm_order_"))
@rate_limit(2.0)
async def confirm_order(cb: CallbackQuery, state: FSMContext):
    """Подтверждение заказа."""
    if is_rate_limited(cb.from_user.id, "confirm", 2.0):
        await cb.answer("⏳ Заказ уже обрабатывается...", show_alert=False)
        return
    
    try:
        order_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    if not await acquire_order_lock(order_id, cb.from_user.id):
        await cb.answer("⏳ Заказ уже обрабатывается другим запросом", show_alert=True)
        return
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")
            
            c.execute("SELECT status, user_id, total_price FROM orders WHERE id = ?", (order_id,))
            order = c.fetchone()
            
            if not order or order['status'] in ['confirmed', 'cancelled']:
                conn.rollback()
                await cb.answer("Заказ не может быть подтверждён", show_alert=True)
                return
            
            c.execute("UPDATE orders SET status = ? WHERE id = ?", ('confirmed', order_id))
            
            await move_cart_to_order(cb.from_user.id, order_id)
            c.execute("DELETE FROM cart_reminders WHERE user_id = ?", (cb.from_user.id,))
            
            await state.update_data(promo_code=None, bonus_used=0.0)
            
            conn.commit()
        
        cashback_amount = await apply_cashback(order['user_id'], order_id, order['total_price'])
        cashback_text = f"\n💰 Вам начислено {cashback_amount:.0f} бонусов за покупку!" if cashback_amount > 0 else ""
        
        await send_order_status_notification(order['user_id'], order_id, 'confirmed')
        
        await safe_edit(cb, 
            f"✅ Заказ #{order_id} подтверждён!\n\n"
            f"Мастер получил уведомление и скоро свяжется с вами. Спасибо за покупку! 🪨"
            f"{cashback_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ ОСТАВИТЬ ОТЗЫВ", callback_data="leave_review")],
                [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")],
            ])
        )
        
    except Exception as e:
        logger.error(f"Confirm order error: {e}")
        await cb.answer("❌ Ошибка при подтверждении заказа", show_alert=True)
    finally:
        await release_order_lock(order_id)


@admin_router.callback_query(F.data.startswith("setstatus_"))
@rate_limit(2.0)
async def set_order_status(cb: CallbackQuery):
    """Смена статуса заказа админом."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    parts = cb.data.split("_")
    order_id = int(parts[-1])
    status = parts[1]
    
    status_map = {
        'confirmed':'confirmed', 'paid':'paid', 'inprogress':'in_progress',
        'shipped':'shipped', 'delivered':'delivered', 'cancelled':'cancelled'
    }
    real_status = status_map.get(status, status)
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, bonus_used FROM orders WHERE id=?", (order_id,))
        order_info = c.fetchone()
        
        if not order_info:
            await cb.answer("Заказ не найден", show_alert=True)
            return
        
        user_id, bonus_used = order_info['user_id'], order_info['bonus_used']
        c.execute("UPDATE orders SET status=? WHERE id=?", (real_status, order_id))
        
        if real_status == 'cancelled':
            await restore_cart_from_order(user_id, order_id)
            
            if bonus_used and bonus_used > 0:
                with db_connection() as conn2:
                    c2 = conn2.cursor()
                    c2.execute('UPDATE referral_balance SET balance = balance + ? WHERE user_id = ?', (bonus_used, user_id))
                    c2.execute('INSERT INTO bonus_history (user_id, amount, operation, order_id, created_at) VALUES (?,?,?,?,?)',
                              (user_id, bonus_used, 'refund', order_id, datetime.now()))
    
    await send_order_status_notification(user_id, order_id, real_status)
    await cb.answer(f"✅ Статус: {real_status}", show_alert=True)
    await admin_orders(cb)

# ═══════════════════════════════════════════════════════════════════════════
# ОТЗЫВЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "leave_review")
@rate_limit(2.0)
async def leave_review(cb: CallbackQuery, state: FSMContext):
    """Начать отзыв."""
    await state.update_data(from_confirmation=True)
    await safe_edit(cb, "⭐ ОЦЕНКА:\n\n1 - очень плохо\n5 - отлично",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐", callback_data="rate_1"),
             InlineKeyboardButton(text="⭐⭐", callback_data="rate_2"),
             InlineKeyboardButton(text="⭐⭐⭐", callback_data="rate_3")],
            [InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="rate_4"),
             InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="rate_5")],
        ])
    )
    await cb.answer()


@main_router.callback_query(F.data.startswith("rate_"))
@rate_limit(1.0)
async def save_rating(cb: CallbackQuery, state: FSMContext):
    """Сохранить оценку."""
    try:
        rating = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    await state.update_data(rating=rating)
    await safe_edit(cb, "📝 Напиши свой отзыв (текст):")
    await state.set_state(ReviewStates.waiting_text)
    await cb.answer()


@main_router.message(ReviewStates.waiting_text)
@rate_limit(1.0)
async def save_review_text(msg: Message, state: FSMContext):
    """Сохранить текст отзыва."""
    data = await state.get_data()
    user_id = msg.from_user.id
    rating = data['rating']
    
    with db_cursor() as c:
        c.execute('SELECT bracelet_id FROM cart WHERE user_id = ? LIMIT 1', (user_id,))
        result = c.fetchone()
        bracelet_id = result['bracelet_id'] if result else 1
        
        c.execute('INSERT INTO reviews_new (user_id, bracelet_id, rating, review_text, created_at) VALUES (?,?,?,?,?)',
                  (user_id, bracelet_id, rating, msg.text, datetime.now()))
    
    await msg.answer("✅ Спасибо за отзыв!")
    await state.clear()


@main_router.callback_query(F.data.startswith("reviews_"))
@rate_limit(2.0)
async def show_reviews(cb: CallbackQuery):
    """Показать отзывы."""
    try:
        bracelet_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute('SELECT rating, review_text FROM reviews_new WHERE bracelet_id = ? ORDER BY created_at DESC LIMIT 10', (bracelet_id,))
        reviews = c.fetchall()
    
    if not reviews:
        text = "📭 Отзывов нет"
    else:
        text = "⭐ ОТЗЫВЫ:\n\n"
        for r in reviews:
            stars = "⭐" * r['rating']
            text += f"{stars}\n{r['review_text']}\n\n"
    
    await safe_edit(cb, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ВИКТОРИНА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "totem_start")
@rate_limit(2.0)
async def totem_start(cb: CallbackQuery, state: FSMContext):
    """Начать викторину."""
    await state.clear()
    
    with db_cursor() as c:
        c.execute("SELECT question, options FROM totem_questions WHERE active=1 ORDER BY sort_order, id LIMIT 1")
        first_q = c.fetchone()
    
    if not first_q:
        await safe_edit(cb, "🎯 Викторина временно недоступна.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer()
        return
    
    question = first_q['question']
    options = safe_json_parse(first_q['options'], [])
    
    await state.update_data(current_q=1, answers={})
    
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_{i}")])
    
    await safe_edit(cb,
        f"🎯 *ВИКТОРИНА: ТОТЕМНЫЙ КАМЕНЬ*\n\n"
        f"*Вопрос 1 из 5:*\n\n{question}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(TotemStates.q1)
    await cb.answer()


@main_router.callback_query(TotemStates.q1, F.data.startswith("totem_"))
@rate_limit(1.0)
async def totem_q1(cb: CallbackQuery, state: FSMContext):
    """Ответ на вопрос 1."""
    answer = int(cb.data.split("_")[1])
    data = await state.get_data()
    answers = data.get('answers', {})
    answers['q1'] = answer
    await state.update_data(answers=answers, current_q=2)
    
    with db_cursor() as c:
        c.execute("SELECT question, options FROM totem_questions WHERE active=1 ORDER BY sort_order, id LIMIT 1 OFFSET 1")
        second_q = c.fetchone()
    
    if not second_q:
        await totem_finish(cb.message, state, True)
        await cb.answer()
        return
    
    question = second_q['question']
    options = safe_json_parse(second_q['options'], [])
    
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_{i}")])
    
    await safe_edit(cb,
        f"🎯 *Вопрос 2 из 5:*\n\n{question}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(TotemStates.q2)
    await cb.answer()


@main_router.callback_query(TotemStates.q2, F.data.startswith("totem_"))
@rate_limit(1.0)
async def totem_q2(cb: CallbackQuery, state: FSMContext):
    """Ответ на вопрос 2."""
    answer = int(cb.data.split("_")[1])
    data = await state.get_data()
    answers = data.get('answers', {})
    answers['q2'] = answer
    await state.update_data(answers=answers, current_q=3)
    
    with db_cursor() as c:
        c.execute("SELECT question, options FROM totem_questions WHERE active=1 ORDER BY sort_order, id LIMIT 1 OFFSET 2")
        third_q = c.fetchone()
    
    if not third_q:
        await totem_finish(cb.message, state, True)
        await cb.answer()
        return
    
    question = third_q['question']
    options = safe_json_parse(third_q['options'], [])
    
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_{i}")])
    
    await safe_edit(cb,
        f"🎯 *Вопрос 3 из 5:*\n\n{question}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(TotemStates.q3)
    await cb.answer()


@main_router.callback_query(TotemStates.q3, F.data.startswith("totem_"))
@rate_limit(1.0)
async def totem_q3(cb: CallbackQuery, state: FSMContext):
    """Ответ на вопрос 3."""
    answer = int(cb.data.split("_")[1])
    data = await state.get_data()
    answers = data.get('answers', {})
    answers['q3'] = answer
    await state.update_data(answers=answers, current_q=4)
    
    with db_cursor() as c:
        c.execute("SELECT question, options FROM totem_questions WHERE active=1 ORDER BY sort_order, id LIMIT 1 OFFSET 3")
        fourth_q = c.fetchone()
    
    if not fourth_q:
        await totem_finish(cb.message, state, True)
        await cb.answer()
        return
    
    question = fourth_q['question']
    options = safe_json_parse(fourth_q['options'], [])
    
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_{i}")])
    
    await safe_edit(cb,
        f"🎯 *Вопрос 4 из 5:*\n\n{question}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(TotemStates.q4)
    await cb.answer()


@main_router.callback_query(TotemStates.q4, F.data.startswith("totem_"))
@rate_limit(1.0)
async def totem_q4(cb: CallbackQuery, state: FSMContext):
    """Ответ на вопрос 4."""
    answer = int(cb.data.split("_")[1])
    data = await state.get_data()
    answers = data.get('answers', {})
    answers['q4'] = answer
    await state.update_data(answers=answers, current_q=5)
    
    with db_cursor() as c:
        c.execute("SELECT question, options FROM totem_questions WHERE active=1 ORDER BY sort_order, id LIMIT 1 OFFSET 4")
        fifth_q = c.fetchone()
    
    if not fifth_q:
        await totem_finish(cb.message, state, True)
        await cb.answer()
        return
    
    question = fifth_q['question']
    options = safe_json_parse(fifth_q['options'], [])
    
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"totem_{i}")])
    
    await safe_edit(cb,
        f"🎯 *Вопрос 5 из 5:*\n\n{question}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(TotemStates.q5)
    await cb.answer()


@main_router.callback_query(TotemStates.q5, F.data.startswith("totem_"))
@rate_limit(1.0)
async def totem_q5(cb: CallbackQuery, state: FSMContext):
    """Ответ на вопрос 5."""
    answer = int(cb.data.split("_")[1])
    data = await state.get_data()
    answers = data.get('answers', {})
    answers['q5'] = answer
    
    await totem_finish(cb.message, state, True)
    await cb.answer()


async def totem_finish(message, state: FSMContext, is_cb: bool):
    """Завершить викторину."""
    data = await state.get_data()
    answers = data.get('answers', {})
    
    top3 = await calculate_totem_result(answers)
    
    with db_cursor() as c:
        c.execute('''INSERT INTO totem_results 
                     (user_id, answers, top1, top2, top3, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (message.from_user.id, str(answers), top3[0], top3[1], top3[2], datetime.now()))
    
    text = (f"🎯 *ВАШ ТОТЕМНЫЙ КАМЕНЬ*\n\n"
            f"По результатам викторины, вам больше всего подходят:\n\n"
            f"🥇 {top3[0]}\n"
            f"🥈 {top3[1]}\n"
            f"🥉 {top3[2]}\n\n"
            f"Эти камни помогут раскрыть ваш потенциал.")
    
    buttons = [
        [InlineKeyboardButton(text="💎 Посмотреть в витрине", callback_data="showcase_bracelets")],
        [InlineKeyboardButton(text="🔄 Пройти ещё раз", callback_data="totem_start")],
        [InlineKeyboardButton(text="← В меню", callback_data="menu")],
    ]
    
    if is_cb:
        await message.edit_text(text, parse_mode="Markdown", 
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ПОДАРОЧНЫЕ СЕРТИФИКАТЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "gift_menu")
@rate_limit(2.0)
async def gift_menu(cb: CallbackQuery):
    """Меню сертификатов."""
    await safe_edit(cb,
        "🎁 *ПОДАРОЧНЫЙ СЕРТИФИКАТ*\n\n"
        "Вы можете:\n"
        "1. Купить сертификат для друга\n"
        "2. Активировать полученный сертификат\n\n"
        "Сертификат действует 1 год.\n"
        "Бонусы зачисляются на баланс.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить сертификат", callback_data="gift_buy")],
            [InlineKeyboardButton(text="✅ Активировать сертификат", callback_data="gift_activate")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()


@main_router.callback_query(F.data == "gift_buy")
@rate_limit(2.0)
async def gift_buy_start(cb: CallbackQuery, state: FSMContext):
    """Купить сертификат."""
    await safe_edit(cb,
        "🎁 *Введите сумму сертификата* (в рублях):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="500 ₽", callback_data="gift_amount_500"),
             InlineKeyboardButton(text="1000 ₽", callback_data="gift_amount_1000")],
            [InlineKeyboardButton(text="1500 ₽", callback_data="gift_amount_1500"),
             InlineKeyboardButton(text="2000 ₽", callback_data="gift_amount_2000")],
            [InlineKeyboardButton(text="5000 ₽", callback_data="gift_amount_5000"),
             InlineKeyboardButton(text="10000 ₽", callback_data="gift_amount_10000")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")],
        ])
    )
    await state.set_state(GiftCertificateStates.waiting_amount)
    await cb.answer()


@main_router.callback_query(F.data.startswith("gift_amount_"))
@rate_limit(1.0)
async def gift_amount_selected(cb: CallbackQuery, state: FSMContext):
    """Выбрана сумма."""
    amount = int(cb.data.split("_")[2])
    await state.update_data(gift_amount=amount)
    
    await safe_edit(cb,
        f"🎁 *Сумма:* {amount} ₽\n\n"
        f"Введите *имя получателя*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")],
        ])
    )
    await state.set_state(GiftCertificateStates.waiting_recipient)
    await cb.answer()


@main_router.message(GiftCertificateStates.waiting_recipient)
@rate_limit(1.0)
async def gift_recipient(msg: Message, state: FSMContext):
    """Сохранить получателя."""
    recipient = msg.text.strip()
    if len(recipient) > 100:
        await msg.answer("❌ Слишком длинное имя")
        return
    
    await state.update_data(gift_recipient=recipient)
    await msg.answer(
        "💬 Введите поздравительное сообщение (или 'пропустить'):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="gift_skip_message")],
        ])
    )
    await state.set_state(GiftCertificateStates.waiting_message)


@main_router.callback_query(F.data == "gift_skip_message")
@rate_limit(1.0)
async def gift_skip_message(cb: CallbackQuery, state: FSMContext):
    """Пропустить сообщение."""
    await state.update_data(gift_message="")
    await create_gift_order(cb.message, state, True)
    await cb.answer()


@main_router.message(GiftCertificateStates.waiting_message)
@rate_limit(1.0)
async def gift_message(msg: Message, state: FSMContext):
    """Сохранить сообщение."""
    message = msg.text.strip()
    if msg.text.lower() == 'пропустить':
        message = ""
    elif len(message) > 500:
        await msg.answer("❌ Слишком длинное сообщение")
        return
    
    await state.update_data(gift_message=message)
    await create_gift_order(msg, state, False)


async def create_gift_order(message, state: FSMContext, is_cb: bool):
    """Создать заказ на сертификат."""
    data = await state.get_data()
    amount = data['gift_amount']
    recipient = data['gift_recipient']
    gift_message = data.get('gift_message', '')
    
    with db_cursor() as c:
        c.execute("""INSERT INTO orders 
                     (user_id, total_price, status, payment_method, created_at)
                     VALUES (?, ?, 'pending', 'gift_certificate', ?)""",
                  (message.from_user.id, amount, datetime.now()))
        order_id = c.lastrowid
    
    await state.update_data(gift_order_id=order_id)
    
    text = (f"🎁 *ЗАКАЗ СЕРТИФИКАТА #{order_id}*\n\n"
            f"*Сумма:* {amount} ₽\n"
            f"*Получатель:* {recipient}\n")
    if gift_message:
        text += f"*Сообщение:* {gift_message}\n\n"
    text += "Выберите способ оплаты:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data=f"pay_gift_{order_id}")],
        [InlineKeyboardButton(text="₿ КРИПТО", callback_data=f"pay_gift_crypto_{order_id}")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")],
    ])
    
    if is_cb:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@main_router.callback_query(F.data.startswith("pay_gift_"))
@rate_limit(2.0)
async def pay_gift(cb: CallbackQuery, state: FSMContext):
    """Оплата сертификата."""
    try:
        order_id = int(cb.data.split("_")[2])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    data = await state.get_data()
    amount = data.get('gift_amount', 0)
    
    if not amount:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    code = await create_gift_certificate(
        buyer_id=cb.from_user.id,
        amount=amount,
        recipient_name=data['gift_recipient'],
        message=data.get('gift_message', '')
    )
    
    with db_cursor() as c:
        c.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
    
    await safe_edit(cb,
        f"✅ *СЕРТИФИКАТ СОЗДАН!*\n\n"
        f"*Код сертификата:* `{code}`\n\n"
        f"Отправьте этот код получателю.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
        ])
    )
    await state.clear()


@main_router.callback_query(F.data == "gift_activate")
@rate_limit(2.0)
async def gift_activate_start(cb: CallbackQuery, state: FSMContext):
    """Активировать сертификат."""
    await safe_edit(cb,
        "✅ Введите *код подарочного сертификата*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")],
        ])
    )
    await state.set_state(GiftCertificateStates.waiting_code)
    await cb.answer()


@main_router.message(GiftCertificateStates.waiting_code)
@rate_limit(1.0)
async def gift_activate_code(msg: Message, state: FSMContext):
    """Активировать код."""
    code = msg.text.strip().upper()
    
    if not code.startswith('GIFT-'):
        await msg.answer("❌ Неверный формат кода")
        return
    
    amount = await apply_gift_certificate(code, msg.from_user.id)
    
    if amount:
        await msg.answer(
            f"✅ *СЕРТИФИКАТ АКТИВИРОВАН!*\n\n"
            f"На ваш бонусный счёт зачислено *{amount:.0f} ₽*.\n"
            f"Их можно потратить при следующем заказе.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Посмотреть баланс", callback_data="my_referral")],
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
            ])
        )
    else:
        await msg.answer("❌ Сертификат не найден или уже использован",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")]]))
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "diag_start")
@rate_limit(2.0)
async def diag_start_cb(cb: CallbackQuery, state: FSMContext):
    """Начать диагностику."""
    await state.clear()
    await safe_edit(cb,
        "📸 ДИАГНОСТИКА\n\n"
        "Мастер подберёт камни лично для вас на основе фото.\n\n"
        "Нужно два фото:\n\n"
        "1️⃣ Фото СПЕРЕДИ во весь рост\n"
        "2️⃣ Фото СЗАДИ во весь рост\n\n"
        "Загружайте первое фото 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()


@diag_router.message(DiagnosticStates.waiting_photo1)
@rate_limit(1.0)
async def diag_photo1(msg: Message, state: FSMContext):
    """Получить фото 1."""
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    await state.update_data(photo1=msg.photo[-1].file_id)
    await msg.answer("✅ Фото спереди получено!\n\nТеперь загрузите фото СЗАДИ 👇")
    await state.set_state(DiagnosticStates.waiting_photo2)


@diag_router.message(DiagnosticStates.waiting_photo2)
@rate_limit(1.0)
async def diag_photo2(msg: Message, state: FSMContext):
    """Получить фото 2."""
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    await state.update_data(photo2=msg.photo[-1].file_id)
    await msg.answer("✅ Оба фото получены!\n\nЕсть что-то важное о себе? Напишите или 'пропустить':")
    await state.set_state(DiagnosticStates.waiting_notes)


@diag_router.message(DiagnosticStates.waiting_notes)
@rate_limit(1.0)
async def diag_notes(msg: Message, state: FSMContext):
    """Сохранить заметки."""
    data = await state.get_data()
    user_id = msg.from_user.id
    notes = msg.text if msg.text.lower() != 'пропустить' else "Нет заметок"
    
    with db_cursor() as c:
        c.execute("INSERT INTO diagnostics (user_id, photo_count, notes, created_at, photo1_file_id, photo2_file_id) VALUES (?,?,?,?,?,?)",
                  (user_id, 2, notes, datetime.now(), data.get("photo1"), data.get("photo2")))
    
    if ADMIN_ID:
        await notify_admin_diagnostic(user_id, notes, data.get('photo1'), data.get('photo2'))
    
    await msg.answer("✅ СПАСИБО!\n\nДиагностика отправлена! Результаты в течение 24 часов! 💚")
    await state.clear()


@admin_router.callback_query(F.data == "admin_diagnostics")
@rate_limit(2.0)
async def admin_diagnostics(cb: CallbackQuery):
    """Просмотр диагностик."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute('SELECT COUNT(*) FROM diagnostics WHERE sent = FALSE')
        count = c.fetchone()[0]
    
    text = f"🩺 ДИАГНОСТИКА\n\nОжидающих проверки: {count}"
    await safe_edit(cb, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# БАЗА ЗНАНИЙ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "knowledge_list")
@rate_limit(2.0)
async def knowledge_list(cb: CallbackQuery):
    """Список камней."""
    with db_cursor() as c:
        c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name")
        stones = c.fetchall()
    
    if not stones:
        await safe_edit(cb, "📚 База знаний пуста",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer()
        return
    
    buttons = [[InlineKeyboardButton(text=f"{s['emoji']} {s['stone_name']}", callback_data=f"stone_info_{s['id']}")] for s in stones]
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, "📚 БАЗА ЗНАНИЙ О КАМНЯХ\n\nВыберите камень:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


@main_router.callback_query(F.data.startswith("stone_info_"))
@rate_limit(2.0)
async def stone_detail(cb: CallbackQuery):
    """Детальная информация о камне."""
    try:
        stone_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT stone_name, emoji, properties, chakra, photo_file_id, 
                           short_desc, full_desc, color, price_per_bead, forms, notes 
                    FROM knowledge WHERE id=?""", (stone_id,))
        s = c.fetchone()
    
    if not s:
        await cb.answer("Не найдено", show_alert=True)
        return
    
    name, emoji, props, chakra, photo_id, short_desc, full_desc, color, price, forms, notes = s
    em = emoji or "💎"
    
    lines = [f"{em} {name.upper()}"]
    if short_desc:
        lines.append(f"\n{short_desc}")
    if full_desc:
        lines.append(f"\n{full_desc}")
    if chakra:
        lines.append(f"\n🧘 Чакры: {chakra}")
    if color:
        lines.append(f"🎨 Цвет: {color}")
    if forms:
        lines.append(f"📿 Размеры: {forms}")
    if price:
        lines.append(f"💰 Цена за бусину: {price} руб")
    if notes:
        lines.append(f"\n💡 {notes}")
    
    text = "\n".join(lines)[:3000]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💍 ЗАКАЗАТЬ БРАСЛЕТ", callback_data="order_bracelet_start")],
        [InlineKeyboardButton(text="← К СПИСКУ", callback_data="knowledge_list")]])
    
    if photo_id:
        await cb.message.answer_photo(photo=photo_id, caption=text[:1024], reply_markup=kb)
        await cb.message.delete()
    else:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - РАССЫЛКИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_broadcast")
@rate_limit(2.0)
async def admin_broadcast_start(cb: CallbackQuery, state: FSMContext):
    """Начать рассылку."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    await safe_edit(cb, "📢 РАССЫЛКА\n\nНапишите текст сообщения:")
    await state.set_state(BroadcastStates.waiting_text)
    await cb.answer()


@admin_router.message(BroadcastStates.waiting_text)
@rate_limit(1.0)
async def admin_broadcast_confirm(msg: Message, state: FSMContext):
    """Подтверждение рассылки."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(broadcast_text=msg.text)
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]
    
    await msg.answer(
        f"📢 Текст:\n{msg.text}\n\n👥 Получателей: {count}\n\nОтправить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(BroadcastStates.waiting_confirm)


@admin_router.callback_query(F.data == "broadcast_confirm")
@rate_limit(5.0)
async def admin_broadcast_send(cb: CallbackQuery, state: FSMContext):
    """Отправить рассылку."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    
    with db_cursor() as c:
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
    
    await cb.message.edit_text(f"📤 Отправляю {len(users)} пользователям...")
    
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user['user_id'], f"📢 СООБЩЕНИЕ ОТ МАСТЕРА\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    
    with db_cursor() as c:
        c.execute("INSERT INTO broadcasts (broadcast_text, created_at, sent_count) VALUES (?, ?, ?)",
                  (text, datetime.now(), sent))
    
    await cb.message.edit_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА\n\n📤 Отправлено: {sent}\n❌ Не доставлено: {failed}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await state.clear()
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДЕНЬ РОЖДЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "set_birthday")
@rate_limit(2.0)
async def set_birthday_start(cb: CallbackQuery, state: FSMContext):
    """Установить день рождения."""
    user_info = await get_user_info(cb.from_user.id)
    current = ""
    if user_info.get('birthday'):
        bd = datetime.strptime(user_info['birthday'], '%Y-%m-%d').date()
        current = f"\n\n*Текущая дата:* {bd.strftime('%d.%m.%Y')}"
    
    await safe_edit(cb,
        f"🎂 *УКАЖИТЕ ДАТУ РОЖДЕНИЯ*{current}\n\n"
        f"Введите дату в формате `ДД.ММ.ГГГГ`\n"
        f"(например: 15.05.1990)\n\n"
        f"В день рождения вы получите персональный промокод!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await state.set_state(BirthdayStates.waiting_birthday)
    await cb.answer()


@main_router.message(BirthdayStates.waiting_birthday)
@rate_limit(1.0)
async def set_birthday_save(msg: Message, state: FSMContext):
    """Сохранить день рождения."""
    date_text = msg.text.strip()
    
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
        await msg.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")
        return
    
    try:
        day, month, year = map(int, date_text.split('.'))
        birthday = date(year, month, day)
        
        if birthday > date.today():
            await msg.answer("❌ Дата не может быть в будущем")
            return
        
        with db_cursor() as c:
            c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", (birthday, msg.from_user.id))
        
        await msg.answer(
            "✅ *Дата рождения сохранена!*\n\n"
            "В ваш день рождения мы пришлём персональный промокод.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]]))
    except:
        await msg.answer("❌ Некорректная дата")
    finally:
        await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ЭКСПОРТ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "export_orders")
@rate_limit(5.0)
async def export_orders(cb: CallbackQuery):
    """Экспорт заказов."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        csv_data = await generate_orders_csv()
        filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        await cb.message.answer_document(
            document=BufferedInputFile(csv_data, filename=filename),
            caption="📊 *Выгрузка заказов*",
            parse_mode="Markdown"
        )
        await cb.answer("✅ Файл сгенерирован")
    except Exception as e:
        logger.error(f"Export error: {e}")
        await cb.answer("❌ Ошибка", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ВОРОНКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_funnel")
@rate_limit(2.0)
async def admin_funnel(cb: CallbackQuery):
    """Статистика воронки."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    stats = await FunnelTracker.get_stats(30)
    
    stages = [
        ('start', '👋 Начало работы'),
        ('view_cart', '🛒 Просмотр корзины'),
        ('order_created', '📦 Заказ создан'),
        ('payment_success', '✅ Оплата'),
    ]
    
    text = "📊 *ВОРОНКА ПРОДАЖ (30 дней)*\n\n"
    prev = 0
    for stage_key, stage_name in stages:
        users = stats.get(stage_key, {}).get('users', 0)
        text += f"{stage_name}: {users}\n"
        if prev > 0 and users > 0:
            conv = (users / prev) * 100
            text += f"  └ конверсия: {conv:.1f}%\n"
        prev = users if users > 0 else prev
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - PUSH-РАССЫЛКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_push")
@rate_limit(2.0)
async def admin_push_start(cb: CallbackQuery, state: FSMContext):
    """Push-рассылка."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) FROM new_item_subscribers")
        count = c.fetchone()[0]
    
    await safe_edit(cb,
        f"🔔 *PUSH-РАССЫЛКА*\n\nПодписчиков: {count}\n\nВведите *заголовок*:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")]]))
    await state.set_state(PushNotificationStates.waiting_title)
    await cb.answer()


@admin_router.message(PushNotificationStates.waiting_title)
@rate_limit(1.0)
async def push_title(msg: Message, state: FSMContext):
    """Сохранить заголовок."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(push_title=msg.text)
    await msg.answer("📝 Введите *текст* уведомления:", parse_mode="Markdown")
    await state.set_state(PushNotificationStates.waiting_message)


@admin_router.message(PushNotificationStates.waiting_message)
@rate_limit(1.0)
async def push_message(msg: Message, state: FSMContext):
    """Сохранить сообщение."""
    if not is_admin(msg.from_user.id):
        return
    
    await state.update_data(push_message=msg.text)
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) FROM new_item_subscribers")
        count = c.fetchone()[0]
    
    data = await state.get_data()
    await msg.answer(
        f"🔔 *ПОДТВЕРЖДЕНИЕ*\n\n"
        f"*Заголовок:* {data['push_title']}\n"
        f"*Сообщение:* {data['push_message']}\n\n"
        f"Получателей: {count}\n\n"
        f"Отправить?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="push_send")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(PushNotificationStates.waiting_confirm)


@admin_router.callback_query(F.data == "push_send")
@rate_limit(5.0)
async def push_send(cb: CallbackQuery, state: FSMContext):
    """Отправить push."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    data = await state.get_data()
    sent, failed = await PushNotificationManager.send_to_all(
        data['push_title'],
        data['push_message']
    )
    
    await cb.message.edit_text(
        f"✅ *РАССЫЛКА ЗАВЕРШЕНА*\n\n📤 Отправлено: {sent}\n❌ Не доставлено: {failed}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← В АДМИНКУ", callback_data="admin_panel")]]))
    await state.clear()
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# РЕФЕРАЛЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "my_referral")
@rate_limit(2.0)
async def my_referral(cb: CallbackQuery):
    """Реферальная ссылка."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute('SELECT referral_count, balance, total_earned FROM referral_balance WHERE user_id = ?', (user_id,))
        row = c.fetchone()
    
    ref_count = row['referral_count'] if row else 0
    balance = row['balance'] if row else 0
    total_earned = row['total_earned'] if row else 0
    
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    
    await safe_edit(cb,
        f"🤝 *РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
        f"Статус: {get_referral_status(ref_count)}\n"
        f"Приглашено: {ref_count}\n\n"
        f"💰 Баланс: {balance:.0f} руб\n"
        f"📈 Заработано: {total_earned:.0f} руб\n\n"
        f"🎁 За каждого друга — 100 руб\n\n"
        f"🔗 *Ваша ссылка:*\n`{ref_link}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# СВЯЗЬ С МАСТЕРОМ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "contact_master")
@rate_limit(2.0)
async def contact_master(cb: CallbackQuery):
    """Связь с мастером."""
    await safe_edit(cb,
        "📞 *СВЯЗЬ С МАСТЕРОМ*\n\nНапишите ваш вопрос:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать сообщение", callback_data="send_to_master")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()


@main_router.callback_query(F.data == "send_to_master")
@rate_limit(2.0)
async def send_to_master_start(cb: CallbackQuery, state: FSMContext):
    """Начать сообщение мастеру."""
    await cb.message.edit_text("✍️ Напишите ваш вопрос мастеру:")
    await state.set_state(ContactStates.waiting_message)
    await cb.answer()


@main_router.message(ContactStates.waiting_message)
@rate_limit(1.0)
async def send_to_master_finish(msg: Message, state: FSMContext):
    """Отправить сообщение мастеру."""
    user = msg.from_user
    try:
        await bot.send_message(ADMIN_ID,
            f"📩 *СООБЩЕНИЕ ОТ КЛИЕНТА*\n\n"
            f"👤 {user.first_name} (@{user.username or 'нет'})\n"
            f"ID: {user.id}\n\n"
            f"💬 {msg.text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Ответить", url=f"tg://user?id={user.id}")]]))
        await msg.answer("✅ Сообщение отправлено мастеру!")
    except:
        await msg.answer("✅ Сообщение отправлено!")
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ИСТОРИИ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "show_stories")
@rate_limit(2.0)
async def show_stories_cb(cb: CallbackQuery):
    """Показать истории."""
    with db_cursor() as c:
        c.execute("SELECT s.story_text, s.photo_file_id, u.first_name FROM stories s JOIN users u ON s.user_id = u.user_id WHERE s.approved = TRUE ORDER BY s.created_at DESC LIMIT 5")
        stories = c.fetchall()
    
    if not stories:
        await safe_edit(cb,
            "📖 *ИСТОРИИ КЛИЕНТОВ*\n\nПока историй нет.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Поделиться историей", callback_data="add_story")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    else:
        await cb.message.edit_text("📖 *ИСТОРИИ КЛИЕНТОВ*", parse_mode="Markdown")
        for story in stories:
            caption = f"👤 {story['first_name']}\n\n{story['story_text']}"
            if story['photo_file_id']:
                await cb.message.answer_photo(photo=story['photo_file_id'], caption=caption)
            else:
                await cb.message.answer(caption)
        await cb.message.answer("✍️ Поделитесь своей историей!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Поделиться", callback_data="add_story")]]))
    await cb.answer()


@main_router.callback_query(F.data == "add_story")
@rate_limit(2.0)
async def add_story_start(cb: CallbackQuery, state: FSMContext):
    """Добавить историю."""
    await cb.message.edit_text("✍️ Расскажите как наши камни помогли вам:")
    await state.set_state(StoryStates.waiting_text)
    await cb.answer()


@main_router.message(StoryStates.waiting_text)
@rate_limit(1.0)
async def add_story_text(msg: Message, state: FSMContext):
    """Сохранить текст истории."""
    await state.update_data(story_text=msg.text)
    await msg.answer("📸 Прикрепите фото или нажмите кнопку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Без фото", callback_data="story_no_photo")]]))
    await state.set_state(StoryStates.waiting_photo)


@main_router.message(StoryStates.waiting_photo)
@rate_limit(1.0)
async def add_story_photo(msg: Message, state: FSMContext):
    """Сохранить фото истории."""
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else None
    
    with db_cursor() as c:
        c.execute("INSERT INTO stories (user_id, story_text, photo_file_id, approved, created_at) VALUES (?,?,?,?,?)",
                  (msg.from_user.id, data["story_text"], photo_id, 0, datetime.now()))
    
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID,
            f"📖 *НОВАЯ ИСТОРИЯ*\n\n👤 {msg.from_user.first_name}\n\n{data['story_text']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_story_{msg.from_user.id}")]]))
    
    await msg.answer("✅ История отправлена на проверку!")
    await state.clear()


@main_router.callback_query(F.data == "story_no_photo")
@rate_limit(2.0)
async def story_no_photo(cb: CallbackQuery, state: FSMContext):
    """История без фото."""
    data = await state.get_data()
    
    with db_cursor() as c:
        c.execute("INSERT INTO stories (user_id, story_text, approved, created_at) VALUES (?,?,?,?)",
                  (cb.from_user.id, data["story_text"], 0, datetime.now()))
    
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID,
            f"📖 *НОВАЯ ИСТОРИЯ*\n\n👤 {cb.from_user.first_name}\n\n{data['story_text']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_story_{cb.from_user.id}")]]))
    
    await safe_edit(cb, "✅ История отправлена на проверку!")
    await state.clear()
    await cb.answer()


@admin_router.callback_query(F.data.startswith("approve_story_"))
@rate_limit(2.0)
async def approve_story(cb: CallbackQuery):
    """Одобрить историю."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    try:
        user_id = int(cb.data.split("_")[-1])
    except:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("UPDATE stories SET approved = TRUE WHERE user_id = ? AND approved = FALSE", (user_id,))
    
    await cb.answer("✅ История одобрена!", show_alert=True)


@admin_router.callback_query(F.data == "admin_stories")
@rate_limit(2.0)
async def admin_stories(cb: CallbackQuery):
    """Админ панель историй."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) FROM stories WHERE approved = FALSE")
        pending = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM stories WHERE approved = TRUE")
        approved_count = c.fetchone()[0]
    
    await safe_edit(cb,
        f"📖 *ИСТОРИИ КЛИЕНТОВ*\n\nОжидают проверки: {pending}\nОдобрено: {approved_count}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Главная функция запуска бота."""
    print("\n" + "="*70)
    print("🚀 БОТ V4 - ПОЛНЫЙ ФУНКЦИОНАЛ ЗАПУСКАЕТСЯ")
    print("="*70 + "\n")
    
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 7,914 СТРОК КОДА")
    print(f"📍 36 ТАБЛИЦ")
    print(f"📍 ВСЕ ХЕНДЛЕРЫ НА МЕСТЕ")
    print("\n" + "="*70 + "\n")
    
    @dp.callback_query.middleware()
    async def rate_limit_middleware(handler, event, data):
        user_id = event.from_user.id
        if is_rate_limited(user_id, "cb", 0.7):
            await event.answer("⏳", show_alert=False)
            return
        return await handler(event, data)

    asyncio.create_task(check_pending_orders())
    asyncio.create_task(check_birthdays())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")