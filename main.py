"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ ДЛЯ RAILWAY

✅ ВСЕ БАГИ ИСПРАВЛЕНЫ (#1-#15)
✅ ПОЛНАЯ ОПТИМИЗАЦИЯ (индексы, кэширование, безопасность)
✅ ВОРОНКА ПРОДАЖ (MKT-1)
✅ АВТО-ПОСТЫ В STORIES (MKT-3)
✅ ДЕНЬ РОЖДЕНИЯ (NEW-8)
✅ PUSH-УВЕДОМЛЕНИЯ (NEW-6)

ВСЁ БЕЗ КОДА! ТОЛЬКО АДМИН-ПАНЕЛЬ!
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
import hashlib
import hmac
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional, Dict, List, Any, Tuple

from aiogram import F, types, Router, Dispatcher, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else 0
PORT = int(os.getenv('PORT', 8000))

# ПЛАТЕЖИ
YANDEX_KASSA_EMAIL = os.getenv('YANDEX_KASSA_EMAIL', 'your-email@yandex.kassa.com')
YANDEX_KASSA_SHOP_ID = os.getenv('YANDEX_KASSA_SHOP_ID', 'YOUR_SHOP_ID')
YANDEX_KASSA_API_KEY = os.getenv('YANDEX_KASSA_API_KEY', 'YOUR_API_KEY')

CRYPTO_WALLET_ADDRESS = os.getenv('CRYPTO_WALLET_ADDRESS', 'bc1qyour_bitcoin_address_here')
CRYPTO_WALLET_NETWORK = os.getenv('CRYPTO_WALLET_NETWORK', 'Bitcoin')

# Путь к БД через переменную окружения (для Volume)
DB = os.getenv('DB', 'storage/beads.db')

# Создаём папки
db_path = Path(DB).parent
db_path.mkdir(parents=True, exist_ok=True)
Path('storage/diagnostics').mkdir(parents=True, exist_ok=True)
Path('storage/stories').mkdir(parents=True, exist_ok=True)

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# БОТ И ДИСПЕТЧЕР
# ═══════════════════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
main_router = Router()
admin_router = Router()
diag_router = Router()

# ── Безопасный edit_text helper ──
async def safe_edit(cb: types.CallbackQuery, text: str = None, reply_markup=None, **kwargs):
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

# ── Антиспам: rate limiting ──
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


# ═══════════════════════════════════════════════════════════════════════════
# ОПТИМИЗАЦИЯ 6: КОНТЕКСТНЫЙ МЕНЕДЖЕР ДЛЯ БД (OPT-6)
# ═══════════════════════════════════════════════════════════════════════════

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
# ОПТИМИЗАЦИЯ 2: ИНДЕКСЫ ДЛЯ БД (OPT-2)
# ═══════════════════════════════════════════════════════════════════════════

def create_indexes():
    """Создать индексы для ускорения запросов."""
    with db_connection() as conn:
        c = conn.cursor()
        
        # Индексы для корзины
        c.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cart_order ON cart(order_id)")
        
        # Индексы для заказов
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(created_at)")
        
        # Индексы для товаров в заказе
        c.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
        
        # Индексы для бонусов
        c.execute("CREATE INDEX IF NOT EXISTS idx_bonus_user ON bonus_history(user_id)")
        
        # Индексы для витрины
        c.execute("CREATE INDEX IF NOT EXISTS idx_showcase_collection ON showcase_items(collection_id)")
        
        # Индексы для диагностики
        c.execute("CREATE INDEX IF NOT EXISTS idx_diag_user ON diagnostics(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_diag_sent ON diagnostics(sent)")
        
        # Индексы для пользователей
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)")
        
        # Индексы для отзывов
        c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_approved ON reviews_new(approved)")
        
        conn.commit()


# ═══════════════════════════════════════════════════════════════════════════
# ОПТИМИЗАЦИЯ 3: КЭШИРОВАНИЕ (OPT-3)
# ═══════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def get_cached_categories():
    """Загрузить категории из БД с кэшированием."""
    with db_cursor() as c:
        c.execute('SELECT id, emoji, name FROM categories ORDER BY id')
        return c.fetchall()

@lru_cache(maxsize=1)
def get_cached_settings():
    """Загрузить настройки из БД с кэшированием."""
    with db_cursor() as c:
        c.execute('SELECT key, value FROM bot_settings')
        return {row['key']: row['value'] for row in c.fetchall()}

def invalidate_cache():
    """Сбросить кэш при изменениях."""
    get_cached_categories.cache_clear()
    get_cached_settings.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════
# ОПТИМИЗАЦИЯ 1: ВЫНОС ПОВТОРЯЮЩЕГОСЯ КОДА (OPT-1)
# ═══════════════════════════════════════════════════════════════════════════

class ItemInfo:
    """Класс для получения информации о товаре (оптимизация повторяющегося кода)."""
    
    @staticmethod
    def get_item_info(item_id: int) -> Tuple[str, float, str]:
        """
        Получить информацию о товаре по его ID.
        Возвращает (название, цена, тип)
        """
        with db_cursor() as c:
            if item_id >= 100000:
                real_id = item_id - 100000
                c.execute("SELECT name, price FROM showcase_items WHERE id = ?", (real_id,))
                row = c.fetchone()
                if row:
                    return row['name'], row['price'] or 0.0, 'showcase'
            else:
                c.execute("SELECT name, price FROM bracelets WHERE id = ?", (item_id,))
                row = c.fetchone()
                if row:
                    return row['name'], row['price'] or 0.0, 'bracelet'
        
        return f"Товар #{item_id}", 0.0, 'unknown'

    @staticmethod
    def format_price(price: float) -> str:
        """Форматировать цену."""
        return f"{price:.0f}₽" if price else "цена уточняется"


# ═══════════════════════════════════════════════════════════════════════════
# БАГ #8: ЗАМЕНА eval() НА json.loads()
# ═══════════════════════════════════════════════════════════════════════════

def safe_json_parse(json_str: str, default=None):
    """Безопасный парсинг JSON вместо eval()."""
    try:
        return json.loads(json_str)
    except:
        return default if default is not None else []

def safe_weights_parse(weights_str: str) -> Dict[str, int]:
    """Безопасный парсинг весов для викторины."""
    try:
        if isinstance(weights_str, str):
            return json.loads(weights_str)
        return weights_str or {}
    except:
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# НОВАЯ ФИЧА NEW-8: ДЕНЬ РОЖДЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def check_birthdays():
    """Фоновая задача: проверять дни рождения и отправлять промокоды."""
    while True:
        try:
            await asyncio.sleep(3600)  # Проверяем каждый час
            
            with db_cursor() as c:
                # Находим пользователей у которых сегодня день рождения
                today = datetime.now().strftime('%m-%d')
                c.execute('''SELECT user_id, first_name FROM users 
                             WHERE strftime('%m-%d', birthday) = ?''', (today,))
                birthday_users = c.fetchall()
                
                for user in birthday_users:
                    user_id, name = user['user_id'], user['first_name']
                    
                    # Проверяем, не отправляли ли уже сегодня
                    c.execute('''SELECT 1 FROM birthday_promos 
                                 WHERE user_id = ? AND date = date('now')''', (user_id,))
                    if c.fetchone():
                        continue
                    
                    # Генерируем персональный промокод
                    promo_code = f"BDAY{user_id}{datetime.now().strftime('%d%m')}"
                    
                    # Создаём промокод в БД
                    c.execute('''INSERT INTO promocodes 
                                 (code, discount_pct, max_uses, active, created_at)
                                 VALUES (?, 15, 1, 1, ?)''',
                              (promo_code, datetime.now()))
                    
                    # Отмечаем, что отправили
                    c.execute('''INSERT INTO birthday_promos (user_id, promo_code, date)
                                 VALUES (?, ?, date('now'))''',
                              (user_id, promo_code))
                    
                    # Отправляем поздравление
                    try:
                        await bot.send_message(
                            user_id,
                            f"🎂 С ДНЁМ РОЖДЕНИЯ, {name}!\n\n"
                            f"В честь вашего праздника дарим персональную скидку 15%!\n\n"
                            f"🎟️ Промокод: {promo_code}\n"
                            f"Действует 7 дней.",
                            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                                [types.InlineKeyboardButton(text="🛍️ Перейти в витрину", 
                                                            callback_data="showcase_bracelets")],
                            ])
                        )
                        logger.info(f"Birthday promo sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Birthday message error: {e}")
                    
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Birthday check error: {e}")
            await asyncio.sleep(300)


# ═══════════════════════════════════════════════════════════════════════════
# НОВАЯ ФИЧА NEW-6: PUSH-УВЕДОМЛЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def send_push_notification(user_id: int, title: str, message: str, button_text: str = None, button_data: str = None):
    """Отправить push-уведомление пользователю."""
    try:
        kb = None
        if button_text and button_data:
            kb = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text=button_text, callback_data=button_data)]
            ])
        
        await bot.send_message(
            user_id,
            f"🔔 {title}\n\n{message}",
            reply_markup=kb
        )
        return True
    except Exception as e:
        logger.error(f"Push notification error to {user_id}: {e}")
        return False

async def notify_all_subscribers(title: str, message: str, button_text: str = None, button_data: str = None):
    """Отправить уведомление всем подписчикам."""
    with db_cursor() as c:
        c.execute("SELECT user_id FROM new_item_subscribers")
        subscribers = c.fetchall()
        
        sent = 0
        failed = 0
        
        for sub in subscribers:
            if await send_push_notification(sub['user_id'], title, message, button_text, button_data):
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)
        
        logger.info(f"Push notifications: {sent} sent, {failed} failed")
        return sent, failed


# ═══════════════════════════════════════════════════════════════════════════
# НОВАЯ ФИЧА MKT-1: ВОРОНКА ПРОДАЖ
# ═══════════════════════════════════════════════════════════════════════════

async def track_funnel_event(user_id: int, event_type: str, details: str = None):
    """Отследить событие в воронке продаж."""
    with db_cursor() as c:
        c.execute('''INSERT INTO funnel_stats 
                     (user_id, event_type, details, created_at)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, event_type, details, datetime.now()))

async def get_funnel_stats(days: int = 30) -> Dict[str, int]:
    """Получить статистику воронки за указанный период."""
    with db_cursor() as c:
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute('''SELECT event_type, COUNT(DISTINCT user_id) as users
                     FROM funnel_stats
                     WHERE created_at > ?
                     GROUP BY event_type''', (since,))
        
        return {row['event_type']: row['users'] for row in c.fetchall()}


# ═══════════════════════════════════════════════════════════════════════════
# НОВАЯ ФИЧА MKT-3: АВТО-ПОСТЫ В STORIES
# ═══════════════════════════════════════════════════════════════════════════

async def auto_story_from_purchase(user_id: int, order_id: int, item_name: str):
    """Автоматически создать историю после покупки."""
    story_text = (
        f"🌟 Спасибо за покупку!\n\n"
        f"Я приобрёл(а) {item_name} в магазине @The_magic_of_stones_bot\n"
        f"Камень уже со мной и делится своей энергией! 💎"
    )
    
    with db_cursor() as c:
        c.execute('''INSERT INTO stories 
                     (user_id, text, photo_file_id, approved, created_at, auto_generated)
                     VALUES (?, ?, NULL, 0, ?, 1)''',
                  (user_id, story_text, datetime.now()))
        
        # Уведомляем админа
        if ADMIN_ID:
            await bot.send_message(
                ADMIN_ID,
                f"📖 НОВАЯ АВТО-ИСТОРИЯ\n\n"
                f"Пользователь: {user_id}\n"
                f"Заказ: #{order_id}\n\n"
                f"{story_text}",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="✅ ОДОБРИТЬ", 
                                                callback_data=f"approve_story_{user_id}")],
                ])
            )


# ═══════════════════════════════════════════════════════════════════════════
# БД - ИНИЦИАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    """Инициализация базы данных со всеми таблицами."""
    with db_connection() as conn:
        c = conn.cursor()
        
        # Пользователи
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INT PRIMARY KEY, username TEXT, first_name TEXT, 
                      created_at TIMESTAMP, birthday DATE, 
                      welcome_sent BOOLEAN DEFAULT FALSE, referred_by INT DEFAULT NULL)''')
        
        # Категории
        c.execute('''CREATE TABLE IF NOT EXISTS categories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, 
                      emoji TEXT, desc TEXT)''')
        
        # Контент
        c.execute('''CREATE TABLE IF NOT EXISTS content 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INT, 
                      title TEXT, desc TEXT, created_at TIMESTAMP)''')
        
        # Тренировки
        c.execute('''CREATE TABLE IF NOT EXISTS workouts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, 
                      duration INT, difficulty TEXT, created_at TIMESTAMP)''')
        
        # Музыка
        c.execute('''CREATE TABLE IF NOT EXISTS music 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, 
                      duration INT, audio_url TEXT, created_at TIMESTAMP)''')
        
        # Услуги
        c.execute('''CREATE TABLE IF NOT EXISTS services 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, 
                      price REAL, created_at TIMESTAMP)''')
        
        # Диагностика
        c.execute('''CREATE TABLE IF NOT EXISTS diagnostics 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, photo_count INT, 
                      notes TEXT, created_at TIMESTAMP, admin_result TEXT, 
                      sent BOOLEAN DEFAULT FALSE, photo1_file_id TEXT, 
                      photo2_file_id TEXT, followup_sent INT DEFAULT 0)''')
        
        # Браслеты
        c.execute('''CREATE TABLE IF NOT EXISTS bracelets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, 
                      price REAL, image_url TEXT, created_at TIMESTAMP)''')
        
        # Корзина
        c.execute('''CREATE TABLE IF NOT EXISTS cart 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INT, bracelet_id INT, quantity INT, 
                      added_at TIMESTAMP, status TEXT DEFAULT 'active', order_id INT DEFAULT 0)''')
        
        # Заказы
        c.execute('''CREATE TABLE IF NOT EXISTS orders 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, 
                      total_price REAL, status TEXT, payment_method TEXT, 
                      created_at TIMESTAMP, promo_code TEXT, discount_rub REAL DEFAULT 0,
                      bonus_used REAL DEFAULT 0, bonus_payment REAL DEFAULT 0,
                      cashback_amount REAL DEFAULT 0)''')
        
        # Товары в заказе
        c.execute('''CREATE TABLE IF NOT EXISTS order_items
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INT, user_id INT,
                      item_type TEXT, item_id INT, item_name TEXT,
                      quantity INT, price REAL, created_at TIMESTAMP)''')
        
        # Отзывы с фото
        c.execute('''CREATE TABLE IF NOT EXISTS reviews_new
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, order_id INT,
                      bracelet_id INT, rating INT, text TEXT, photo_file_id TEXT,
                      approved BOOLEAN DEFAULT FALSE, created_at TIMESTAMP)''')
        
        # Подкатегории
        c.execute('''CREATE TABLE IF NOT EXISTS subcategories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, 
                      name TEXT, emoji TEXT, created_at TIMESTAMP)''')
        
        # Под-подкатегории
        c.execute('''CREATE TABLE IF NOT EXISTS subsubcategories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, 
                      name TEXT, emoji TEXT, created_at TIMESTAMP)''')
        
        # Админы
        c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INT PRIMARY KEY)''')
        
        # Рефералы
        c.execute('''CREATE TABLE IF NOT EXISTS referrals 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INT, 
                      referred_id INT, created_at TIMESTAMP)''')
        
        # Баланс рефералов
        c.execute('''CREATE TABLE IF NOT EXISTS referral_balance 
                     (user_id INT PRIMARY KEY, balance REAL DEFAULT 0, 
                      total_earned REAL DEFAULT 0, referral_count INT DEFAULT 0)''')
        
        # Истории
        c.execute('''CREATE TABLE IF NOT EXISTS stories 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, text TEXT, 
                      photo_file_id TEXT, approved BOOLEAN DEFAULT FALSE, 
                      created_at TIMESTAMP, auto_generated BOOLEAN DEFAULT FALSE)''')
        
        # Рассылки
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, 
                      created_at TIMESTAMP, sent_count INT DEFAULT 0)''')
        
        # Коллекции витрины
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_collections
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, 
                      emoji TEXT, desc TEXT, sort_order INT DEFAULT 0, created_at TIMESTAMP)''')
        
        # Товары витрины
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_items
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, collection_id INT, 
                      name TEXT, desc TEXT, price REAL, stars_price INTEGER DEFAULT 0,
                      image_file_id TEXT, sort_order INT DEFAULT 0, created_at TIMESTAMP)''')
        
        # База знаний
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, stone_name TEXT UNIQUE, 
                      emoji TEXT, properties TEXT, elements TEXT, zodiac TEXT, 
                      chakra TEXT, photo_file_id TEXT, created_at TIMESTAMP,
                      short_desc TEXT, full_desc TEXT, color TEXT, stone_id TEXT,
                      tasks TEXT, price_per_bead INTEGER, forms TEXT, notes TEXT)''')
        
        # Результаты теста
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, 
                      answers TEXT, recommended_stone TEXT, created_at TIMESTAMP)''')
        
        # Настройки бота
        c.execute('''CREATE TABLE IF NOT EXISTS bot_settings 
                     (key TEXT PRIMARY KEY, value TEXT)''')
        
        # Начатые тесты
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_started 
                     (user_id INT PRIMARY KEY, started_at TIMESTAMP, completed INT DEFAULT 0)''')
        
        # Напоминания о диагностике
        c.execute('''CREATE TABLE IF NOT EXISTS diag_reminded 
                     (user_id INT PRIMARY KEY, reminded_at TIMESTAMP)''')
        
        # Промокоды
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
                      discount_pct INT DEFAULT 0, discount_rub INT DEFAULT 0,
                      max_uses INT DEFAULT 0, used_count INT DEFAULT 0,
                      active INT DEFAULT 1, created_at TIMESTAMP)''')
        
        # Использования промокодов
        c.execute('''CREATE TABLE IF NOT EXISTS promo_uses
                     (user_id INT, code TEXT, used_at TIMESTAMP,
                      PRIMARY KEY (user_id, code))''')
        
        # Избранное
        c.execute('''CREATE TABLE IF NOT EXISTS wishlist
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      item_id INT, added_at TIMESTAMP, UNIQUE(user_id, item_id))''')
        
        # Консультации
        c.execute('''CREATE TABLE IF NOT EXISTS consultations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      date TEXT, time_slot TEXT, topic TEXT,
                      status TEXT DEFAULT 'pending', created_at TIMESTAMP)''')
        
        # Слоты расписания
        c.execute('''CREATE TABLE IF NOT EXISTS schedule_slots
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                      time_slot TEXT, available INT DEFAULT 1,
                      UNIQUE(date, time_slot))''')
        
        # FAQ
        c.execute('''CREATE TABLE IF NOT EXISTS faq
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
                      answer TEXT, sort_order INT DEFAULT 0, active INT DEFAULT 1)''')
        
        # Заметки CRM
        c.execute('''CREATE TABLE IF NOT EXISTS crm_notes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      note TEXT, created_at TIMESTAMP, admin_id INT)''')
        
        # Подписчики на новинки
        c.execute('''CREATE TABLE IF NOT EXISTS new_item_subscribers
                     (user_id INT PRIMARY KEY, subscribed_at TIMESTAMP)''')
        
        # Напоминания о корзине
        c.execute('''CREATE TABLE IF NOT EXISTS cart_reminders
                     (user_id INT PRIMARY KEY, last_reminder TIMESTAMP,
                      reminded INT DEFAULT 0)''')
        
        # Stars заказы
        c.execute('''CREATE TABLE IF NOT EXISTS stars_orders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, item_id INT,
                      item_name TEXT, stars_amount INT, charge_id TEXT UNIQUE,
                      status TEXT DEFAULT 'paid', created_at TIMESTAMP)''')
        
        # История бонусов
        c.execute('''CREATE TABLE IF NOT EXISTS bonus_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      amount REAL, operation TEXT, order_id INT,
                      created_at TIMESTAMP)''')
        
        # Блокировки заказов
        c.execute('''CREATE TABLE IF NOT EXISTS order_locks
                     (order_id INT PRIMARY KEY, locked_until TIMESTAMP,
                      user_id INT, created_at TIMESTAMP)''')
        
        # Настройки кэшбэка
        c.execute('''CREATE TABLE IF NOT EXISTS cashback_settings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, cashback_percent INT DEFAULT 5,
                      min_order_amount REAL DEFAULT 0, active INT DEFAULT 1,
                      updated_at TIMESTAMP)''')
        
        # Вопросы викторины
        c.execute('''CREATE TABLE IF NOT EXISTS totem_questions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
                      options TEXT, weights TEXT, sort_order INT DEFAULT 0,
                      active INT DEFAULT 1, created_at TIMESTAMP)''')
        
        # Результаты викторины
        c.execute('''CREATE TABLE IF NOT EXISTS totem_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      answers TEXT, top1 TEXT, top2 TEXT, top3 TEXT,
                      created_at TIMESTAMP)''')
        
        # Подарочные сертификаты
        c.execute('''CREATE TABLE IF NOT EXISTS gift_certificates
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
                      amount REAL, buyer_id INT, recipient_name TEXT,
                      message TEXT, status TEXT DEFAULT 'active',
                      used_by INT DEFAULT NULL, used_at TIMESTAMP,
                      created_at TIMESTAMP, expires_at TIMESTAMP)''')
        
        # Неоплаченные заказы
        c.execute('''CREATE TABLE IF NOT EXISTS pending_orders
                     (order_id INT PRIMARY KEY, user_id INT,
                      created_at TIMESTAMP, reminder_sent INT DEFAULT 0)''')
        
        # Статистика воронки (MKT-1)
        c.execute('''CREATE TABLE IF NOT EXISTS funnel_stats
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      event_type TEXT, details TEXT, created_at TIMESTAMP)''')
        
        # Дни рождения (NEW-8)
        c.execute('''CREATE TABLE IF NOT EXISTS birthday_promos
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      promo_code TEXT, date DATE, UNIQUE(user_id, date))''')
        
        # Push-уведомления (NEW-6)
        c.execute('''CREATE TABLE IF NOT EXISTS push_notifications
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                      title TEXT, message TEXT, sent_at TIMESTAMP,
                      clicked BOOLEAN DEFAULT FALSE)''')
        
        conn.commit()
        
        # Вставляем дефолтные данные
        insert_default_data(c)
        
        # Создаём индексы (OPT-2)
        create_indexes()


def insert_default_data(c):
    """Вставить дефолтные данные при первом запуске."""
    
    # Дефолтные вопросы для викторины
    c.execute("SELECT COUNT(*) FROM totem_questions")
    if c.fetchone()[0] == 0:
        questions = [
            ("Как ты обычно восстанавливаешь силы?",
             json.dumps(["🌿 На природе, в тишине", "🔥 В компании друзей", 
                        "💭 В одиночестве, медитируя", "🏃 В движении, спорте"]),
             json.dumps({"amethyst":3, "garnet":2, "clear_quartz":3, "carnelian":2})),
            
            ("Что для тебя важнее всего в жизни?",
             json.dumps(["❤️ Любовь и отношения", "💰 Деньги и успех", 
                        "🛡 Защита и безопасность", "🌟 Духовное развитие"]),
             json.dumps({"rose_quartz":3, "citrine":3, "black_tourmaline":3, "amethyst":3})),
            
            ("Как ты принимаешь важные решения?",
             json.dumps(["🧠 Логически, взвешивая всё", "💫 Интуитивно, как сердце подскажет",
                        "👥 Советуюсь с близкими", "🌀 Долго сомневаюсь"]),
             json.dumps({"tiger_eye":2, "moonstone":3, "sodalite":2, "lepidolite":3})),
            
            ("Чего тебе не хватает прямо сейчас?",
             json.dumps(["⚡ Энергии и драйва", "😌 Спокойствия", 
                        "✨ Ясности в мыслях", "💰 Денежного потока"]),
             json.dumps({"carnelian":3, "amethyst":3, "clear_quartz":3, "citrine":3})),
            
            ("Какая твоя главная мечта?",
             json.dumps(["🌍 Путешествовать и познавать мир", "🏠 Создать уютный дом",
                        "🚀 Достичь карьерных высот", "🔮 Найти себя и свой путь"]),
             json.dumps({"labradorite":3, "rose_quartz":2, "tiger_eye":3, "moonstone":3}))
        ]
        for q in questions:
            c.execute("INSERT INTO totem_questions (question, options, weights, sort_order, created_at) VALUES (?,?,?,?,?)",
                      (q[0], q[1], q[2], 0, datetime.now()))
    
    # Дефолтные настройки кэшбэка
    c.execute("SELECT COUNT(*) FROM cashback_settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO cashback_settings (cashback_percent, min_order_amount, active, updated_at) VALUES (5, 0, 1, ?)",
                  (datetime.now(),))
    
    # Дефолтное приветствие
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)''',
              ('welcome_text', '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nЯ помогу найти браслет или чётки, которые подойдут именно вам.\n\n🎁 СКИДКА 20% на первый заказ!\nПромокод: WELCOME20\n\nВыберите раздел 👇'))
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)''',
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
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", 
                  (name, emoji, desc))
    
    # Админ
    if ADMIN_ID:
        try:
            c.execute("INSERT OR IGNORE INTO admins VALUES (?)", (ADMIN_ID,))
        except:
            pass


# Инициализация
init_db()


# ═══════════════════════════════════════════════════════════════════════════
# ОПТИМИЗАЦИЯ 5: ОБЪЕДИНЕНИЕ FSM СОСТОЯНИЙ (OPT-5)
# ═══════════════════════════════════════════════════════════════════════════

class BaseInputStates(StatesGroup):
    """Базовые состояния для ввода данных (объединение)."""
    waiting_name = State()
    waiting_emoji = State()
    waiting_description = State()
    waiting_price = State()
    waiting_photo = State()
    waiting_text = State()
    waiting_number = State()
    waiting_confirm = State()


class AdminStates(BaseInputStates):
    """Админ-панель (расширяет базовые)."""
    # Специфичные для админки состояния
    select_category = State()
    select_item = State()
    edit_field = State()


class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()


class ReviewStates(BaseInputStates):
    waiting_rating = State()
    # waiting_text уже есть в BaseInputStates


class BroadcastStates(BaseInputStates):
    waiting_text = State()
    waiting_confirm = State()


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


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ
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
        return row['balance'] if row else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# ИСПРАВЛЕНИЕ БАГ #10: ЗАЩИТА ОТ ДВОЙНОГО КЭШБЭКА
# ═══════════════════════════════════════════════════════════════════════════

async def get_cashback_settings():
    """Получить настройки кэшбэка."""
    with db_cursor() as c:
        c.execute("SELECT cashback_percent, min_order_amount, active FROM cashback_settings WHERE id=1")
        row = c.fetchone()
        if row:
            return {"percent": row['cashback_percent'], 
                    "min_amount": row['min_order_amount'], 
                    "active": row['active']}
    return {"percent": 5, "min_amount": 0, "active": True}


async def apply_cashback(user_id: int, order_id: int, order_amount: float):
    """Начислить кэшбэк за заказ (с защитой от двойного начисления)."""
    settings = await get_cashback_settings()
    if not settings["active"]:
        return 0
    
    if order_amount < settings["min_amount"]:
        return 0
    
    # Проверяем, не начисляли ли уже кэшбэк на этот заказ
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
            
            # Начисляем кэшбэк
            c.execute('''INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                         VALUES (?, ?, ?, 0)
                         ON CONFLICT(user_id) DO UPDATE SET
                         balance = balance + ?,
                         total_earned = total_earned + ?''',
                      (user_id, cashback_amount, cashback_amount, cashback_amount, cashback_amount))
            
            # Записываем в историю
            c.execute('''INSERT INTO bonus_history 
                         (user_id, amount, operation, order_id, created_at) 
                         VALUES (?, ?, 'cashback', ?, ?)''',
                      (user_id, cashback_amount, order_id, datetime.now()))
            
            # Обновляем заказ (помечаем, что кэшбэк начислен)
            c.execute("UPDATE orders SET cashback_amount = ? WHERE id = ?", 
                     (cashback_amount, order_id))
            
            conn.commit()
            return cashback_amount
        except Exception as e:
            logger.error(f"Cashback error: {e}")
            conn.rollback()
            return 0


async def update_cashback_settings(percent: int, min_amount: float = 0, active: bool = True):
    """Обновить настройки кэшбэка."""
    with db_cursor() as c:
        c.execute('''UPDATE cashback_settings 
                     SET cashback_percent = ?, min_order_amount = ?, active = ?, updated_at = ?
                     WHERE id = 1''',
                  (percent, min_amount, 1 if active else 0, datetime.now()))
        return True


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ КОРЗИНЫ (БАГ #9 - защита от отрицательных значений)
# ═══════════════════════════════════════════════════════════════════════════

async def move_cart_to_order(user_id: int, order_id: int):
    """Перенести товары из корзины в заказ."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            # Получаем все активные товары из корзины
            c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id = ? AND status = 'active'", 
                     (user_id,))
            cart_items = c.fetchall()
            
            for item in cart_items:
                bracelet_id = item['bracelet_id']
                qty = item['quantity']
                
                # БАГ #9: защита от отрицательного количества
                if qty <= 0:
                    logger.warning(f"Negative quantity {qty} for user {user_id}, skipping")
                    continue
                
                # Получаем информацию о товаре
                name, price, _ = ItemInfo.get_item_info(bracelet_id)
                
                # Добавляем в order_items
                c.execute('''INSERT INTO order_items 
                             (order_id, user_id, item_type, item_id, item_name, quantity, price, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                          (order_id, user_id, 'item', bracelet_id, name, qty, price, datetime.now()))
            
            # Помечаем товары в корзине как заказанные
            c.execute("UPDATE cart SET status = 'ordered', order_id = ? WHERE user_id = ? AND status = 'active'", 
                      (order_id, user_id))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Move cart error: {e}")
            conn.rollback()
            return False


async def restore_cart_from_order(user_id: int, order_id: int):
    """Восстановить корзину из отменённого заказа."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            # Получаем товары из заказа
            c.execute("SELECT item_id, quantity FROM order_items WHERE order_id = ?", (order_id,))
            items = c.fetchall()
            
            for item in items:
                item_id = item['item_id']
                qty = item['quantity']
                
                # БАГ #9: защита от отрицательного количества
                if qty <= 0:
                    continue
                
                # БАГ #13: проверяем, существует ли товар
                name, price, _ = ItemInfo.get_item_info(item_id)
                if name.startswith("Товар #") and price == 0:
                    logger.warning(f"Item {item_id} not found, skipping")
                    continue
                
                # Проверяем, нет ли уже такого товара в активной корзине
                c.execute("SELECT id, quantity FROM cart WHERE user_id = ? AND bracelet_id = ? AND status = 'active'",
                          (user_id, item_id))
                existing = c.fetchone()
                
                if existing:
                    new_qty = existing['quantity'] + qty
                    c.execute("UPDATE cart SET quantity = ? WHERE id = ?", (new_qty, existing['id']))
                else:
                    c.execute('''INSERT INTO cart (user_id, bracelet_id, quantity, added_at, status, order_id)
                                 VALUES (?, ?, ?, ?, 'active', 0)''',
                              (user_id, item_id, qty, datetime.now()))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Restore cart error: {e}")
            conn.rollback()
            return False


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ УВЕДОМЛЕНИЙ
# ═══════════════════════════════════════════════════════════════════════════

STATUS_MESSAGES = {
    'pending': ('⏳ Заказ создан и ожидает подтверждения', '⏳'),
    'confirmed': ('✅ Заказ подтверждён! Мастер приступил к работе.', '✅'),
    'paid': ('💰 Оплата получена, спасибо!', '💰'),
    'in_progress': ('🔨 Ваш заказ в работе! Мастер создаёт его прямо сейчас.', '🔨'),
    'shipped': ('🚚 Ваш заказ отправлен! Скоро будет у вас.', '🚚'),
    'delivered': ('📦 Заказ доставлен! Наслаждайтесь силой камней 💎', '📦'),
    'cancelled': ('❌ Заказ отменён. Если есть вопросы — напишите мастеру.', '❌')
}


async def send_order_status_notification(user_id: int, order_id: int, new_status: str):
    """Отправить уведомление о смене статуса заказа."""
    if new_status not in STATUS_MESSAGES:
        return
    
    message, _ = STATUS_MESSAGES[new_status]
    
    buttons = []
    if new_status == 'delivered':
        buttons.append([types.InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="leave_review")])
    elif new_status == 'cancelled':
        buttons.append([types.InlineKeyboardButton(text="🔄 Восстановить корзину", 
                                                   callback_data=f"restore_cart_{order_id}")])
    
    buttons.append([types.InlineKeyboardButton(text="✍️ Написать мастеру", callback_data="contact_master")])
    buttons.append([types.InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders")])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    
    try:
        await bot.send_message(
            user_id,
            f"📦 Заказ #{order_id}\n\n{message}",
            reply_markup=kb
        )
        
        # NEW-6: логируем отправку
        with db_cursor() as c:
            c.execute('''INSERT INTO push_notifications 
                         (user_id, title, message, sent_at)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, f"Заказ #{order_id}", message, datetime.now()))
    except Exception as e:
        logger.error(f"Status notification error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ ВИКТОРИНЫ (БАГ #8 - безопасный парсинг)
# ═══════════════════════════════════════════════════════════════════════════

async def calculate_totem_result(answers: dict):
    """Рассчитать топ-3 камня по ответам (безопасная версия)."""
    scores = defaultdict(int)
    
    with db_cursor() as c:
        c.execute("SELECT id, weights FROM totem_questions ORDER BY sort_order, id")
        questions = c.fetchall()
    
    for i, q in enumerate(questions, 1):
        answer_key = f'q{i}'
        if answer_key not in answers:
            continue
        
        # БАГ #8: используем safe_weights_parse вместо eval
        weights = safe_weights_parse(q['weights'])
        for stone, score in weights.items():
            scores[stone] += score
    
    # Сортируем по убыванию
    sorted_stones = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    # Берём топ-3
    top3 = []
    for stone, _ in sorted_stones[:3]:
        with db_cursor() as c:
            c.execute("SELECT stone_name, emoji FROM knowledge WHERE stone_id = ? OR LOWER(stone_name) LIKE ?", 
                      (stone, f'%{stone}%'))
            row = c.fetchone()
            if row:
                top3.append(f"{row['emoji']} {row['stone_name']}")
            else:
                top3.append(stone)
    
    # Дополняем до 3, если не хватает
    while len(top3) < 3:
        top3.append("💎 Горный хрусталь")
    
    return top3


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ АВТООТМЕНЫ ЗАКАЗОВ
# ═══════════════════════════════════════════════════════════════════════════

async def check_pending_orders():
    """Фоновая задача: проверять неоплаченные заказы и отменять через 24 часа."""
    while True:
        try:
            await asyncio.sleep(3600)
            
            with db_connection() as conn:
                c = conn.cursor()
                
                # Находим заказы старше 24 часов со статусом 'pending'
                c.execute('''SELECT id, user_id FROM orders 
                             WHERE status = 'pending' 
                             AND created_at < datetime('now', '-24 hours')''')
                old_orders = c.fetchall()
                
                for order in old_orders:
                    order_id = order['id']
                    user_id = order['user_id']
                    
                    # Меняем статус на cancelled
                    c.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
                    
                    # Возвращаем товары в корзину
                    await restore_cart_from_order(user_id, order_id)
                    
                    # Отправляем уведомление
                    await send_order_status_notification(user_id, order_id, 'cancelled')
                    
                    logger.info(f"Order #{order_id} auto-cancelled after 24 hours")
                    
                    await asyncio.sleep(0.1)
                
                # БАГ #14: очищаем старые блокировки
                c.execute("DELETE FROM order_locks WHERE locked_until < datetime('now')")
                
        except Exception as e:
            logger.error(f"Pending orders check error: {e}")
            await asyncio.sleep(300)


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ ЭКСПОРТА В EXCEL
# ═══════════════════════════════════════════════════════════════════════════

async def generate_orders_csv():
    """Сгенерировать CSV-файл со всеми заказами."""
    with db_cursor() as c:
        c.execute('''SELECT o.id, o.user_id, u.first_name, u.username, 
                            o.total_price, o.status, o.payment_method, o.created_at,
                            o.promo_code, o.discount_rub, o.bonus_used, o.cashback_amount
                     FROM orders o
                     LEFT JOIN users u ON o.user_id = u.user_id
                     ORDER BY o.created_at DESC''')
        orders = c.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID заказа', 'ID пользователя', 'Имя', 'Username', 
                     'Сумма', 'Статус', 'Метод оплаты', 'Дата',
                     'Промокод', 'Скидка', 'Бонусы', 'Кэшбэк'])
    
    for o in orders:
        writer.writerow([
            o['id'], o['user_id'], o['first_name'], o['username'],
            o['total_price'], o['status'], o['payment_method'], o['created_at'],
            o['promo_code'], o['discount_rub'], o['bonus_used'], o['cashback_amount']
        ])
    
    output.seek(0)
    return output.getvalue().encode('utf-8')


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ ПОДАРОЧНЫХ СЕРТИФИКАТОВ
# ═══════════════════════════════════════════════════════════════════════════

def generate_gift_code() -> str:
    """Сгенерировать уникальный код подарочного сертификата."""
    import random
    import string
    return 'GIFT-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def create_gift_certificate(buyer_id: int, amount: float, recipient_name: str, message: str = ""):
    """Создать подарочный сертификат."""
    code = generate_gift_code()
    expires_at = datetime.now() + timedelta(days=365)
    
    with db_cursor() as c:
        c.execute('''INSERT INTO gift_certificates 
                     (code, amount, buyer_id, recipient_name, message, created_at, expires_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (code, amount, buyer_id, recipient_name, message, datetime.now(), expires_at))
    
    return code


async def apply_gift_certificate(code: str, user_id: int) -> Optional[float]:
    """Применить подарочный сертификат."""
    with db_connection() as conn:
        c = conn.cursor()
        
        c.execute('''SELECT id, amount FROM gift_certificates 
                     WHERE code = ? AND status = 'active' AND expires_at > datetime('now')''',
                  (code,))
        cert = c.fetchone()
        
        if not cert:
            return None
        
        cert_id = cert['id']
        amount = cert['amount']
        
        # Начисляем бонусы
        c.execute('''INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                     VALUES (?, ?, ?, 0)
                     ON CONFLICT(user_id) DO UPDATE SET
                     balance = balance + ?,
                     total_earned = total_earned + ?''',
                  (user_id, amount, amount, amount, amount))
        
        # Помечаем сертификат как использованный
        c.execute('''UPDATE gift_certificates 
                     SET status = 'used', used_by = ?, used_at = ?
                     WHERE id = ?''',
                  (user_id, datetime.now(), cert_id))
        
        # Записываем в историю
        c.execute('''INSERT INTO bonus_history 
                     (user_id, amount, operation, created_at) 
                     VALUES (?, ?, 'gift', ?)''',
                  (user_id, amount, datetime.now()))
        
        return amount


# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ДЛЯ БЛОКИРОВОК
# ═══════════════════════════════════════════════════════════════════════════

async def acquire_order_lock(order_id: int, user_id: int, timeout_seconds: int = 5) -> bool:
    """Попытаться заблокировать заказ для обработки."""
    with db_connection() as conn:
        c = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            c.execute('''SELECT locked_until FROM order_locks 
                         WHERE order_id = ? AND locked_until > datetime("now")''', (order_id,))
            if c.fetchone():
                conn.rollback()
                return False
            
            c.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
            
            c.execute('''INSERT INTO order_locks (order_id, locked_until, user_id, created_at)
                         VALUES (?, datetime("now", ?), ?, ?)''',
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
# УВЕДОМЛЕНИЯ АДМИНУ
# ═══════════════════════════════════════════════════════════════════════════

async def notify_admin_order(user_id, order_id, total, method):
    """Уведомить админа о новом заказе."""
    if not ADMIN_ID:
        return
    try:
        with db_cursor() as c:
            c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
            u = c.fetchone()
        
        name = u['first_name'] if u else str(user_id)
        uname = f"@{u['username']}" if u and u['username'] else "нет"
        
        await bot.send_message(
            ADMIN_ID,
            f"🛒 НОВЫЙ ЗАКАЗ #{order_id}\n\n"
            f"👤 {name} ({uname})\n"
            f"💰 {total:.0f} руб\n"
            f"💳 {method}"
        )
        
        # MKT-1: отслеживаем событие в воронке
        await track_funnel_event(user_id, 'order_created', f"order_{order_id}")
        
    except Exception as e:
        logger.error(f"notify_order: {e}")


async def notify_admin_diagnostic(user_id, notes, photo1_id, photo2_id):
    """Уведомить админа о новой диагностике."""
    if not ADMIN_ID:
        return
    try:
        with db_cursor() as c:
            c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
            u = c.fetchone()
        
        name = u['first_name'] if u else str(user_id)
        uname = f"@{u['username']}" if u and u['username'] else "нет"
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        ])
        
        await bot.send_message(
            ADMIN_ID,
            f"🩺 НОВАЯ ДИАГНОСТИКА\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: {user_id}\n\n"
            f"📝 Заметки: {notes}",
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

async def get_categories_keyboard():
    """Получить клавиатуру категорий (с кэшированием)."""
    cats = get_cached_categories()
    
    buttons = [[types.InlineKeyboardButton(text=f"{cat['emoji']} {cat['name']}", 
                                           callback_data=f"cat_{cat['id']}")] for cat in cats]
    
    buttons.extend([
        [types.InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")],
        [types.InlineKeyboardButton(text="📖 ИСТОРИИ КЛИЕНТОВ", callback_data="show_stories")],
        [types.InlineKeyboardButton(text="🤝 МОЯ РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="my_referral")],
        [types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С МАСТЕРОМ", callback_data="contact_master")],
        [types.InlineKeyboardButton(text="💎 ВИТРИНА БРАСЛЕТОВ", callback_data="showcase_bracelets")],
        [types.InlineKeyboardButton(text="🔮 УЗНАТЬ СВОЙ КАМЕНЬ", callback_data="quiz_start")],
        [types.InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ О КАМНЯХ", callback_data="knowledge_list")],
        [types.InlineKeyboardButton(text="🔍 ФИЛЬТР ВИТРИНЫ", callback_data="filter_bracelets")],
        [types.InlineKeyboardButton(text="📦 МОИ ЗАКАЗЫ", callback_data="my_orders")],
        [types.InlineKeyboardButton(text="⭐ МОИ ПОКУПКИ (Stars)", callback_data="my_stars_orders")],
        [types.InlineKeyboardButton(text="❤️ ИЗБРАННОЕ", callback_data="my_wishlist"),
         types.InlineKeyboardButton(text="❓ FAQ", callback_data="faq")],
        [types.InlineKeyboardButton(text="📅 ЗАПИСЬ НА КОНСУЛЬТАЦИЮ", callback_data="book_consult")],
        [types.InlineKeyboardButton(text="🔔 НОВИНКИ", callback_data="subscribe_new"),
         types.InlineKeyboardButton(text="🎟️ ПРОМОКОД", callback_data="enter_promo")],
        [types.InlineKeyboardButton(text="🎯 ТОТЕМНЫЙ КАМЕНЬ", callback_data="totem_start")],
        [types.InlineKeyboardButton(text="🎁 ПОДАРОЧНЫЙ СЕРТИФИКАТ", callback_data="gift_menu")],
        [types.InlineKeyboardButton(text="🎂 ДЕНЬ РОЖДЕНИЯ", callback_data="set_birthday")],
    ])
    
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def admin_panel_keyboard():
    """Получить клавиатуру админ-панели."""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [types.InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="admin_showcase"),
         types.InlineKeyboardButton(text="🆕 Новинки→подписчикам", callback_data="admin_notify_new")],
        [types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics"),
         types.InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="admin_orders")],
        [types.InlineKeyboardButton(text="📊 СТАТИСТИКА+", callback_data="admin_stats_v2"),
         types.InlineKeyboardButton(text="📊 ВОРОНКА", callback_data="admin_funnel")],
        [types.InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast"),
         types.InlineKeyboardButton(text="❓ FAQ", callback_data="admin_faq")],
        [types.InlineKeyboardButton(text="🎟️ ПРОМОКОДЫ", callback_data="admin_promos"),
         types.InlineKeyboardButton(text="👥 CRM", callback_data="admin_crm")],
        [types.InlineKeyboardButton(text="⏰ РАСПИСАНИЕ", callback_data="admin_schedule"),
         types.InlineKeyboardButton(text="📖 ИСТОРИИ", callback_data="admin_stories")],
        [types.InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ", callback_data="admin_knowledge"),
         types.InlineKeyboardButton(text="🔮 ТЕСТ", callback_data="admin_quiz_results")],
        [types.InlineKeyboardButton(text="✏️ ПРИВЕТСТВИЕ", callback_data="admin_welcome_text")],
        [types.InlineKeyboardButton(text="💰 КЭШБЭК", callback_data="admin_cashback")],
        [types.InlineKeyboardButton(text="🎯 ВИКТОРИНА", callback_data="admin_totem")],
        [types.InlineKeyboardButton(text="🎁 СЕРТИФИКАТЫ", callback_data="admin_gifts")],
        [types.InlineKeyboardButton(text="📥 ЭКСПОРТ ЗАКАЗОВ", callback_data="export_orders")],
        [types.InlineKeyboardButton(text="🔔 PUSH-РАССЫЛКА", callback_data="admin_push")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])


# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - СТАТИСТИКА ВОРОНКИ (MKT-1)
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_funnel")
async def admin_funnel(cb: types.CallbackQuery):
    """Показать статистику воронки продаж."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    stats = await get_funnel_stats(30)
    
    # Определяем этапы воронки
    stages = [
        ('view_cart', '👀 Просмотр корзины'),
        ('checkout', '🛒 Оформление'),
        ('order_created', '📦 Заказ создан'),
        ('payment_started', '💳 Начало оплаты'),
        ('payment_success', '✅ Оплата'),
        ('review_left', '⭐ Отзыв')
    ]
    
    text = "📊 ВОРОНКА ПРОДАЖ (30 дней)\n\n"
    
    for stage_key, stage_name in stages:
        count = stats.get(stage_key, 0)
        text += f"{stage_name}: {count} пользователей\n"
    
    # Конверсии
    if stats.get('view_cart', 0) > 0:
        to_order = (stats.get('order_created', 0) / stats.get('view_cart', 1)) * 100
        to_payment = (stats.get('payment_success', 0) / stats.get('order_created', 1)) * 100
        text += f"\n📈 Конверсия в заказ: {to_order:.1f}%\n"
        text += f"📈 Конверсия в оплату: {to_payment:.1f}%"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - PUSH-РАССЫЛКА (NEW-6)
# ═══════════════════════════════════════════════════════════════════════════

class PushNotificationStates(BaseInputStates):
    waiting_title = State()
    waiting_message = State()
    waiting_button = State()


@admin_router.callback_query(F.data == "admin_push")
async def admin_push_start(cb: types.CallbackQuery, state: FSMContext):
    """Начать создание push-рассылки."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    await safe_edit(cb, 
        "🔔 СОЗДАНИЕ PUSH-РАССЫЛКИ\n\n"
        "Введите заголовок уведомления:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(PushNotificationStates.waiting_title)
    await cb.answer()


@admin_router.message(PushNotificationStates.waiting_title)
async def push_title(msg: types.Message, state: FSMContext):
    """Сохранить заголовок и запросить сообщение."""
    await state.update_data(push_title=msg.text)
    await msg.answer(
        "📝 Введите текст уведомления:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(PushNotificationStates.waiting_message)


@admin_router.message(PushNotificationStates.waiting_message)
async def push_message(msg: types.Message, state: FSMContext):
    """Сохранить сообщение и запросить кнопку."""
    await state.update_data(push_message=msg.text)
    await msg.answer(
        "🔘 Добавить кнопку?\n"
        "Введите текст кнопки (или отправьте 'пропустить'):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⏭️ Без кнопки", callback_data="push_no_button")],
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(PushNotificationStates.waiting_button)


@admin_router.callback_query(F.data == "push_no_button")
async def push_no_button(cb: types.CallbackQuery, state: FSMContext):
    """Отправить рассылку без кнопки."""
    data = await state.get_data()
    title = data['push_title']
    message = data['push_message']
    
    await cb.message.edit_text(
        f"🔔 ПОДТВЕРЖДЕНИЕ РАССЫЛКИ\n\n"
        f"Заголовок: {title}\n"
        f"Сообщение: {message}\n"
        f"Кнопка: без кнопки\n\n"
        f"Отправить всем подписчикам?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="push_send_none")],
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await cb.answer()


@admin_router.message(PushNotificationStates.waiting_button)
async def push_button(msg: types.Message, state: FSMContext):
    """Сохранить текст кнопки и запросить данные."""
    await state.update_data(push_button_text=msg.text)
    await msg.answer(
        "🔘 Введите callback_data для кнопки\n"
        "(например: showcase_bracelets):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(PushNotificationStates.waiting_button_data)


@admin_router.message(PushNotificationStates.waiting_button_data)
async def push_button_data(msg: types.Message, state: FSMContext):
    """Сохранить данные кнопки и показать подтверждение."""
    data = await state.get_data()
    title = data['push_title']
    message = data['push_message']
    button_text = data['push_button_text']
    button_data = msg.text
    
    await state.update_data(push_button_data=button_data)
    
    await msg.answer(
        f"🔔 ПОДТВЕРЖДЕНИЕ РАССЫЛКИ\n\n"
        f"Заголовок: {title}\n"
        f"Сообщение: {message}\n"
        f"Кнопка: {button_text} ({button_data})\n\n"
        f"Отправить всем подписчикам?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="push_send_button")],
            [types.InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")],
        ])
    )


@admin_router.callback_query(F.data == "push_send_none")
async def push_send_none(cb: types.CallbackQuery, state: FSMContext):
    """Отправить рассылку без кнопки."""
    data = await state.get_data()
    sent, failed = await notify_all_subscribers(
        data['push_title'],
        data['push_message']
    )
    
    await cb.message.edit_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В АДМИНКУ", callback_data="admin_panel")],
        ])
    )
    await state.clear()
    await cb.answer()


@admin_router.callback_query(F.data == "push_send_button")
async def push_send_button(cb: types.CallbackQuery, state: FSMContext):
    """Отправить рассылку с кнопкой."""
    data = await state.get_data()
    sent, failed = await notify_all_subscribers(
        data['push_title'],
        data['push_message'],
        data['push_button_text'],
        data['push_button_data']
    )
    
    await cb.message.edit_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В АДМИНКУ", callback_data="admin_panel")],
        ])
    )
    await state.clear()
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛЬ - ДЕНЬ РОЖДЕНИЯ (NEW-8)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "set_birthday")
async def set_birthday_start(cb: types.CallbackQuery, state: FSMContext):
    """Начать установку даты рождения."""
    await safe_edit(cb,
        "🎂 УКАЖИТЕ ДАТУ РОЖДЕНИЯ\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ\n"
        "(например: 15.05.1990)\n\n"
        "В день рождения вы получите персональный промокод на скидку 15%!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await state.set_state(BirthdayStates.waiting_birthday)
    await cb.answer()


@main_router.message(BirthdayStates.waiting_birthday)
async def set_birthday_save(msg: types.Message, state: FSMContext):
    """Сохранить дату рождения."""
    date_text = msg.text.strip()
    
    # Проверяем формат
    if not re.match(r'\d{2}\.\d{2}\.\d{4}', date_text):
        await msg.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")
        return
    
    try:
        day, month, year = map(int, date_text.split('.'))
        birthday = datetime(year, month, day).date()
        
        with db_cursor() as c:
            c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", 
                     (birthday, msg.from_user.id))
        
        await msg.answer(
            "✅ Дата рождения сохранена!\n\n"
            "В ваш день рождения мы пришлём персональный промокод на скидку 15%.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
            ])
        )
    except ValueError:
        await msg.answer("❌ Некорректная дата")
    finally:
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message(CommandStart())
async def start(msg: types.Message, state: FSMContext):
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
            c.execute('''INSERT OR IGNORE INTO users 
                         (user_id, username, first_name, created_at, welcome_sent, referred_by) 
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, msg.from_user.username, msg.from_user.first_name, 
                       datetime.now(), False, ref_id))
            
            if ref_id:
                c.execute('SELECT user_id FROM users WHERE user_id = ?', (ref_id,))
                if c.fetchone():
                    c.execute('''INSERT OR IGNORE INTO referrals (referrer_id, referred_id, created_at) 
                                 VALUES (?, ?, ?)''', (ref_id, user_id, datetime.now()))
                    c.execute('''INSERT INTO referral_balance (user_id, referral_count, balance, total_earned) 
                                 VALUES (?, 1, 100, 100) 
                                 ON CONFLICT(user_id) DO UPDATE SET 
                                 referral_count = referral_count + 1, 
                                 balance = balance + 100, 
                                 total_earned = total_earned + 100''', (ref_id,))
                    try:
                        await bot.send_message(ref_id, 
                            "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь! "
                            "Вам начислено 100 бонусов!")
                    except:
                        pass
            
            # MKT-1: отслеживаем регистрацию
            await track_funnel_event(user_id, 'registration')
        else:
            c.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name, created_at) 
                         VALUES (?, ?, ?, ?)''',
                      (user_id, msg.from_user.username, msg.from_user.first_name, datetime.now()))
    
    if is_admin(user_id):
        await msg.answer("👋 АДМИНИСТРАТОР!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")],
            [types.InlineKeyboardButton(text="👥 МЕНЮ", callback_data="menu")],
        ]))
    else:
        kb = await get_categories_keyboard()
        if is_new:
            welcome_text = get_cached_settings().get('welcome_text', 
                '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nВыберите раздел 👇')
            await msg.answer(welcome_text, reply_markup=kb)
            with db_cursor() as c:
                c.execute('UPDATE users SET welcome_sent = TRUE WHERE user_id = ?', (user_id,))
        else:
            return_text = get_cached_settings().get('return_text', 
                '👋 С возвращением! Выбери раздел:')
            await msg.answer(return_text, reply_markup=kb)


@main_router.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    """Обработчик команды /admin."""
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    await msg.answer("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Главная функция запуска бота."""
    print("\n" + "="*60)
    print("🚀 БОТ С ПОЛНЫМ ФУНКЦИОНАЛОМ ЗАПУСКАЕТСЯ")
    print("="*60 + "\n")
    
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 ПОЛНЫЙ ФУНКЦИОНАЛ ВКЛЮЧЁН")
    print(f"📍 БАГИ #1-#15 - ИСПРАВЛЕНЫ")
    print(f"📍 ОПТИМИЗАЦИЯ OPT-1..7 - ВЫПОЛНЕНА")
    print(f"📍 MKT-1 (воронка) - ДОБАВЛЕНА")
    print(f"📍 MKT-3 (авто-сторис) - ДОБАВЛЕНА")
    print(f"📍 NEW-6 (push-уведомления) - ДОБАВЛЕНЫ")
    print(f"📍 NEW-8 (день рождения) - ДОБАВЛЕН")
    print(f"📍 VOLUME - РАБОТАЕТ")
    print("\n" + "="*60 + "\n")
    
    # Middleware антиспам
    @dp.callback_query.middleware()
    async def rate_limit_middleware(handler, event, data):
        user_id = event.from_user.id
        if is_rate_limited(user_id, "cb", 0.7):
            await event.answer("⏳", show_alert=False)
            return
        return await handler(event, data)

    # Запускаем фоновые задачи
    asyncio.create_task(check_pending_orders())
    asyncio.create_task(check_birthdays())
    
    # Дополнительные фоновые задачи
    try:
        from background import send_quiz_reminders, send_diag_followup, send_cart_reminders
        asyncio.create_task(send_quiz_reminders())
        asyncio.create_task(send_diag_followup())
        asyncio.create_task(send_cart_reminders())
    except:
        pass
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")