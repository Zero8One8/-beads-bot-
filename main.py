"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ V5 (ИСПРАВЛЕННАЯ ВЕРСИЯ)
✅ ИСПРАВЛЕНО: database is locked (строки 3128, db_cursor с retry)
✅ ИСПРАВЛЕНО: добавлены все недостающие хендлеры (61/61 кнопок)
✅ ИСПРАВЛЕНО: добавлена очистка rate_limit кэша
✅ ИСПРАВЛЕНО: добавлены повторные попытки при блокировке БД
✅ ИСПРАВЛЕНО: добавлено экранирование Markdown
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

import aiohttp
import aiofiles
import aiosqlite

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

# AmoCRM
AMOCRM_SUBDOMAIN = os.getenv('AMOCRM_SUBDOMAIN', '')
AMOCRM_ACCESS_TOKEN = os.getenv('AMOCRM_ACCESS_TOKEN', '')

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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (НОВЫЕ)
# ═══════════════════════════════════════════════════════════════════════════

def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown"""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def cleanup_rate_cache():
    """Фоновая задача для очистки устаревших записей rate_limit"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        now = time.time()
        expired_keys = [
            key for key, timestamp in _rate_cache.items() 
            if now - timestamp > 3600  # Старше часа
        ]
        for key in expired_keys:
            del _rate_cache[key]
        logger.info(f"Cleaned up {len(expired_keys)} rate_limit cache entries")

# ═══════════════════════════════════════════════════════════════════════════
# БАЗОВЫЕ ФУНКЦИИ (ИСПРАВЛЕННЫЕ)
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
    """Контекстный менеджер для безопасной работы с БД (синхронный)."""
    conn = sqlite3.connect(DB, timeout=30)  # Увеличен таймаут
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def db_cursor(max_retries=5, retry_delay=0.1):
    """Контекстный менеджер для курсора с повторными попытками при блокировке"""
    for attempt in range(max_retries):
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                try:
                    yield cursor
                finally:
                    conn.commit()
                return  # Успех - выходим из функции
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))  # Экспоненциальная задержка
                continue
            else:
                logger.error(f"DB error after {attempt+1} attempts: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected DB error: {e}")
            raise

async def db_cursor_async(max_retries=5, retry_delay=0.1):
    """Асинхронный контекстный менеджер для курсора с повторными попытками"""
    for attempt in range(max_retries):
        try:
            async with aiosqlite.connect(DB, timeout=30) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute("PRAGMA cache_size=10000")
                await db.execute("PRAGMA temp_store=MEMORY")
                db.row_factory = aiosqlite.Row
                yield db
                await db.commit()
                return
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))
                continue
            else:
                logger.error(f"Async DB error after {attempt+1} attempts: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected async DB error: {e}")
            raise

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

# ======================================================
# ЭКСКЛЮЗИВНЫЙ МОДУЛЬ 1: УМНЫЙ АНАЛИТИК
# ======================================================

class SmartAnalytics:
    """Умный аналитик с прогнозированием и рекомендациями"""
    
    @staticmethod
    async def get_sales_forecast(days_ahead: int = 30) -> Dict[str, Any]:
        """Прогнозирование продаж на основе истории"""
        with db_cursor() as c:
            c.execute("""SELECT DATE(created_at) as date, COUNT(*) as orders, SUM(total_price) as revenue
                         FROM orders 
                         WHERE status = 'paid'
                         AND created_at > datetime('now', '-90 days')
                         GROUP BY DATE(created_at)
                         ORDER BY date""")
            history = c.fetchall()
        
        if len(history) < 7:
            return {"error": "Недостаточно данных для прогноза (нужно минимум 7 дней)"}
        
        # Линейная регрессия для прогноза
        dates = list(range(len(history)))
        revenues = [row['revenue'] or 0 for row in history]
        
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
        
        forecast = []
        last_date = datetime.now()
        for i in range(1, days_ahead + 1):
            pred = slope * (len(history) + i) + intercept
            forecast.append({
                'date': (last_date + timedelta(days=i)).strftime('%Y-%m-%d'),
                'predicted_revenue': max(0, round(pred, 2)),
                'predicted_orders': max(0, round(pred / (sum(revenues)/len(revenues) if revenues else 1000), 2))
            })
        
        return {
            'trend': 'up' if slope > 0 else 'down',
            'slope': round(slope, 2),
            'avg_daily': round(sum(revenues) / len(revenues), 2),
            'forecast': forecast
        }
    
    @staticmethod
    async def get_popular_stones(limit: int = 10) -> Dict[str, List[Dict]]:
        """Определение популярных камней по сезонам"""
        current_month = datetime.now().month
        
        with db_cursor() as c:
            # Популярные в текущем месяце
            c.execute("""
                SELECT k.stone_name, k.emoji, COUNT(*) as purchase_count,
                       SUM(oi.price * oi.quantity) as total_revenue
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                JOIN knowledge k ON LOWER(k.stone_name) LIKE '%' || LOWER(oi.item_name) || '%'
                WHERE o.status = 'paid'
                AND strftime('%m', o.created_at) = ?
                GROUP BY k.id
                ORDER BY purchase_count DESC
                LIMIT ?
            """, (f"{current_month:02d}", limit))
            current = c.fetchall()
            
            # Популярные за всё время
            c.execute("""
                SELECT k.stone_name, k.emoji, COUNT(*) as purchase_count,
                       SUM(oi.price * oi.quantity) as total_revenue
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                JOIN knowledge k ON LOWER(k.stone_name) LIKE '%' || LOWER(oi.item_name) || '%'
                WHERE o.status = 'paid'
                GROUP BY k.id
                ORDER BY purchase_count DESC
                LIMIT ?
            """, (limit,))
            all_time = c.fetchall()
        
        return {
            'current_month': [dict(row) for row in current],
            'all_time': [dict(row) for row in all_time]
        }
    
    @staticmethod
    async def get_sleeping_clients(days_threshold: int = 60) -> List[Dict]:
        """Определение клиентов, которые давно не покупали"""
        with db_cursor() as c:
            c.execute("""
                SELECT u.user_id, u.first_name, u.username, u.created_at,
                       MAX(o.created_at) as last_order,
                       COUNT(o.id) as total_orders,
                       SUM(o.total_price) as total_spent
                FROM users u
                LEFT JOIN orders o ON u.user_id = o.user_id AND o.status = 'paid'
                GROUP BY u.user_id
                HAVING last_order < datetime('now', ?)
                AND total_orders > 0
                ORDER BY last_order
            """, (f'-{days_threshold} days',))
            
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    async def get_recommendations(item_id: int) -> List[Dict]:
        """Рекомендации 'с этим товаром покупают'"""
        with db_cursor() as c:
            # Находим заказы с этим товаром
            c.execute("""
                SELECT DISTINCT order_id FROM order_items
                WHERE item_id = ? OR item_id = ?
            """, (item_id, item_id + 100000))
            
            order_ids = [row['order_id'] for row in c.fetchall()]
            if not order_ids:
                return []
            
            placeholders = ','.join(['?'] * len(order_ids))
            
            # Находим другие товары в этих заказах
            c.execute(f"""
                SELECT oi.item_id, 
                       CASE WHEN oi.item_id >= 100000 
                            THEN (SELECT name FROM showcase_items WHERE id = oi.item_id - 100000)
                            ELSE (SELECT name FROM bracelets WHERE id = oi.item_id)
                       END as name,
                       COUNT(*) as together_count
                FROM order_items oi
                WHERE oi.order_id IN ({placeholders})
                AND (oi.item_id != ? AND oi.item_id != ?)
                GROUP BY oi.item_id
                ORDER BY together_count DESC
                LIMIT 5
            """, order_ids + [item_id, item_id + 100000])
            
            return [dict(row) for row in c.fetchall()]

# ======================================================
# ЭКСКЛЮЗИВНЫЙ МОДУЛЬ 2: CRM ИНТЕГРАЦИЯ (AmoCRM)
# ======================================================

class AmoCRMIntegration:
    """Интеграция с AmoCRM для автоматической отправки заказов"""
    
    @staticmethod
    async def send_order_to_amocrm(order_id: int) -> bool:
        """Отправка заказа в AmoCRM"""
        if not AMOCRM_ACCESS_TOKEN or not AMOCRM_SUBDOMAIN:
            logger.warning("AmoCRM not configured - missing credentials")
            return False
        
        # Получаем данные заказа
        with db_cursor() as c:
            c.execute("""
                SELECT o.*, u.first_name, u.username, u.user_id,
                       GROUP_CONCAT(oi.item_name || ' x' || oi.quantity, '\n') as items
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                LEFT JOIN order_items oi ON o.id = oi.order_id
                WHERE o.id = ?
                GROUP BY o.id
            """, (order_id,))
            order = c.fetchone()
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return False
        
        # Формируем данные для AmoCRM
        lead_data = {
            'name': f"Заказ #{order_id} от {order['first_name'] or order['username'] or order['user_id']}",
            'price': order['total_price'],
            'status_id': 142,  # Статус "Сделка"
            'custom_fields_values': [
                {
                    'field_id': 123,  # ID поля "Телефон/Username"
                    'values': [{'value': f"@{order['username']}" if order['username'] else ''}]
                },
                {
                    'field_id': 456,  # ID поля "Состав заказа"
                    'values': [{'value': order['items']}]
                },
                {
                    'field_id': 789,  # ID поля "Метод оплаты"
                    'values': [{'value': order['payment_method'] or 'Не указан'}]
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {AMOCRM_ACCESS_TOKEN}',
                    'Content-Type': 'application/json'
                }
                async with session.post(
                    f'https://{AMOCRM_SUBDOMAIN}.amocrm.ru/api/v4/leads',
                    headers=headers,
                    json=[lead_data]
                ) as resp:
                    if resp.status == 200 or resp.status == 201:
                        logger.info(f"✅ Order {order_id} sent to AmoCRM")
                        
                        # Уведомляем админа об успехе
                        if ADMIN_ID:
                            try:
                                await bot.send_message(
                                    ADMIN_ID,
                                    f"🔄 *AmoCRM интеграция*\n\n"
                                    f"✅ Заказ #{order_id} успешно отправлен в AmoCRM",
                                    parse_mode="Markdown"
                                )
                            except:
                                pass
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"AmoCRM error: {resp.status} - {error_text}")
                        
                        # Уведомляем админа об ошибке
                        if ADMIN_ID:
                            try:
                                await bot.send_message(
                                    ADMIN_ID,
                                    f"🔄 *AmoCRM интеграция*\n\n"
                                    f"❌ Ошибка при отправке заказа #{order_id}\n"
                                    f"Код: {resp.status}\n"
                                    f"Ответ: {error_text[:200]}",
                                    parse_mode="Markdown"
                                )
                            except:
                                pass
                        return False
        except Exception as e:
            logger.error(f"AmoCRM connection error: {e}")
            
            # Уведомляем админа об ошибке
            if ADMIN_ID:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"🔄 *AmoCRM интеграция*\n\n"
                        f"❌ Ошибка подключения при отправке заказа #{order_id}\n"
                        f"{str(e)[:200]}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            return False

# ======================================================
# ЭКСКЛЮЗИВНЫЙ МОДУЛЬ 3: WEBVIEW ПРИЛОЖЕНИЕ
# ======================================================

class WebViewApp:
    """Генерация webview приложения для мобильных устройств"""
    
    @staticmethod
    async def generate_html(bot_username: str = "The_magic_of_stones_bot") -> str:
        """Генерация HTML-страницы с iframe бота"""
        html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Магия Камней</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }}
        .container {{
            display: flex;
            flex-direction: column;
            height: 100vh;
            width: 100vw;
        }}
        .header {{
            background: rgba(255, 255, 255, 0.95);
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 10;
        }}
        .logo {{
            font-size: 18px;
            font-weight: bold;
            color: #4a148c;
        }}
        .refresh-btn {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 5px;
            transition: background 0.3s;
        }}
        .refresh-btn:hover {{
            background: #f0f0f0;
        }}
        iframe {{
            flex: 1;
            width: 100%;
            border: none;
            background: white;
        }}
        .loader {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            display: none;
            z-index: 20;
        }}
        .loader.active {{
            display: block;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #4a148c;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        @media (prefers-color-scheme: dark) {{
            .header {{
                background: rgba(30, 30, 30, 0.95);
            }}
            .logo {{
                color: #bb86fc;
            }}
            .refresh-btn {{
                color: white;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="logo">✨ Магия Камней</span>
            <button class="refresh-btn" onclick="refreshFrame()">↻</button>
        </div>
        <iframe id="botFrame" src="https://t.me/{bot_username}" allow="microphone; camera"></iframe>
        <div class="loader" id="loader">
            <div class="spinner"></div>
        </div>
    </div>

    <script>
        const frame = document.getElementById('botFrame');
        const loader = document.getElementById('loader');
        
        frame.onload = function() {{
            loader.classList.remove('active');
        }};
        
        frame.onerror = function() {{
            loader.classList.remove('active');
            alert('Ошибка загрузки. Проверьте подключение к интернету.');
        }};
        
        function refreshFrame() {{
            loader.classList.add('active');
            frame.src = frame.src;
        }}
        
        if (window.location.hash) {{
            const hash = window.location.hash.substring(1);
            frame.src = `https://t.me/{bot_username}?start=${{hash}}`;
        }}
    </script>
</body>
</html>"""
        return html_template
    
    @staticmethod
    async def generate_pwa_manifest() -> dict:
        """Генерация PWA манифеста для установки на телефон"""
        return {
            "name": "Магия Камней",
            "short_name": "Stones",
            "description": "Магазин натуральных камней. Браслеты, амулеты, индивидуальный подбор.",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#4a148c",
            "orientation": "portrait",
            "scope": "/",
            "icons": [
                {
                    "src": "/static/icon-72x72.png",
                    "sizes": "72x72",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-96x96.png",
                    "sizes": "96x96",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-128x128.png",
                    "sizes": "128x128",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-144x144.png",
                    "sizes": "144x144",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-152x152.png",
                    "sizes": "152x152",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-192x192.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-384x384.png",
                    "sizes": "384x384",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-512x512.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ]
        }
    
    @staticmethod
    async def save_webview_files(bot_username: str = "The_magic_of_stones_bot"):
        """Сохранение всех файлов для webview приложения"""
        Path('static').mkdir(parents=True, exist_ok=True)
        
        html = await WebViewApp.generate_html(bot_username)
        async with aiofiles.open('static/index.html', 'w', encoding='utf-8') as f:
            await f.write(html)
        
        manifest = await WebViewApp.generate_pwa_manifest()
        async with aiofiles.open('static/manifest.json', 'w', encoding='utf-8') as f:
            await f.write(json.dumps(manifest, ensure_ascii=False, indent=2))
        
        sw = """self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request);
        })
    );
});"""
        
        async with aiofiles.open('static/sw.js', 'w', encoding='utf-8') as f:
            await f.write(sw)
        
        return True

# ======================================================
# ЭКСКЛЮЗИВНЫЙ МОДУЛЬ 4: SEO ГЕНЕРАТОР
# ======================================================

class SEOGenerator:
    """Генерация SEO-контента для карточек товаров и соцсетей"""
    
    @staticmethod
    async def generate_product_description(stone_name: str) -> str:
        """Генерация уникального описания для карточки товара"""
        templates = [
            "✨ {stone} - это удивительный камень, который поможет вам {benefit}. {full_desc}",
            "💫 Откройте для себя магию {stone}. Этот камень известен своими свойствами {properties}. {short_desc}",
            "🌟 {stone} - идеальный выбор для тех, кто ищет {benefit}. {full_desc}",
            "💎 Позвольте энергии {stone} изменить вашу жизнь. {short_desc} {full_desc}",
            "🔮 {stone} - древний камень {properties}. Он поможет вам {benefit}."
        ]
        
        with db_cursor() as c:
            c.execute("SELECT short_desc, full_desc, properties, tasks FROM knowledge WHERE stone_name LIKE ?", 
                     (f'%{stone_name}%',))
            stone = c.fetchone()
        
        if not stone:
            return f"✨ {stone_name} - натуральный камень с уникальными свойствами. Подходит для ежедневного ношения."
        
        props = stone['properties'].split(', ') if stone['properties'] else ['защита', 'гармония']
        benefits = [
            "обрести внутреннюю гармонию",
            "усилить интуицию",
            "привлечь удачу",
            "защититься от негатива",
            "раскрыть творческий потенциал",
            "улучшить финансовое положение",
            "найти любовь",
            "успокоить ум"
        ]
        
        import random
        template = random.choice(templates)
        benefit = random.choice(benefits)
        properties = ', '.join(props[:3]) if props else 'удивительными'
        
        description = template.format(
            stone=stone_name,
            benefit=benefit,
            short_desc=stone['short_desc'] or '',
            full_desc=stone['full_desc'] or '',
            properties=properties
        )
        
        hashtags = ' '.join([f"#{p.strip()}" for p in props[:5]])
        description += f"\n\n{hashtags}"
        
        return description
    
    @staticmethod
    async def generate_meta_tags(page: str, item_name: str = None) -> Dict[str, str]:
        """Генерация SEO-метатегов для страниц"""
        base_tags = {
            'title': 'Магия Камней - натуральные камни и браслеты',
            'description': 'Магазин натуральных камней. Браслеты, чётки, амулеты. Индивидуальный подбор под вашу энергетику.',
            'keywords': 'камни, минералы, браслеты, амулеты, энергетика, литотерапия, натуральные камни'
        }
        
        if page == 'product' and item_name:
            base_tags.update({
                'title': f'{item_name} - купить в Магии Камней | Цена, свойства',
                'description': f'{item_name} - натуральный камень. Свойства, значение, цена. Индивидуальный подбор и доставка.',
                'keywords': f'{item_name}, камень, свойства, купить, цена'
            })
        
        return base_tags
    
    @staticmethod
    async def generate_social_post(stone_name: str, platform: str = 'telegram') -> str:
        """Генерация поста для социальных сетей"""
        templates = {
            'telegram': [
                "🌟 **{stone}** – ваш личный помощник!\n\n{desc}\n\n👉 Заказать в боте: @The_magic_of_stones_bot",
                "💫 Знакомьтесь – **{stone}**!\n\n{desc}\n\n✨ Переходите в бота: @The_magic_of_stones_bot"
            ],
            'instagram': [
                "✨ {stone} – ваш личный помощник!\n.\n{desc}\n.\n👉 Ссылка в шапке профиля",
                "💫 Знакомьтесь – {stone}!\n.\n{desc}\n.\n🔥 Заходите в бота по ссылке в шапке"
            ],
            'tiktok': [
                "{stone} – твой камень силы! {desc_short} #камни #магия #литотерапия",
                "Что такое {stone}? {desc_short} #камни #эзотерика #саморазвитие"
            ]
        }
        
        short_descs = [
            "помогает обрести гармонию",
            "усиливает интуицию",
            "привлекает удачу",
            "защищает от негатива"
        ]
        
        import random
        desc_short = random.choice(short_descs)
        desc = f"{stone_name} - натуральный камень, который {desc_short}."
        
        template_list = templates.get(platform, templates['telegram'])
        template = random.choice(template_list)
        
        return template.format(stone=stone_name, desc=desc, desc_short=desc_short)

# ======================================================
# ЭКСКЛЮЗИВНЫЙ МОДУЛЬ 5: САЙТ-ВИЗИТКА
# ======================================================

class WebsiteGenerator:
    """Генерация статического сайта-визитки на основе данных из бота"""
    
    @staticmethod
    async def generate_html() -> str:
        """Генерация HTML страницы с каталогом товаров"""
        with db_cursor() as c:
            c.execute("""
                SELECT si.*, sc.name as collection_name, sc.emoji as collection_emoji
                FROM showcase_items si
                JOIN showcase_collections sc ON si.collection_id = sc.id
                WHERE si.price > 0
                ORDER BY si.created_at DESC
                LIMIT 12
            """)
            products = c.fetchall()
        
        products_html = ""
        for p in products:
            products_html += f"""
            <div class="product-card">
                <div class="product-image">
                    <img src="/static/products/{p['image_file_id'] or 'default.jpg'}" alt="{p['name']}">
                </div>
                <div class="product-info">
                    <h3>{p['name']}</h3>
                    <p class="product-desc">{p['description'][:100] if p['description'] else ''}...</p>
                    <div class="product-meta">
                        <span class="collection">{p['collection_emoji']} {p['collection_name']}</span>
                        <span class="price">{p['price']:.0f} ₽</span>
                    </div>
                    <a href="https://t.me/The_magic_of_stones_bot" class="buy-btn" target="_blank">
                        🛒 Купить в Telegram
                    </a>
                </div>
            </div>
            """
        
        if not products_html:
            products_html = "<p class='no-products'>Скоро здесь появятся наши изделия</p>"
        
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Магия Камней - магазин натуральных камней</title>
    <meta name="description" content="Магазин натуральных камней. Браслеты, чётки, амулеты. Индивидуальный подбор под вашу энергетику.">
    <meta name="keywords" content="камни, минералы, браслеты, амулеты, литотерапия">
    
    <meta property="og:title" content="Магия Камней">
    <meta property="og:description" content="Магазин натуральных камней. Браслеты, чётки, амулеты.">
    <meta property="og:image" content="/static/og-image.jpg">
    
    <link rel="icon" type="image/png" href="/static/favicon.png">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#4a148c">
    
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }}
        
        header {{
            background: rgba(255, 255, 255, 0.95);
            padding: 20px 0;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
        }}
        
        .header-content {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #4a148c;
        }}
        
        .nav-links {{
            display: flex;
            gap: 30px;
        }}
        
        .nav-links a {{
            text-decoration: none;
            color: #333;
            font-weight: 500;
            transition: color 0.3s;
        }}
        
        .nav-links a:hover {{
            color: #4a148c;
        }}
        
        .hero {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 100px 0;
            text-align: center;
        }}
        
        .hero h1 {{
            font-size: 48px;
            margin-bottom: 20px;
            animation: fadeInUp 1s ease;
        }}
        
        .hero p {{
            font-size: 18px;
            max-width: 600px;
            margin: 0 auto 30px;
            animation: fadeInUp 1s ease 0.2s both;
        }}
        
        .hero-buttons {{
            display: flex;
            gap: 20px;
            justify-content: center;
            animation: fadeInUp 1s ease 0.4s both;
        }}
        
        .btn {{
            display: inline-block;
            padding: 15px 40px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: 600;
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}
        
        .btn-primary {{
            background: white;
            color: #4a148c;
        }}
        
        .btn-secondary {{
            background: transparent;
            color: white;
            border: 2px solid white;
        }}
        
        .features {{
            background: white;
            padding: 80px 0;
        }}
        
        .features-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 30px;
        }}
        
        .feature {{
            text-align: center;
            padding: 30px;
        }}
        
        .feature-emoji {{
            font-size: 48px;
            margin-bottom: 20px;
        }}
        
        .feature h3 {{
            margin-bottom: 15px;
            color: #333;
        }}
        
        .feature p {{
            color: #666;
        }}
        
        .products {{
            padding: 80px 0;
            background: #f5f5f5;
        }}
        
        .section-title {{
            text-align: center;
            margin-bottom: 50px;
        }}
        
        .section-title h2 {{
            font-size: 36px;
            color: #333;
            margin-bottom: 15px;
        }}
        
        .section-title p {{
            color: #666;
            max-width: 600px;
            margin: 0 auto;
        }}
        
        .products-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
        }}
        
        .product-card {{
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        
        .product-card:hover {{
            transform: translateY(-5px);
        }}
        
        .product-image {{
            height: 250px;
            overflow: hidden;
        }}
        
        .product-image img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.3s;
        }}
        
        .product-card:hover .product-image img {{
            transform: scale(1.05);
        }}
        
        .product-info {{
            padding: 20px;
        }}
        
        .product-info h3 {{
            margin-bottom: 10px;
            color: #333;
        }}
        
        .product-desc {{
            color: #666;
            margin-bottom: 15px;
            line-height: 1.6;
        }}
        
        .product-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .collection {{
            color: #4a148c;
            font-size: 14px;
        }}
        
        .price {{
            font-size: 20px;
            font-weight: bold;
            color: #4a148c;
        }}
        
        .buy-btn {{
            display: block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
            font-weight: 600;
            transition: opacity 0.3s;
        }}
        
        .buy-btn:hover {{
            opacity: 0.9;
        }}
        
        .testimonials {{
            padding: 80px 0;
            background: white;
        }}
        
        .testimonials-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
        }}
        
        .testimonial {{
            background: #f5f5f5;
            padding: 30px;
            border-radius: 15px;
        }}
        
        .testimonial-text {{
            font-style: italic;
            margin-bottom: 20px;
            color: #555;
        }}
        
        .testimonial-author {{
            font-weight: 600;
            color: #333;
        }}
        
        .cta {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 80px 0;
            text-align: center;
        }}
        
        .cta h2 {{
            font-size: 36px;
            margin-bottom: 20px;
        }}
        
        .cta p {{
            max-width: 600px;
            margin: 0 auto 30px;
            font-size: 18px;
        }}
        
        .cta-buttons {{
            display: flex;
            gap: 20px;
            justify-content: center;
        }}
        
        .cta-btn {{
            display: inline-block;
            padding: 15px 40px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: 600;
            transition: transform 0.3s;
        }}
        
        .cta-btn-primary {{
            background: white;
            color: #4a148c;
        }}
        
        .cta-btn-secondary {{
            background: transparent;
            color: white;
            border: 2px solid white;
        }}
        
        footer {{
            background: #333;
            color: white;
            padding: 40px 0;
        }}
        
        .footer-content {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}
        
        .footer-col h4 {{
            margin-bottom: 20px;
            color: #fff;
        }}
        
        .footer-col ul {{
            list-style: none;
        }}
        
        .footer-col ul li {{
            margin-bottom: 10px;
        }}
        
        .footer-col ul li a {{
            color: #999;
            text-decoration: none;
            transition: color 0.3s;
        }}
        
        .footer-col ul li a:hover {{
            color: #fff;
        }}
        
        .copyright {{
            text-align: center;
            padding-top: 30px;
            border-top: 1px solid #555;
            color: #999;
        }}
        
        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        @media (max-width: 768px) {{
            .hero h1 {{
                font-size: 36px;
            }}
            .nav-links {{
                display: none;
            }}
            .hero-buttons {{
                flex-direction: column;
                padding: 0 20px;
            }}
        }}
        
        @media (prefers-color-scheme: dark) {{
            body {{
                background: #1a1a1a;
            }}
            .features,
            .testimonials {{
                background: #2d2d2d;
            }}
            .product-card,
            .testimonial {{
                background: #3d3d3d;
            }}
            .product-info h3,
            .feature h3,
            .section-title h2 {{
                color: #fff;
            }}
            .product-desc,
            .feature p,
            .testimonial-text,
            .section-title p {{
                color: #ccc;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="header-content">
                <div class="logo">✨ Магия Камней</div>
                <nav class="nav-links">
                    <a href="#about">О нас</a>
                    <a href="#products">Товары</a>
                    <a href="#reviews">Отзывы</a>
                    <a href="#contacts">Контакты</a>
                </nav>
            </div>
        </div>
    </header>
    
    <section class="hero">
        <div class="container">
            <h1>Натуральные камни с душой</h1>
            <p>Браслеты, чётки и амулеты из натуральных камней. Индивидуальный подбор под вашу энергетику.</p>
            <div class="hero-buttons">
                <a href="https://t.me/The_magic_of_stones_bot" class="btn btn-primary" target="_blank">
                    🚀 Перейти в бота
                </a>
                <a href="#products" class="btn btn-secondary">
                    📦 Смотреть товары
                </a>
            </div>
        </div>
    </section>
    
    <section class="features" id="about">
        <div class="container">
            <div class="features-grid">
                <div class="feature">
                    <div class="feature-emoji">💎</div>
                    <h3>Натуральные камни</h3>
                    <p>Только сертифицированные минералы высшего качества из проверенных месторождений</p>
                </div>
                <div class="feature">
                    <div class="feature-emoji">✨</div>
                    <h3>Индивидуальный подход</h3>
                    <p>Персональный подбор камней под ваши задачи с помощью теста в боте</p>
                </div>
                <div class="feature">
                    <div class="feature-emoji">🚀</div>
                    <h3>Быстрая доставка</h3>
                    <p>Отправляем по всей России за 1-3 дня. Трекинг-номер сразу</p>
                </div>
            </div>
        </div>
    </section>
    
    <section class="products" id="products">
        <div class="container">
            <div class="section-title">
                <h2>Наши изделия</h2>
                <p>Выберите свой камень в нашем Telegram-боте</p>
            </div>
            <div class="products-grid">
                {products_html}
            </div>
        </div>
    </section>
    
    <section class="testimonials" id="reviews">
        <div class="container">
            <div class="section-title">
                <h2>Отзывы клиентов</h2>
                <p>Что говорят о нас те, кто уже носит наши камни</p>
            </div>
            <div class="testimonials-grid">
                <div class="testimonial">
                    <p class="testimonial-text">"Заказала браслет с аметистом. Очень довольна качеством! Камень действительно помогает успокоиться и лучше спать."</p>
                    <p class="testimonial-author">— Анна, Москва</p>
                </div>
                <div class="testimonial">
                    <p class="testimonial-text">"Уже третий заказ. Камни реально работают. Тест в боте очень точный - мой камень действительно подошел."</p>
                    <p class="testimonial-author">— Дмитрий, СПб</p>
                </div>
                <div class="testimonial">
                    <p class="testimonial-text">"Покупал в подарок жене. Очень красивый браслет, упаковка отличная. Жена в восторге!"</p>
                    <p class="testimonial-author">— Михаил, Казань</p>
                </div>
            </div>
        </div>
    </section>
    
    <section class="cta">
        <div class="container">
            <h2>Найдите свой камень</h2>
            <p>Пройдите тест в Telegram-боте и получите персональную рекомендацию</p>
            <div class="cta-buttons">
                <a href="https://t.me/The_magic_of_stones_bot" class="cta-btn cta-btn-primary" target="_blank">
                    🚀 Перейти в бота
                </a>
            </div>
        </div>
    </section>
    
    <footer>
        <div class="container">
            <div class="footer-content">
                <div class="footer-col">
                    <h4>Магия Камней</h4>
                    <ul>
                        <li><a href="#about">О нас</a></li>
                        <li><a href="#products">Товары</a></li>
                        <li><a href="#reviews">Отзывы</a></li>
                    </ul>
                </div>
                <div class="footer-col">
                    <h4>Контакты</h4>
                    <ul>
                        <li><a href="https://t.me/The_magic_of_stones_bot" target="_blank">Telegram бот</a></li>
                        <li><a href="mailto:info@magicstones.ru">Email</a></li>
                    </ul>
                </div>
                <div class="footer-col">
                    <h4>Информация</h4>
                    <ul>
                        <li><a href="/static/privacy.html">Политика конфиденциальности</a></li>
                        <li><a href="/static/offer.html">Договор оферты</a></li>
                    </ul>
                </div>
            </div>
            <div class="copyright">
                <p>© 2024 Магия Камней. Все права защищены.</p>
            </div>
        </div>
    </footer>
    
    <script>
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth' }});
                }}
            }});
        }});
    </script>
</body>
</html>"""
        
        return html

# ═══════════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ БД - ПОЛНАЯ
# ═══════════════════════════════════════════════════════════════════════════

def init_db():
    """Инициализация базы данных со всеми таблицами."""
    with db_connection() as conn:
        c = conn.cursor()
        
        # ✅ ВКЛЮЧАЕМ WAL РЕЖИМ ДЛЯ ЛУЧШЕЙ ПРОИЗВОДИТЕЛЬНОСТИ
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA cache_size=10000")
        c.execute("PRAGMA temp_store=MEMORY")
        
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
    # Добавленные индексы
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_payment ON orders(payment_method)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_gift_code ON gift_certificates(code)")

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
                        "💭 В одиночестве, медитируя", "🏃 В движении, спорте"]),
             json.dumps({"amethyst": 3, "garnet": 2, "clear_quartz": 3, "carnelian": 2})),
            
            ("Что для тебя важнее всего в жизни?",
             json.dumps(["❤️ Любовь и отношения", "💰 Деньги и успех", 
                        "🛡 Защита и безопасность", "🌟 Духовное развитие"]),
             json.dumps({"rose_quartz": 3, "citrine": 3, "black_tourmaline": 3, "amethyst": 3})),
            
            ("Как ты принимаешь важные решения?",
             json.dumps(["🧠 Логически, взвешивая всё", "💫 Интуитивно, как сердце подскажет",
                        "👥 Советуюсь с близкими", "🌀 Долго сомневаюсь"]),
             json.dumps({"tiger_eye": 2, "moonstone": 3, "sodalite": 2, "lepidolite": 3})),
            
            ("Чего тебе не хватает прямо сейчас?",
             json.dumps(["⚡ Энергии и драйва", "😌 Спокойствия", 
                        "✨ Ясности в мыслях", "💰 Денежного потока"]),
             json.dumps({"carnelian": 3, "amethyst": 3, "clear_quartz": 3, "citrine": 3})),
            
            ("Какая твоя главная мечта?",
             json.dumps(["🌍 Путешествовать и познавать мир", "🏠 Создать уютный дом",
                        "🚀 Достичь карьерных высот", "🔮 Найти себя и свой путь"]),
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
            
            # Отправка в AmoCRM при создании заказа
            if AMOCRM_ACCESS_TOKEN and AMOCRM_SUBDOMAIN:
                asyncio.create_task(AmoCRMIntegration.send_order_to_amocrm(order_id))
            
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
        [InlineKeyboardButton(text="📊 УМНЫЙ АНАЛИТИК", callback_data="smart_analytics_menu")],
        [InlineKeyboardButton(text="🌐 САЙТ-ВИЗИТКА", callback_data="visit_site")],
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
        [InlineKeyboardButton(text="📈 УМНЫЙ АНАЛИТИК", callback_data="admin_smart_analytics")],
        [InlineKeyboardButton(text="🔄 CRM ИНТЕГРАЦИЯ", callback_data="admin_crm")],
        [InlineKeyboardButton(text="📱 WEBVIEW ПРИЛОЖЕНИЕ", callback_data="admin_webview")],
        [InlineKeyboardButton(text="🔍 SEO ГЕНЕРАТОР", callback_data="admin_seo")],
        [InlineKeyboardButton(text="🌐 САЙТ-ВИЗИТКА", callback_data="admin_website")],
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
# ВОРОНКА (ИСПРАВЛЕННАЯ ВЕРСИЯ - СТРОКА 3128)
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
        """Отследить событие в воронке с повторными попытками (ИСПРАВЛЕНО)."""
        if event_type not in FunnelTracker.EVENTS:
            logger.warning(f"Unknown funnel event: {event_type}")
            return
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                async with aiosqlite.connect(DB, timeout=30) as db:
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("PRAGMA synchronous=NORMAL")
                    await db.execute("PRAGMA cache_size=10000")
                    await db.execute("PRAGMA temp_store=MEMORY")
                    
                    await db.execute('''INSERT INTO funnel_stats 
                                         (user_id, event_type, details, created_at)
                                         VALUES (?, ?, ?, ?)''',
                                      (user_id, event_type, details, datetime.now()))
                    await db.commit()
                    return
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)  # Экспоненциальная задержка
                    logger.warning(f"Database locked, retry {attempt+1}/{max_retries} after {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed to track event after {attempt+1} attempts: {e}")
                    # Пытаемся сохранить в синхронном режиме как fallback
                    try:
                        with db_cursor(max_retries=3) as c:
                            c.execute('''INSERT INTO funnel_stats 
                                         (user_id, event_type, details, created_at)
                                         VALUES (?, ?, ?, ?)''',
                                      (user_id, event_type, details, datetime.now()))
                            return
                    except Exception as fallback_error:
                        logger.error(f"Fallback also failed: {fallback_error}")
                        raise
            except Exception as e:
                logger.error(f"Unexpected error in track: {e}")
                raise
    
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

# ======================================================
# АДМИН - УМНЫЙ АНАЛИТИК
# ======================================================

@admin_router.callback_query(F.data == "admin_smart_analytics")
@rate_limit(2.0)
async def admin_smart_analytics(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    forecast = await SmartAnalytics.get_sales_forecast(7)
    stones = await SmartAnalytics.get_popular_stones(5)
    sleeping = await SmartAnalytics.get_sleeping_clients(60)
    
    text = "📈 *УМНЫЙ АНАЛИТИК*\n\n"
    
    if 'error' in forecast:
        text += f"*ПРОГНОЗ:* {forecast['error']}\n\n"
    else:
        text += "*ПРОГНОЗ ПРОДАЖ (7 дней)*\n"
        for day in forecast['forecast'][:7]:
            text += f"  • {day['date']}: {day['predicted_revenue']:.0f}₽\n"
        text += f"\n*ТРЕНД:* {'📈 рост' if forecast['trend'] == 'up' else '📉 падение'}\n"
        text += f"*СРЕДНИЙ ДНЕВНОЙ:* {forecast['avg_daily']:.0f}₽\n\n"
    
    text += "*ПОПУЛЯРНЫЕ КАМНИ (месяц)*\n"
    for stone in stones.get('current_month', [])[:3]:
        text += f"  • {stone['emoji']} {stone['stone_name']}: {stone['purchase_count']} шт.\n"
    
    text += f"\n*СПЯЩИХ КЛИЕНТОВ:* {len(sleeping)} чел.\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Детальный прогноз", callback_data="analytics_forecast")],
            [InlineKeyboardButton(text="💎 Популярность по сезонам", callback_data="analytics_seasons")],
            [InlineKeyboardButton(text="😴 Реактивация клиентов", callback_data="analytics_sleeping")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "analytics_forecast")
@rate_limit(2.0)
async def analytics_forecast(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    forecast = await SmartAnalytics.get_sales_forecast(30)
    
    if 'error' in forecast:
        text = f"❌ {forecast['error']}"
    else:
        text = f"📊 *ПРОГНОЗ НА 30 ДНЕЙ*\n\n"
        for week in range(0, 30, 7):
            week_sum = sum(d['predicted_revenue'] for d in forecast['forecast'][week:week+7])
            text += f"*Неделя {week//7 + 1}:* {week_sum:.0f}₽\n"
        text += f"\n*Тренд:* {forecast['trend']}\n"
        text += f"*Средний чек:* {forecast['avg_daily']:.0f}₽"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_smart_analytics")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "analytics_seasons")
@rate_limit(2.0)
async def analytics_seasons(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    stones = await SmartAnalytics.get_popular_stones(10)
    
    text = "🍂 *ПОПУЛЯРНОСТЬ ПО СЕЗОНАМ*\n\n"
    text += "*Текущий месяц:*\n"
    for stone in stones['current_month'][:5]:
        text += f"  • {stone['emoji']} {stone['stone_name']}: {stone['purchase_count']} шт.\n"
    
    text += "\n*За всё время:*\n"
    for stone in stones['all_time'][:5]:
        text += f"  • {stone['emoji']} {stone['stone_name']}: {stone['purchase_count']} шт.\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_smart_analytics")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "analytics_sleeping")
@rate_limit(2.0)
async def analytics_sleeping(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    clients = await SmartAnalytics.get_sleeping_clients(60)
    
    text = "😴 *СПЯЩИЕ КЛИЕНТЫ*\n\n"
    if clients:
        for client in clients[:5]:
            name = client['first_name'] or client['username'] or f"ID{client['user_id']}"
            text += f"• {name}\n"
            text += f"  Последний заказ: {client['last_order'][:10]}\n"
            text += f"  Всего покупок: {client['total_orders']}\n\n"
    else:
        text += "Спящих клиентов нет"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_smart_analytics")],
        ])
    )
    await cb.answer()

# ======================================================
# АДМИН - CRM ИНТЕГРАЦИЯ
# ======================================================

@admin_router.callback_query(F.data == "admin_crm")
@rate_limit(2.0)
async def admin_crm(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    text = "🔄 *CRM ИНТЕГРАЦИЯ*\n\n"
    text += "*AmoCRM*\n"
    if AMOCRM_ACCESS_TOKEN and AMOCRM_SUBDOMAIN:
        text += "  ✅ Подключено\n"
        text += f"  • Поддомен: {AMOCRM_SUBDOMAIN}\n"
    else:
        text += "  ❌ Не настроено\n"
        text += "  • Требуется AMOCRM_SUBDOMAIN и AMOCRM_ACCESS_TOKEN\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Тест интеграции", callback_data="crm_test")],
            [InlineKeyboardButton(text="📊 Отправить тестовый заказ", callback_data="crm_test_order")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "crm_test")
@rate_limit(2.0)
async def crm_test(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute("SELECT id FROM orders ORDER BY created_at DESC LIMIT 1")
        last_order = c.fetchone()
    
    if not last_order:
        await cb.answer("❌ Нет заказов для теста", show_alert=True)
        return
    
    result = await AmoCRMIntegration.send_order_to_amocrm(last_order['id'])
    
    if result:
        await cb.answer("✅ Интеграция работает!", show_alert=True)
    else:
        await cb.answer("❌ Ошибка интеграции. Проверьте логи.", show_alert=True)

@admin_router.callback_query(F.data == "crm_test_order")
@rate_limit(2.0)
async def crm_test_order(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    test_user_id = ADMIN_ID
    test_amount = random.randint(1000, 5000)
    
    with db_cursor() as c:
        c.execute("""INSERT INTO orders 
                     (user_id, total_price, status, payment_method, created_at)
                     VALUES (?, ?, 'paid', 'test', ?)""",
                  (test_user_id, test_amount, datetime.now()))
        order_id = c.lastrowid
        
        c.execute("""INSERT INTO order_items
                     (order_id, user_id, item_type, item_id, item_name, quantity, price, created_at)
                     VALUES (?, ?, 'test', 1, 'Тестовый товар', 1, ?, ?)""",
                  (order_id, test_user_id, test_amount, datetime.now()))
    
    result = await AmoCRMIntegration.send_order_to_amocrm(order_id)
    
    if result:
        await cb.answer(f"✅ Тестовый заказ #{order_id} отправлен!", show_alert=True)
    else:
        await cb.answer("❌ Ошибка отправки", show_alert=True)

# ======================================================
# АДМИН - WEBVIEW ПРИЛОЖЕНИЕ
# ======================================================

@admin_router.callback_query(F.data == "admin_webview")
@rate_limit(2.0)
async def admin_webview(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    text = "📱 *WEBVIEW ПРИЛОЖЕНИЕ*\n\n"
    text += "Генерация обертки для мобильных устройств:\n"
    text += "• HTML-страница с iframe бота\n"
    text += "• PWA манифест для установки на телефон\n"
    text += "• Service Worker для офлайн-доступа\n\n"
    text += "Файлы будут сохранены в папку `static/`"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 СГЕНЕРИРОВАТЬ", callback_data="webview_generate")],
            [InlineKeyboardButton(text="📥 СКАЧАТЬ АРХИВ", callback_data="webview_download")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "webview_generate")
@rate_limit(5.0)
async def webview_generate(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    await cb.message.edit_text("🔄 Генерация файлов...")
    
    result = await WebViewApp.save_webview_files()
    
    if result:
        await cb.message.edit_text(
            "✅ *WEBVIEW ПРИЛОЖЕНИЕ СОЗДАНО*\n\n"
            "Файлы сохранены в папке `static/`:\n"
            "• `index.html` - главная страница\n"
            "• `manifest.json` - PWA манифест\n"
            "• `sw.js` - service worker\n\n"
            "Для публикации загрузите файлы на хостинг",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_webview")],
            ])
        )
    else:
        await cb.message.edit_text("❌ *ОШИБКА ПРИ ГЕНЕРАЦИИ*", parse_mode="Markdown")
    await cb.answer()

@admin_router.callback_query(F.data == "webview_download")
@rate_limit(5.0)
async def webview_download(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    import zipfile
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        static_path = Path('static')
        if static_path.exists():
            for file_path in static_path.rglob('*'):
                if file_path.is_file():
                    zip_file.write(file_path, file_path.relative_to(static_path.parent))
    
    zip_buffer.seek(0)
    
    await cb.message.answer_document(
        document=BufferedInputFile(
            zip_buffer.getvalue(),
            filename=f"webview_{datetime.now().strftime('%Y%m%d')}.zip"
        ),
        caption="📱 *WebView приложение*",
        parse_mode="Markdown"
    )
    await cb.answer()

# ======================================================
# АДМИН - SEO ГЕНЕРАТОР
# ======================================================

@admin_router.callback_query(F.data == "admin_seo")
@rate_limit(2.0)
async def admin_seo(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    text = "🔍 *SEO ГЕНЕРАТОР*\n\n"
    text += "Автоматическая генерация контента:\n"
    text += "• Описания товаров на основе базы знаний\n"
    text += "• Мета-теги для страниц\n"
    text += "• Посты для соцсетей\n"
    text += "• Сценарии для Reels/Shorts\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Сгенерировать описания", callback_data="seo_descriptions")],
            [InlineKeyboardButton(text="📱 Посты для соцсетей", callback_data="seo_posts")],
            [InlineKeyboardButton(text="🎬 Сценарии для Reels", callback_data="seo_reels")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "seo_descriptions")
@rate_limit(2.0)
async def seo_descriptions(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    with db_cursor() as c:
        c.execute("SELECT stone_name FROM knowledge LIMIT 5")
        stones = c.fetchall()
    
    text = "📝 *СГЕНЕРИРОВАННЫЕ ОПИСАНИЯ*\n\n"
    
    for stone in stones:
        desc = await SEOGenerator.generate_product_description(stone['stone_name'])
        text += f"**{stone['stone_name']}:**\n{desc[:150]}...\n\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё", callback_data="seo_descriptions")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_seo")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "seo_posts")
@rate_limit(2.0)
async def seo_posts(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    stones = ["Аметист", "Розовый кварц", "Цитрин", "Тигровый глаз", "Лабрадор"]
    
    text = "📱 *ПОСТЫ ДЛЯ СОЦСЕТЕЙ*\n\n"
    
    for stone in stones:
        post_tg = await SEOGenerator.generate_social_post(stone, 'telegram')
        post_inst = await SEOGenerator.generate_social_post(stone, 'instagram')
        text += f"**{stone}**\n"
        text += f"TG: {post_tg[:100]}...\n"
        text += f"IG: {post_inst[:100]}...\n\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё", callback_data="seo_posts")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_seo")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "seo_reels")
@rate_limit(2.0)
async def seo_reels(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    reels_content = """30 ИДЕЙ ДЛЯ REELS/SHORTS (60 ДНЕЙ)

1. "Магия камня: Аметист" - 15 сек, красивый камень + текст о свойствах
2. "Как выбрать свой камень" - тест: ответь на 3 вопроса и узнай
3. "3 способа применить розовый кварц" - быстрая смена кадров
4. "Что будет, если носить тигровый глаз" - эффект до/после
5. "Топ-5 камней для денег" - список
6. "Как отличить настоящий камень от подделки" - экспертный контент
7. "Как создается браслет" - процесс создания
8. "Реакция: отзыв клиента" - социальное доказательство
9. "Как заряжать камни" - практика
10. "Аметист VS Цитрин" - сравнение
11. "Мифы о камнях" - разоблачение
12. "Как составить браслет самостоятельно" - DIY формат
13. "Что внутри? Распаковка заказа" - UGC контент
14. "Камень дня: [название]" - ежедневный формат
15. "Вопрос-ответ: отвечаю на комментарии" - интерактив
16. "Медитация с камнем" - ASMR формат
17. "Челлендж: 7 дней с камнем" - ежедневные сторис
18. "Как ухаживать за камнями" - полезные советы
19. "Путешествие камня: откуда он родом" - география
20. "Итоги месяца: лучшие камни" - дайджест
21. "Один день из жизни камня" - юмористический
22. "Энергетическая зарядка за 1 минуту" - упражнение
23. "Что твой камень говорит о тебе" - психология
24. "Магия чисел: сколько камней должно быть в браслете" - нумерология
25. "Как камень меняет воду" - эксперимент
26. "Дуэль камней: Аметист vs Цитрин" - голосование
27. "Секретная комната" - распаковка поставки
28. "Гадание на камнях" - игра
29. "Бюджетный набор для начинающего коллекционера" - обзор
30. "Почему я люблю камни" - личная история"""
    
    await cb.message.answer_document(
        document=BufferedInputFile(
            reels_content.encode('utf-8'),
            filename=f"reels_ideas_{datetime.now().strftime('%Y%m%d')}.txt"
        ),
        caption="🎬 *30 идей для Reels/Shorts*\n\nГотовые сценарии на 60 дней",
        parse_mode="Markdown"
    )
    await cb.answer()

# ======================================================
# АДМИН - САЙТ-ВИЗИТКА
# ======================================================

@admin_router.callback_query(F.data == "admin_website")
@rate_limit(2.0)
async def admin_website(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    text = "🌐 *САЙТ-ВИЗИТКА*\n\n"
    text += "Генерация статического сайта на основе:\n"
    text += "• Товаров из витрины\n"
    text += "• Базы знаний о камнях\n"
    text += "• Настроек бота\n\n"
    text += "Файлы будут сохранены в папку `static/`"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 СГЕНЕРИРОВАТЬ САЙТ", callback_data="website_generate")],
            [InlineKeyboardButton(text="📥 СКАЧАТЬ АРХИВ", callback_data="website_download")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "website_generate")
@rate_limit(5.0)
async def website_generate(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    await cb.message.edit_text("🔄 Генерация сайта...")
    
    html = await WebsiteGenerator.generate_html()
    
    async with aiofiles.open('static/index.html', 'w', encoding='utf-8') as f:
        await f.write(html)
    
    await cb.message.edit_text(
        "✅ *САЙТ СГЕНЕРИРОВАН*\n\n"
        "Файл сохранен в `static/index.html`\n\n"
        "Для публикации загрузите на хостинг",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_website")],
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "website_download")
@rate_limit(5.0)
async def website_download(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌")
        return
    
    import zipfile
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        static_path = Path('static')
        if static_path.exists():
            for file_path in static_path.rglob('*'):
                if file_path.is_file():
                    zip_file.write(file_path, file_path.relative_to(static_path.parent))
    
    zip_buffer.seek(0)
    
    await cb.message.answer_document(
        document=BufferedInputFile(
            zip_buffer.getvalue(),
            filename=f"website_{datetime.now().strftime('%Y%m%d')}.zip"
        ),
        caption="🌐 *Сайт-визитка*\n\nРаспакуйте архив и загрузите на хостинг",
        parse_mode="Markdown"
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ HANDLERS - ВСЕ ОТСУТСТВУЮЩИЕ ОБРАБОТЧИКИ (ДОБАВЛЕНЫ)
# ═══════════════════════════════════════════════════════════════════════════

# ======================================================
# NOOP - ЗАГЛУШКА ДЛЯ КНОПОК БЕЗ ДЕЙСТВИЯ
# ======================================================

@main_router.callback_query(F.data == "noop")
async def noop_handler(cb: CallbackQuery):
    """Заглушка для информационных кнопок (например пагинация N/M)."""
    await cb.answer()

# ======================================================
# ВИТРИНА БРАСЛЕТОВ
# ======================================================

@main_router.callback_query(F.data == "showcase_bracelets")
@rate_limit(2.0)
async def showcase_bracelets(cb: CallbackQuery):
    """Показать витрину браслетов."""
    await FunnelTracker.track(cb.from_user.id, 'view_showcase')
    
    with db_cursor() as c:
        c.execute("""SELECT id, name, price, image_url, description 
                     FROM showcase_items 
                     WHERE collection_id IS NOT NULL 
                     ORDER BY created_at DESC 
                     LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await safe_edit(cb, 
            "📦 *ВИТРИНА ПУСТА*\n\nНа данный момент товары отсутствуют.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "💎 *ВИТРИНА БРАСЛЕТОВ*\n\n"
    buttons = []
    
    for item in items:
        price_str = f"{int(item['price'])}₽" if item['price'] else "Уточнить цену"
        text += f"🔹 {item['name']} — {price_str}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}", 
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

# ======================================================
# ФИЛЬТР БРАСЛЕТОВ
# ======================================================

@main_router.callback_query(F.data == "filter_bracelets")
@rate_limit(2.0)
async def filter_bracelets(cb: CallbackQuery):
    """Фильтр браслетов по цене и характеристикам."""
    
    text = "🔍 *ФИЛЬТР ВИТРИНЫ*\n\n"
    text += "Выберите параметры для фильтрации:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 По цене (до 1000₽)", callback_data="filter_price_1000")],
            [InlineKeyboardButton(text="💎 По цене (1000-3000₽)", callback_data="filter_price_3000")],
            [InlineKeyboardButton(text="⭐ По цене (3000+₽)", callback_data="filter_price_plus")],
            [InlineKeyboardButton(text="🆕 Новинки", callback_data="filter_new")],
            [InlineKeyboardButton(text="❤️ Популярные", callback_data="filter_popular")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ФИЛЬТРЫ ПО ЦЕНЕ
# ======================================================

@main_router.callback_query(F.data == "filter_price_1000")
@rate_limit(2.0)
async def filter_price_1000(cb: CallbackQuery):
    """Фильтр до 1000₽."""
    with db_cursor() as c:
        c.execute("""SELECT id, name, price FROM showcase_items 
                    WHERE price <= 1000 AND price > 0 
                    ORDER BY price LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await cb.answer("Товары не найдены", show_alert=True)
        return
    
    text = "💰 *ДО 1000₽*\n\n"
    buttons = []
    
    for item in items:
        text += f"• {item['name']} — {int(item['price'])}₽\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="filter_bracelets")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data == "filter_price_3000")
@rate_limit(2.0)
async def filter_price_3000(cb: CallbackQuery):
    """Фильтр 1000-3000₽."""
    with db_cursor() as c:
        c.execute("""SELECT id, name, price FROM showcase_items 
                    WHERE price > 1000 AND price <= 3000 
                    ORDER BY price LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await cb.answer("Товары не найдены", show_alert=True)
        return
    
    text = "💎 *1000-3000₽*\n\n"
    buttons = []
    
    for item in items:
        text += f"• {item['name']} — {int(item['price'])}₽\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="filter_bracelets")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data == "filter_price_plus")
@rate_limit(2.0)
async def filter_price_plus(cb: CallbackQuery):
    """Фильтр от 3000₽."""
    with db_cursor() as c:
        c.execute("""SELECT id, name, price FROM showcase_items 
                    WHERE price > 3000 
                    ORDER BY price LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await cb.answer("Товары не найдены", show_alert=True)
        return
    
    text = "⭐ *ОТ 3000₽*\n\n"
    buttons = []
    
    for item in items:
        text += f"• {item['name']} — {int(item['price'])}₽\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="filter_bracelets")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data == "filter_new")
@rate_limit(2.0)
async def filter_new(cb: CallbackQuery):
    """Фильтр - новинки."""
    with db_cursor() as c:
        c.execute("""SELECT id, name, price FROM showcase_items 
                    WHERE price > 0 
                    ORDER BY created_at DESC LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await cb.answer("Новинок пока нет", show_alert=True)
        return
    
    text = "🆕 *НОВИНКИ*\n\n"
    buttons = []
    
    for item in items:
        price_str = f"{int(item['price'])}₽" if item['price'] else "Уточнить"
        text += f"• {item['name']} — {price_str}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="filter_bracelets")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data == "filter_popular")
@rate_limit(2.0)
async def filter_popular(cb: CallbackQuery):
    """Фильтр - популярные."""
    with db_cursor() as c:
        c.execute("""SELECT si.id, si.name, si.price, COUNT(oi.id) as orders_count
                    FROM showcase_items si
                    LEFT JOIN order_items oi ON oi.item_id = si.id + 100000
                    WHERE si.price > 0
                    GROUP BY si.id
                    ORDER BY orders_count DESC
                    LIMIT 10""")
        items = c.fetchall()
    
    if not items:
        await cb.answer("Статистика недоступна", show_alert=True)
        return
    
    text = "❤️ *ПОПУЛЯРНЫЕ*\n\n"
    buttons = []
    
    for item in items:
        price_str = f"{int(item['price'])}₽" if item['price'] else "Уточнить"
        orders = item['orders_count'] or 0
        text += f"• {item['name']} — {price_str}\n  📦 Заказов: {orders}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['id'] + 100000}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="filter_bracelets")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

# ======================================================
# КОРЗИНА
# ======================================================

@main_router.callback_query(F.data == "view_cart")
@rate_limit(2.0)
async def view_cart(cb: CallbackQuery):
    """Просмотр корзины."""
    await FunnelTracker.track(cb.from_user.id, 'view_cart')
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("""SELECT cart.id, cart.bracelet_id, cart.quantity, 
                           bracelets.name, bracelets.price
                    FROM cart
                    JOIN bracelets ON cart.bracelet_id = bracelets.id
                    WHERE cart.user_id = ? AND cart.status = 'active'""",
                  (user_id,))
        items = c.fetchall()
    
    if not items:
        await safe_edit(cb,
            "🛒 *КОРЗИНА ПУСТА*\n\nДобавьте товары из витрины!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase_bracelets")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "🛒 *ВАША КОРЗИНА*\n\n"
    total = 0
    buttons = []
    
    for item in items:
        item_total = (item['price'] or 0) * item['quantity']
        total += item_total
        text += f"• {item['name']}\n"
        text += f"  Количество: {item['quantity']} × {int(item['price'] or 0)}₽ = {int(item_total)}₽\n\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"❌ Удалить {item['name']}",
            callback_data=f"cart_remove_{item['id']}"
        )])
    
    text += f"*ИТОГО: {int(total)}₽*"
    
    buttons.extend([
        [InlineKeyboardButton(text="✅ ОФОРМИТЬ ЗАКАЗ", callback_data="cart_checkout")],
        [InlineKeyboardButton(text="🗑 ОЧИСТИТЬ КОРЗИНУ", callback_data="cart_clear")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
    ])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("cart_remove_"))
@rate_limit(2.0)
async def cart_remove(cb: CallbackQuery):
    """Удалить товар из корзины."""
    cart_id = int(cb.data.split("_")[-1])
    
    await remove_from_cart(cart_id)
    await cb.answer("✅ Товар удален", show_alert=True)
    await view_cart(cb)

@main_router.callback_query(F.data == "cart_checkout")
@rate_limit(2.0)
async def cart_checkout(cb: CallbackQuery, state: FSMContext):
    """Начало оформления заказа из корзины."""
    await FunnelTracker.track(cb.from_user.id, 'checkout')
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("""SELECT SUM((SELECT price FROM bracelets WHERE id = cart.bracelet_id) * cart.quantity) as total
                    FROM cart
                    WHERE user_id = ? AND status = 'active'""",
                  (user_id,))
        result = c.fetchone()
        total = result['total'] if result else 0
    
    if not total or total == 0:
        await cb.answer("❌ Корзина пуста!", show_alert=True)
        return
    
    text = f"💳 *ОФОРМЛЕНИЕ ЗАКАЗА*\n\n"
    text += f"Сумма заказа: *{int(total)}₽*\n\n"
    text += "Выберите способ оплаты:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплата картой (ЮKassa)", callback_data="payment_card")],
            [InlineKeyboardButton(text="₿ Криптовалюта", callback_data="payment_crypto")],
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="payment_stars")],
            [InlineKeyboardButton(text="💰 Бонусы", callback_data="payment_bonus")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "cart_clear")
@rate_limit(2.0)
async def cart_clear(cb: CallbackQuery):
    """Очистить корзину."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("DELETE FROM cart WHERE user_id = ? AND status = 'active'", (user_id,))
    
    await cb.answer("🗑 Корзина очищена", show_alert=True)
    
    kb = await get_categories_keyboard()
    await safe_edit(cb, 
        "🛒 Корзина очищена!\n\nДобавьте новые товары из витрины.",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ======================================================
# ОПЛАТА
# ======================================================

@main_router.callback_query(F.data == "payment_card")
@rate_limit(2.0)
async def payment_card(cb: CallbackQuery):
    """Оплата картой через ЮKassa."""
    await cb.answer(
        "💳 Оплата картой временно недоступна.\n"
        "Пожалуйста, выберите другой способ оплаты или свяжитесь с мастером.",
        show_alert=True
    )

@main_router.callback_query(F.data == "payment_crypto")
@rate_limit(2.0)
async def payment_crypto(cb: CallbackQuery):
    """Оплата криптовалютой."""
    wallet = CRYPTO_WALLET_ADDRESS
    network = CRYPTO_WALLET_NETWORK
    
    with db_cursor() as c:
        c.execute("""SELECT SUM((SELECT price FROM bracelets WHERE id = cart.bracelet_id) * cart.quantity) as total
                    FROM cart WHERE user_id = ? AND status = 'active'""", (cb.from_user.id,))
        result = c.fetchone()
        total = result['total'] if result else 0
    
    text = f"₿ *ОПЛАТА КРИПТОВАЛЮТОЙ*\n\n"
    text += f"Сумма: *{int(total)}₽*\n\n"
    text += f"Сеть: {network}\n"
    text += f"Адрес кошелька:\n`{wallet}`\n\n"
    text += "После оплаты отправьте скриншот транзакции @мастеру"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact_master")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="cart_checkout")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "payment_stars")
@rate_limit(2.0)
async def payment_stars(cb: CallbackQuery):
    """Оплата через Telegram Stars."""
    await cb.answer(
        "⭐ Оплата Stars временно недоступна.\n"
        "Пожалуйста, выберите другой способ оплаты.",
        show_alert=True
    )

@main_router.callback_query(F.data == "payment_bonus")
@rate_limit(2.0)
async def payment_bonus(cb: CallbackQuery):
    """Оплата бонусами."""
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT balance FROM referral_balance WHERE user_id = ?", (user_id,))
        balance_row = c.fetchone()
        balance = balance_row['balance'] if balance_row else 0
        
        c.execute("""SELECT SUM((SELECT price FROM bracelets WHERE id = cart.bracelet_id) * cart.quantity) as total
                    FROM cart WHERE user_id = ? AND status = 'active'""", (user_id,))
        result = c.fetchone()
        total = result['total'] if result else 0
    
    if balance <= 0:
        await cb.answer("❌ У вас нет бонусов", show_alert=True)
        return
    
    if balance < total:
        text = f"💰 *ЧАСТИЧНАЯ ОПЛАТА БОНУСАМИ*\n\n"
        text += f"Ваш баланс: {int(balance)} бонусов\n"
        text += f"Сумма заказа: {int(total)}₽\n\n"
        text += f"Можно списать: {int(balance)} бонусов\n"
        text += f"Остаток к оплате: {int(total - balance)}₽"
    else:
        text = f"💰 *ОПЛАТА БОНУСАМИ*\n\n"
        text += f"Сумма заказа: {int(total)}₽\n"
        text += f"Ваш баланс: {int(balance)} бонусов\n\n"
        text += f"✅ Достаточно для полной оплаты!"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data="confirm_bonus_payment")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="cart_checkout")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "confirm_bonus_payment")
@rate_limit(2.0)
async def confirm_bonus_payment(cb: CallbackQuery):
    """Подтверждение оплаты бонусами."""
    user_id = cb.from_user.id
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        
        try:
            # Получаем баланс
            c.execute("SELECT balance FROM referral_balance WHERE user_id = ?", (user_id,))
            balance_row = c.fetchone()
            balance = balance_row['balance'] if balance_row else 0
            
            # Получаем сумму корзины
            c.execute("""SELECT SUM((SELECT price FROM bracelets WHERE id = cart.bracelet_id) * cart.quantity) as total
                        FROM cart WHERE user_id = ? AND status = 'active'""", (user_id,))
            result = c.fetchone()
            total = result['total'] if result else 0
            
            if balance <= 0:
                await cb.answer("❌ Недостаточно бонусов", show_alert=True)
                return
            
            # Списываем бонусы
            bonus_used = min(balance, total)
            remaining = total - bonus_used
            
            # Создаём заказ
            c.execute("""INSERT INTO orders (user_id, total_price, status, payment_method, bonus_used, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                      (user_id, remaining, 'paid' if remaining == 0 else 'pending', 
                       'bonus' if remaining == 0 else 'partial_bonus', bonus_used, datetime.now()))
            order_id = c.lastrowid
            
            # Переносим товары из корзины в заказ
            c.execute("""SELECT cart.id, cart.bracelet_id, cart.quantity, bracelets.name, bracelets.price
                        FROM cart
                        JOIN bracelets ON cart.bracelet_id = bracelets.id
                        WHERE cart.user_id = ? AND cart.status = 'active'""", (user_id,))
            cart_items = c.fetchall()
            
            for item in cart_items:
                c.execute("""INSERT INTO order_items (order_id, user_id, item_type, item_id, item_name, quantity, price, created_at)
                            VALUES (?, ?, 'bracelet', ?, ?, ?, ?, ?)""",
                          (order_id, user_id, item['bracelet_id'], item['name'], 
                           item['quantity'], item['price'], datetime.now()))
            
            # Очищаем корзину
            c.execute("UPDATE cart SET status = 'ordered', order_id = ? WHERE user_id = ? AND status = 'active'",
                      (order_id, user_id))
            
            # Списываем бонусы
            c.execute("""UPDATE referral_balance SET balance = balance - ? WHERE user_id = ?""",
                      (bonus_used, user_id))
            
            # Записываем в историю бонусов
            c.execute("""INSERT INTO bonus_history (user_id, amount, operation, order_id, created_at)
                        VALUES (?, ?, 'used', ?, ?)""",
                      (user_id, -bonus_used, order_id, datetime.now()))
            
            conn.commit()
            
            await FunnelTracker.track(user_id, 'order_created')
            if remaining == 0:
                await FunnelTracker.track(user_id, 'payment_success')
            
            text = "✅ *ЗАКАЗ ОФОРМЛЕН*\n\n"
            text += f"Номер заказа: #{order_id}\n"
            text += f"Списано бонусов: {int(bonus_used)}\n"
            if remaining > 0:
                text += f"\n⏳ Осталось оплатить: {int(remaining)}₽\n"
                text += "Мастер свяжется с вами для завершения оплаты."
            else:
                text += "\n🎉 Заказ полностью оплачен бонусами!"
            
            await safe_edit(cb, text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📦 МОИ ЗАКАЗЫ", callback_data="my_orders")],
                    [InlineKeyboardButton(text="← ГЛАВНОЕ МЕНЮ", callback_data="menu")]
                ])
            )
            await cb.answer("✅ Заказ создан!", show_alert=True)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in bonus payment: {e}")
            await cb.answer("❌ Ошибка при оформлении заказа", show_alert=True)

# ======================================================
# МОИ ЗАКАЗЫ
# ======================================================

@main_router.callback_query(F.data == "my_orders")
@rate_limit(2.0)
async def my_orders(cb: CallbackQuery):
    """Список заказов пользователя."""
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("""SELECT id, total_price, status, created_at, payment_method
                    FROM orders
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 10""",
                  (user_id,))
        orders = c.fetchall()
    
    if not orders:
        await safe_edit(cb,
            "📦 *У ВАС ЕЩЁ НЕТ ЗАКАЗОВ*\n\nСделайте первую покупку!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase_bracelets")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "📦 *ВАШИ ЗАКАЗЫ*\n\n"
    buttons = []
    
    status_emoji = {
        'pending': '⏳',
        'paid': '✅',
        'processing': '📦',
        'shipped': '🚚',
        'completed': '✅',
        'cancelled': '❌'
    }
    
    for order in orders:
        emoji = status_emoji.get(order['status'], '📦')
        date_str = order['created_at'][:10] if order['created_at'] else ''
        text += f"{emoji} Заказ #{order['id']}\n"
        text += f"  Сумма: {int(order['total_price'])}₽\n"
        text += f"  Дата: {date_str}\n\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"📋 Заказ #{order['id']}",
            callback_data=f"order_details_{order['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("order_details_"))
@rate_limit(2.0)
async def order_details(cb: CallbackQuery):
    """Детали заказа."""
    order_id = int(cb.data.split("_")[-1])
    
    with db_cursor() as c:
        c.execute("""SELECT o.*, u.first_name, u.username
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    WHERE o.id = ?""", (order_id,))
        order = c.fetchone()
        
        if not order:
            await cb.answer("❌ Заказ не найден", show_alert=True)
            return
        
        c.execute("""SELECT item_name, quantity, price
                    FROM order_items
                    WHERE order_id = ?""", (order_id,))
        items = c.fetchall()
    
    status_emoji = {
        'pending': '⏳',
        'paid': '✅',
        'processing': '📦',
        'shipped': '🚚',
        'completed': '✅',
        'cancelled': '❌'
    }
    
    text = f"📦 *ЗАКАЗ #{order_id}*\n\n"
    text += f"Статус: {status_emoji.get(order['status'], '📦')} {order['status']}\n"
    text += f"Дата: {order['created_at'][:10]}\n"
    text += f"Метод оплаты: {order['payment_method'] or 'Не указан'}\n\n"
    text += "*Состав заказа:*\n"
    
    for item in items:
        text += f"• {item['item_name']} x{item['quantity']} = {int(item['price']*item['quantity'])}₽\n"
    
    text += f"\n*ИТОГО: {int(order['total_price'])}₽*"
    
    if order['bonus_used'] and order['bonus_used'] > 0:
        text += f"\n\nСписано бонусов: {int(order['bonus_used'])}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К ЗАКАЗАМ", callback_data="my_orders")],
            [InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact_master")]
        ])
    )
    await cb.answer()

# ======================================================
# STARS ПОКУПКИ
# ======================================================

@main_router.callback_query(F.data == "my_stars_orders")
@rate_limit(2.0)
async def my_stars_orders(cb: CallbackQuery):
    """Покупки через Telegram Stars."""
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("""SELECT id, item_name, stars_amount, status, created_at
                    FROM stars_orders
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 10""",
                  (user_id,))
        orders = c.fetchall()
    
    if not orders:
        await safe_edit(cb,
            "⭐ *ПОКУПКИ ЧЕРЕЗ STARS*\n\nУ вас пока нет покупок через Stars.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "⭐ *ВАШИ ПОКУПКИ (TELEGRAM STARS)*\n\n"
    
    for order in orders:
        date_str = order['created_at'][:10] if order['created_at'] else ''
        text += f"• {order['item_name']}\n"
        text += f"  {order['stars_amount']} ⭐ · {date_str}\n\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ИЗБРАННОЕ
# ======================================================

@main_router.callback_query(F.data == "my_wishlist")
@rate_limit(2.0)
async def my_wishlist(cb: CallbackQuery):
    """Список избранных товаров."""
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("""SELECT wishlist.item_id, bracelets.name, bracelets.price
                    FROM wishlist
                    JOIN bracelets ON wishlist.item_id = bracelets.id
                    WHERE wishlist.user_id = ?
                    ORDER BY wishlist.added_at DESC""",
                  (user_id,))
        items = c.fetchall()
    
    if not items:
        await safe_edit(cb,
            "❤️ *ИЗБРАННОЕ ПУСТО*\n\nДобавляйте понравившиеся товары в избранное!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase_bracelets")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "❤️ *ИЗБРАННОЕ*\n\n"
    buttons = []
    
    for item in items:
        price_str = f"{int(item['price'])}₽" if item['price'] else "Уточнить цену"
        text += f"• {item['name']} — {price_str}\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"item_{item['item_id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

# ======================================================
# FAQ
# ======================================================

@main_router.callback_query(F.data == "faq")
@rate_limit(2.0)
async def faq_handler(cb: CallbackQuery):
    """Часто задаваемые вопросы."""
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, answer
                    FROM faq
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 10""")
        faqs = c.fetchall()
    
    if not faqs:
        await safe_edit(cb,
            "❓ *FAQ*\n\nВопросы и ответы пока не добавлены.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "❓ *ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ*\n\n"
    buttons = []
    
    for faq in faqs:
        text += f"*Q: {faq['question']}*\n"
        text += f"A: {faq['answer']}\n\n"
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

# ======================================================
# БАЗА ЗНАНИЙ О КАМНЯХ
# ======================================================

@main_router.callback_query(F.data == "knowledge_list")
@rate_limit(2.0)
async def knowledge_list(cb: CallbackQuery):
    """База знаний о камнях - список."""
    
    with db_cursor() as c:
        c.execute("""SELECT id, stone_name, emoji, properties
                    FROM knowledge
                    ORDER BY stone_name
                    LIMIT 31""")
        stones = c.fetchall()
    
    if not stones:
        await safe_edit(cb,
            "📚 *БАЗА ЗНАНИЙ О КАМНЯХ*\n\n"
            "База знаний находится в разработке.\n\n"
            "Здесь будет доступна информация о 31 камне:\n"
            "свойства, чакры, стихии, знаки зодиака.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "📚 *БАЗА ЗНАНИЙ О КАМНЯХ*\n\nВсего камней: 31\n\n"
    buttons = []
    
    # Группируем по 2 камня в строке
    row = []
    for stone in stones:
        emoji = stone['emoji'] if stone['emoji'] else '💎'
        row.append(InlineKeyboardButton(
            text=f"{emoji} {stone['stone_name'][:15]}",
            callback_data=f"stone_{stone['id']}"
        ))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:  # Добавляем оставшиеся камни
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("stone_"))
@rate_limit(2.0)
async def stone_detail(cb: CallbackQuery):
    """Детальная информация о камне."""
    stone_id = int(cb.data.split("_")[-1])
    
    with db_cursor() as c:
        c.execute("""SELECT stone_name, emoji, short_desc, full_desc, properties, chakra, zodiac, color, price_per_bead
                    FROM knowledge
                    WHERE id = ?""", (stone_id,))
        stone = c.fetchone()
    
    if not stone:
        await cb.answer("❌ Камень не найден", show_alert=True)
        return
    
    text = f"{stone['emoji'] or '💎'} *{stone['stone_name']}*\n\n"
    text += f"*Кратко:* {stone['short_desc'] or 'Нет описания'}\n\n"
    text += f"{stone['full_desc'] or ''}\n\n"
    text += f"*Свойства:* {stone['properties'] or 'Не указаны'}\n"
    text += f"*Чакра:* {stone['chakra'] or 'Не указана'}\n"
    text += f"*Знаки зодиака:* {stone['zodiac'] or 'Все'}\n"
    text += f"*Цвет:* {stone['color'] or 'Разный'}\n"
    
    if stone['price_per_bead']:
        text += f"*Цена за бусину:* от {stone['price_per_bead']}₽\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 К СПИСКУ", callback_data="knowledge_list")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ВИКТОРИНА - УЗНАТЬ СВОЙ КАМЕНЬ
# ======================================================

@main_router.callback_query(F.data == "quiz_start")
@rate_limit(2.0)
async def quiz_start(cb: CallbackQuery, state: FSMContext):
    """Начало викторины для подбора камня."""
    await FunnelTracker.track(cb.from_user.id, 'quiz_started')
    
    with db_cursor() as c:
        c.execute("INSERT OR REPLACE INTO quiz_started (user_id, started_at) VALUES (?, ?)",
                  (cb.from_user.id, datetime.now()))
    
    text = "🔮 *УЗНАЙ СВОЙ КАМЕНЬ*\n\n"
    text += "Пройди короткую викторину из 5 вопросов,\n"
    text += "и я подскажу, какие камни подходят именно тебе!\n\n"
    text += "Готов начать?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ НАЧАТЬ", callback_data="quiz_q1")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "quiz_q1")
@rate_limit(2.0)
async def quiz_q1(cb: CallbackQuery, state: FSMContext):
    """Первый вопрос викторины."""
    await state.set_state(QuizStates.q1)
    await state.update_data(answers=[])
    
    text = "🔮 *ВОПРОС 1 из 5*\n\n"
    text += "Какая проблема беспокоит вас сейчас больше всего?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💔 Отношения и любовь", callback_data="quiz_a1_1")],
            [InlineKeyboardButton(text="💰 Деньги и карьера", callback_data="quiz_a1_2")],
            [InlineKeyboardButton(text="🛡 Защита и безопасность", callback_data="quiz_a1_3")],
            [InlineKeyboardButton(text="🌟 Духовный рост", callback_data="quiz_a1_4")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("quiz_a1_"))
@rate_limit(2.0)
async def quiz_answer_1(cb: CallbackQuery, state: FSMContext):
    """Ответ на первый вопрос викторины."""
    answer_num = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(('q1', answer_num))
    await state.update_data(answers=answers)
    await state.set_state(QuizStates.q2)
    
    text = "🔮 *ВОПРОС 2 из 5*\n\n"
    text += "Как вы обычно восстанавливаете энергию?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌿 На природе, в тишине", callback_data="quiz_a2_1")],
            [InlineKeyboardButton(text="🔥 В компании друзей", callback_data="quiz_a2_2")],
            [InlineKeyboardButton(text="💭 В одиночестве, медитируя", callback_data="quiz_a2_3")],
            [InlineKeyboardButton(text="🏃 В движении, спорте", callback_data="quiz_a2_4")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("quiz_a2_"))
@rate_limit(2.0)
async def quiz_answer_2(cb: CallbackQuery, state: FSMContext):
    """Ответ на второй вопрос викторины."""
    answer_num = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(('q2', answer_num))
    await state.update_data(answers=answers)
    await state.set_state(QuizStates.q3)
    
    text = "🔮 *ВОПРОС 3 из 5*\n\n"
    text += "Что для вас важнее всего в жизни?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️ Любовь и отношения", callback_data="quiz_a3_1")],
            [InlineKeyboardButton(text="💰 Деньги и успех", callback_data="quiz_a3_2")],
            [InlineKeyboardButton(text="🛡 Защита и безопасность", callback_data="quiz_a3_3")],
            [InlineKeyboardButton(text="🌟 Духовное развитие", callback_data="quiz_a3_4")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("quiz_a3_"))
@rate_limit(2.0)
async def quiz_answer_3(cb: CallbackQuery, state: FSMContext):
    """Ответ на третий вопрос викторины."""
    answer_num = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(('q3', answer_num))
    await state.update_data(answers=answers)
    await state.set_state(QuizStates.q4)
    
    text = "🔮 *ВОПРОС 4 из 5*\n\n"
    text += "Как вы принимаете важные решения?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Логически", callback_data="quiz_a4_1")],
            [InlineKeyboardButton(text="💫 Интуитивно", callback_data="quiz_a4_2")],
            [InlineKeyboardButton(text="👥 Советуюсь", callback_data="quiz_a4_3")],
            [InlineKeyboardButton(text="🌀 Долго сомневаюсь", callback_data="quiz_a4_4")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("quiz_a4_"))
@rate_limit(2.0)
async def quiz_answer_4(cb: CallbackQuery, state: FSMContext):
    """Ответ на четвертый вопрос викторины."""
    answer_num = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(('q4', answer_num))
    await state.update_data(answers=answers)
    await state.set_state(QuizStates.q5)
    
    text = "🔮 *ВОПРОС 5 из 5*\n\n"
    text += "Чего вам не хватает прямо сейчас?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Энергии", callback_data="quiz_a5_1")],
            [InlineKeyboardButton(text="😌 Спокойствия", callback_data="quiz_a5_2")],
            [InlineKeyboardButton(text="✨ Ясности", callback_data="quiz_a5_3")],
            [InlineKeyboardButton(text="💰 Денег", callback_data="quiz_a5_4")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("quiz_a5_"))
@rate_limit(2.0)
async def quiz_answer_5(cb: CallbackQuery, state: FSMContext):
    """Ответ на пятый вопрос и показ результата."""
    answer_num = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(('q5', answer_num))
    
    # Здесь должен быть алгоритм подбора камня
    # Пока заглушка
    recommended_stone = "Аметист"
    
    with db_cursor() as c:
        c.execute("""INSERT INTO quiz_results (user_id, answers, recommended_stone, created_at)
                    VALUES (?, ?, ?, ?)""",
                  (cb.from_user.id, json.dumps(answers), recommended_stone, datetime.now()))
        
        c.execute("UPDATE quiz_started SET completed = 1 WHERE user_id = ?", (cb.from_user.id,))
    
    await state.clear()
    
    text = "🔮 *ВАШ КАМЕНЬ*\n\n"
    text += f"По результатам теста вам больше всего подходит:\n\n"
    text += f"💎 *{recommended_stone}*\n\n"
    text += "Посмотрите браслеты с этим камнем в витрине!"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase_bracelets")],
            [InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ", callback_data="knowledge_list")],
            [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ТОТЕМНЫЙ КАМЕНЬ
# ======================================================

@main_router.callback_query(F.data == "totem_start")
@rate_limit(2.0)
async def totem_start(cb: CallbackQuery, state: FSMContext):
    """Начало теста на тотемный камень."""
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, options
                    FROM totem_questions
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 1""")
        question = c.fetchone()
    
    if not question:
        await safe_edit(cb,
            "🎯 *ТОТЕМНЫЙ КАМЕНЬ*\n\nТест пока не настроен.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    await state.update_data(totem_answers=[])
    await state.set_state(TotemStates.q1)
    
    text = f"🎯 *ТОТЕМНЫЙ КАМЕНЬ*\n\n{question['question']}"
    
    options = safe_json_parse(question['options'], [])
    buttons = []
    
    for i, opt in enumerate(options[:4], 1):
        buttons.append([InlineKeyboardButton(
            text=opt,
            callback_data=f"totem_a1_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("totem_a1_"))
@rate_limit(2.0)
async def totem_answer_1(cb: CallbackQuery, state: FSMContext):
    """Ответ на первый вопрос тотема."""
    answer = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('totem_answers', [])
    answers.append(('q1', answer))
    await state.update_data(totem_answers=answers)
    await state.set_state(TotemStates.q2)
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, options
                    FROM totem_questions
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 1 OFFSET 1""")
        question = c.fetchone()
    
    if not question:
        await totem_finish(cb, state)
        return
    
    text = f"🎯 *ВОПРОС 2 из 5*\n\n{question['question']}"
    
    options = safe_json_parse(question['options'], [])
    buttons = []
    
    for i, opt in enumerate(options[:4], 1):
        buttons.append([InlineKeyboardButton(
            text=opt,
            callback_data=f"totem_a2_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("totem_a2_"))
@rate_limit(2.0)
async def totem_answer_2(cb: CallbackQuery, state: FSMContext):
    """Ответ на второй вопрос тотема."""
    answer = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('totem_answers', [])
    answers.append(('q2', answer))
    await state.update_data(totem_answers=answers)
    await state.set_state(TotemStates.q3)
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, options
                    FROM totem_questions
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 1 OFFSET 2""")
        question = c.fetchone()
    
    if not question:
        await totem_finish(cb, state)
        return
    
    text = f"🎯 *ВОПРОС 3 из 5*\n\n{question['question']}"
    
    options = safe_json_parse(question['options'], [])
    buttons = []
    
    for i, opt in enumerate(options[:4], 1):
        buttons.append([InlineKeyboardButton(
            text=opt,
            callback_data=f"totem_a3_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("totem_a3_"))
@rate_limit(2.0)
async def totem_answer_3(cb: CallbackQuery, state: FSMContext):
    """Ответ на третий вопрос тотема."""
    answer = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('totem_answers', [])
    answers.append(('q3', answer))
    await state.update_data(totem_answers=answers)
    await state.set_state(TotemStates.q4)
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, options
                    FROM totem_questions
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 1 OFFSET 3""")
        question = c.fetchone()
    
    if not question:
        await totem_finish(cb, state)
        return
    
    text = f"🎯 *ВОПРОС 4 из 5*\n\n{question['question']}"
    
    options = safe_json_parse(question['options'], [])
    buttons = []
    
    for i, opt in enumerate(options[:4], 1):
        buttons.append([InlineKeyboardButton(
            text=opt,
            callback_data=f"totem_a4_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("totem_a4_"))
@rate_limit(2.0)
async def totem_answer_4(cb: CallbackQuery, state: FSMContext):
    """Ответ на четвертый вопрос тотема."""
    answer = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('totem_answers', [])
    answers.append(('q4', answer))
    await state.update_data(totem_answers=answers)
    await state.set_state(TotemStates.q5)
    
    with db_cursor() as c:
        c.execute("""SELECT id, question, options
                    FROM totem_questions
                    WHERE active = 1
                    ORDER BY sort_order
                    LIMIT 1 OFFSET 4""")
        question = c.fetchone()
    
    if not question:
        await totem_finish(cb, state)
        return
    
    text = f"🎯 *ВОПРОС 5 из 5*\n\n{question['question']}"
    
    options = safe_json_parse(question['options'], [])
    buttons = []
    
    for i, opt in enumerate(options[:4], 1):
        buttons.append([InlineKeyboardButton(
            text=opt,
            callback_data=f"totem_a5_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("totem_a5_"))
@rate_limit(2.0)
async def totem_answer_5(cb: CallbackQuery, state: FSMContext):
    """Ответ на пятый вопрос и показ результата."""
    answer = cb.data.split("_")[-1]
    
    data = await state.get_data()
    answers = data.get('totem_answers', [])
    answers.append(('q5', answer))
    await state.update_data(totem_answers=answers)
    
    await totem_finish(cb, state)

async def totem_finish(cb: CallbackQuery, state: FSMContext):
    """Завершение теста тотема."""
    data = await state.get_data()
    answers_dict = dict(data.get('totem_answers', []))
    
    top3 = await calculate_totem_result(answers_dict)
    
    with db_cursor() as c:
        c.execute("""INSERT INTO totem_results (user_id, answers, top1, top2, top3, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                  (cb.from_user.id, json.dumps(answers_dict), top3[0], top3[1], top3[2], datetime.now()))
    
    await state.clear()
    
    text = "🎯 *ТВОЙ ТОТЕМНЫЙ КАМЕНЬ*\n\n"
    text += f"1️⃣ {top3[0]}\n"
    text += f"2️⃣ {top3[1]}\n"
    text += f"3️⃣ {top3[2]}\n\n"
    text += "Это камни, которые лучше всего подходят твоей энергетике прямо сейчас!"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase_bracelets")],
            [InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ", callback_data="knowledge_list")],
            [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# РЕФЕРАЛЬНАЯ ПРОГРАММА
# ======================================================

@main_router.callback_query(F.data == "my_referral")
@rate_limit(2.0)
async def my_referral(cb: CallbackQuery):
    """Реферальная программа."""
    
    user_id = cb.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    
    with db_cursor() as c:
        c.execute("""SELECT balance, total_earned, referral_count
                    FROM referral_balance
                    WHERE user_id = ?""",
                  (user_id,))
        balance = c.fetchone()
        
        if not balance:
            balance = {'balance': 0, 'total_earned': 0, 'referral_count': 0}
    
    text = "🤝 *РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
    text += f"Ваш баланс: *{int(balance['balance'])} бонусов*\n"
    text += f"Всего заработано: {int(balance['total_earned'])} бонусов\n"
    text += f"Приглашено друзей: {balance['referral_count']}\n\n"
    text += "💰 *Как это работает?*\n"
    text += "• Приглашай друзей по своей ссылке\n"
    text += "• Получай 100 бонусов за каждого\n"
    text += "• Используй бонусы для покупок!\n\n"
    text += f"🔗 *Твоя реферальная ссылка:*\n`{ref_link}`"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# СВЯЗАТЬСЯ С МАСТЕРОМ
# ======================================================

@main_router.callback_query(F.data == "contact_master")
@rate_limit(2.0)
async def contact_master(cb: CallbackQuery, state: FSMContext):
    """Связь с мастером."""
    
    await state.set_state(ContactStates.waiting_message)
    
    text = "📞 *СВЯЗАТЬСЯ С МАСТЕРОМ*\n\n"
    text += "Напишите ваш вопрос или запрос,\n"
    text += "и я передам его мастеру.\n\n"
    text += "Ответ придёт в течение 24 часов."
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.message(ContactStates.waiting_message)
@rate_limit(2.0)
async def contact_message_received(msg: Message, state: FSMContext):
    """Получение сообщения для мастера."""
    user_id = msg.from_user.id
    user_text = msg.text or msg.caption or "Сообщение без текста"
    
    if ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить", url=f"tg://user?id={user_id}")],
        ])
        
        await bot.send_message(
            ADMIN_ID,
            f"📞 *СВЯЗЬ С МАСТЕРОМ*\n\n"
            f"От: {msg.from_user.full_name} (@{msg.from_user.username})\n"
            f"ID: {user_id}\n\n"
            f"Сообщение:\n{user_text}",
            parse_mode="Markdown",
            reply_markup=kb
        )
    
    await state.clear()
    await msg.answer(
        "✅ Ваше сообщение отправлено мастеру. Ожидайте ответа!",
        reply_markup=await get_categories_keyboard()
    )

# ======================================================
# ИСТОРИИ КЛИЕНТОВ
# ======================================================

@main_router.callback_query(F.data == "show_stories")
@rate_limit(2.0)
async def show_stories(cb: CallbackQuery):
    """Показать истории клиентов."""
    
    with db_cursor() as c:
        c.execute("""SELECT id, story_text, photo_file_id
                    FROM stories
                    WHERE approved = 1
                    ORDER BY created_at DESC
                    LIMIT 5""")
        stories = c.fetchall()
    
    if not stories:
        await safe_edit(cb,
            "📖 *ИСТОРИИ КЛИЕНТОВ*\n\nИстории пока не добавлены.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ ОСТАВИТЬ СВОЮ ИСТОРИЮ", callback_data="leave_review")],
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    # Отправляем каждую историю отдельным сообщением
    for story in stories[:3]:
        if story['photo_file_id']:
            await cb.message.answer_photo(
                photo=story['photo_file_id'],
                caption=f"📖 {story['story_text']}",
                parse_mode="Markdown"
            )
        else:
            await cb.message.answer(f"📖 {story['story_text']}", parse_mode="Markdown")
        await asyncio.sleep(0.5)
    
    await cb.message.answer(
        "📖 *ИСТОРИИ КЛИЕНТОВ*\n\nПоделитесь своей историей!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ОСТАВИТЬ СВОЮ ИСТОРИЮ", callback_data="leave_review")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ОСТАВИТЬ ОТЗЫВ
# ======================================================

@main_router.callback_query(F.data == "leave_review")
@rate_limit(2.0)
async def leave_review(cb: CallbackQuery, state: FSMContext):
    """Начало процесса оставления отзыва."""
    
    await state.set_state(ReviewStates.waiting_rating)
    
    text = "⭐ *ОСТАВИТЬ ОТЗЫВ*\n\n"
    text += "Оцените свою покупку от 1 до 5 звёзд:"
    
    buttons = []
    for i in range(1, 6):
        buttons.append([InlineKeyboardButton(
            text="⭐" * i,
            callback_data=f"review_rating_{i}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("review_rating_"))
@rate_limit(2.0)
async def review_rating(cb: CallbackQuery, state: FSMContext):
    """Выбор рейтинга для отзыва."""
    rating = int(cb.data.split("_")[-1])
    await state.update_data(rating=rating)
    await state.set_state(ReviewStates.waiting_photo)
    
    text = f"⭐ *ОСТАВИТЬ ОТЗЫВ*\n\n"
    text += f"Рейтинг: {'⭐' * rating}\n\n"
    text += "Теперь напишите текст отзыва (можно отправить фото с подписью):"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="leave_review")]
        ])
    )
    await cb.answer()

@main_router.message(ReviewStates.waiting_photo)
@rate_limit(2.0)
async def review_text_received(msg: Message, state: FSMContext):
    """Получение текста отзыва."""
    data = await state.get_data()
    rating = data.get('rating', 5)
    
    review_text = msg.text or msg.caption or "Отзыв без текста"
    photo_id = msg.photo[-1].file_id if msg.photo else None
    
    with db_cursor() as c:
        c.execute("""INSERT INTO reviews_new 
                     (user_id, rating, review_text, photo_file_id, created_at, approved)
                     VALUES (?, ?, ?, ?, ?, 0)""",
                  (msg.from_user.id, rating, review_text, photo_id, datetime.now()))
    
    await state.clear()
    await msg.answer(
        "✅ Спасибо за отзыв! Он будет опубликован после проверки.",
        reply_markup=await get_categories_keyboard()
    )
    
    if ADMIN_ID:
        user_info = await get_user_info(msg.from_user.id)
        name = user_info.get('first_name') or str(msg.from_user.id)
        uname = f"@{user_info['username']}" if user_info.get('username') else "нет"
        
        admin_text = f"⭐ *НОВЫЙ ОТЗЫВ*\n\n"
        admin_text += f"От: {name} ({uname})\n"
        admin_text += f"Рейтинг: {'⭐' * rating}\n\n"
        admin_text += f"Текст: {review_text}"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_review_{msg.from_user.id}")],
            [InlineKeyboardButton(text="✍️ Написать", url=f"tg://user?id={msg.from_user.id}")]
        ])
        
        if photo_id:
            await bot.send_photo(ADMIN_ID, photo_id, caption=admin_text, reply_markup=kb)
        else:
            await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)

# ======================================================
# ЗАПИСЬ НА КОНСУЛЬТАЦИЮ
# ======================================================

@main_router.callback_query(F.data == "book_consult")
@rate_limit(2.0)
async def book_consult(cb: CallbackQuery):
    """Запись на консультацию."""
    
    with db_cursor() as c:
        c.execute("""SELECT slot_date, time_slot
                    FROM schedule_slots
                    WHERE available = 1
                    AND slot_date >= date('now')
                    ORDER BY slot_date, time_slot
                    LIMIT 5""")
        slots = c.fetchall()
    
    if not slots:
        await safe_edit(cb,
            "📅 *ЗАПИСЬ НА КОНСУЛЬТАЦИЮ*\n\n"
            "К сожалению, свободных слотов нет.\n"
            "Попробуйте позже!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await cb.answer()
        return
    
    text = "📅 *ЗАПИСЬ НА КОНСУЛЬТАЦИЮ*\n\n"
    text += "Выберите удобное время:"
    
    buttons = []
    for slot in slots:
        buttons.append([InlineKeyboardButton(
            text=f"{slot['slot_date']} в {slot['time_slot']}",
            callback_data=f"consult_book_{slot['slot_date']}_{slot['time_slot']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("consult_book_"))
@rate_limit(2.0)
async def consult_book(cb: CallbackQuery):
    """Подтверждение записи на консультацию."""
    parts = cb.data.split("_")
    slot_date = parts[2]
    time_slot = parts[3]
    
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        
        try:
            c.execute("""SELECT id FROM schedule_slots 
                        WHERE slot_date = ? AND time_slot = ? AND available = 1""",
                      (slot_date, time_slot))
            slot = c.fetchone()
            
            if not slot:
                await cb.answer("❌ Этот слот уже занят", show_alert=True)
                return
            
            c.execute("""INSERT INTO consultations (user_id, consult_date, time_slot, created_at)
                        VALUES (?, ?, ?, ?)""",
                      (cb.from_user.id, slot_date, time_slot, datetime.now()))
            
            c.execute("""UPDATE schedule_slots SET available = 0 
                        WHERE slot_date = ? AND time_slot = ?""",
                      (slot_date, time_slot))
            
            conn.commit()
            
            text = f"✅ *ЗАПИСЬ ПОДТВЕРЖДЕНА*\n\n"
            text += f"Дата: {slot_date}\n"
            text += f"Время: {time_slot}\n\n"
            text += "Мастер свяжется с вами для подтверждения."
            
            await safe_edit(cb, text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📅 Мои консультации", callback_data="my_consults")],
                    [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]
                ])
            )
            await cb.answer("✅ Вы записаны!", show_alert=True)
            
            if ADMIN_ID:
                user_info = await get_user_info(cb.from_user.id)
                name = user_info.get('first_name') or str(cb.from_user.id)
                uname = f"@{user_info['username']}" if user_info.get('username') else "нет"
                
                await bot.send_message(
                    ADMIN_ID,
                    f"📅 *НОВАЯ КОНСУЛЬТАЦИЯ*\n\n"
                    f"Клиент: {name} ({uname})\n"
                    f"ID: {cb.from_user.id}\n"
                    f"Дата: {slot_date}\n"
                    f"Время: {time_slot}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={cb.from_user.id}")]
                    ])
                )
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Consult booking error: {e}")
            await cb.answer("❌ Ошибка при записи", show_alert=True)

@main_router.callback_query(F.data == "my_consults")
@rate_limit(2.0)
async def my_consults(cb: CallbackQuery):
    """Мои консультации."""
    with db_cursor() as c:
        c.execute("""SELECT consult_date, time_slot, status, created_at
                    FROM consultations
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 5""", (cb.from_user.id,))
        consults = c.fetchall()
    
    if not consults:
        await cb.answer("❌ У вас нет записей", show_alert=True)
        return
    
    text = "📅 *МОИ КОНСУЛЬТАЦИИ*\n\n"
    for consult in consults:
        status_emoji = "⏳" if consult['status'] == 'pending' else "✅"
        text += f"{status_emoji} {consult['consult_date']} в {consult['time_slot']}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ПОДПИСКА НА НОВИНКИ
# ======================================================

@main_router.callback_query(F.data == "subscribe_new")
@rate_limit(2.0)
async def subscribe_new(cb: CallbackQuery):
    """Подписка на уведомления о новинках."""
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT user_id FROM new_item_subscribers WHERE user_id = ?", (user_id,))
        is_subscribed = c.fetchone() is not None
        
        if is_subscribed:
            c.execute("DELETE FROM new_item_subscribers WHERE user_id = ?", (user_id,))
            text = "🔕 Вы отписались от уведомлений о новинках"
        else:
            c.execute("INSERT OR IGNORE INTO new_item_subscribers (user_id, subscribed_at) VALUES (?, ?)",
                      (user_id, datetime.now()))
            text = "🔔 Вы подписались на уведомления о новинках!"
    
    await cb.answer(text, show_alert=True)

# ======================================================
# ВВОД ПРОМОКОДА
# ======================================================

@main_router.callback_query(F.data == "enter_promo")
@rate_limit(2.0)
async def enter_promo(cb: CallbackQuery, state: FSMContext):
    """Ввод промокода."""
    
    await state.set_state(BaseInputStates.waiting_code)
    
    text = "🎟️ *ПРОМОКОД*\n\n"
    text += "Введите промокод для получения скидки:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.message(BaseInputStates.waiting_code)
@rate_limit(2.0)
async def promo_code_received(msg: Message, state: FSMContext):
    """Проверка введенного промокода."""
    code = msg.text.strip().upper()
    
    with db_cursor() as c:
        c.execute("""SELECT id, discount_pct, discount_rub, max_uses, used_count, active
                    FROM promocodes
                    WHERE code = ?""", (code,))
        promo = c.fetchone()
    
    if not promo or not promo['active']:
        await msg.answer("❌ Промокод не найден или не активен")
        await state.clear()
        return
    
    if promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']:
        await msg.answer("❌ Промокод больше не действует (исчерпан лимит)")
        await state.clear()
        return
    
    c.execute("""SELECT used_at FROM promo_uses WHERE user_id = ? AND code = ?""",
              (msg.from_user.id, code))
    if c.fetchone():
        await msg.answer("❌ Вы уже использовали этот промокод")
        await state.clear()
        return
    
    # Сохраняем промокод в сессии
    discount = promo['discount_pct'] if promo['discount_pct'] else promo['discount_rub']
    discount_type = "%" if promo['discount_pct'] else "₽"
    
    await state.update_data(promo_code=code, discount=discount, discount_type=discount_type)
    
    await msg.answer(
        f"✅ Промокод применен!\n\nСкидка: {discount}{discount_type}\n\nТеперь оформите заказ через корзину.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 ПЕРЕЙТИ В КОРЗИНУ", callback_data="view_cart")],
            [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]
        ])
    )
    await state.clear()

# ======================================================
# ПОДАРОЧНЫЙ СЕРТИФИКАТ
# ======================================================

@main_router.callback_query(F.data == "gift_menu")
@rate_limit(2.0)
async def gift_menu(cb: CallbackQuery):
    """Меню подарочных сертификатов."""
    
    text = "🎁 *ПОДАРОЧНЫЕ СЕРТИФИКАТЫ*\n\n"
    text += "Подарите радость близким!\n\n"
    text += "• Купить сертификат на любую сумму\n"
    text += "• Получатель использует его при заказе\n"
    text += "• Срок действия: 6 месяцев"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 КУПИТЬ СЕРТИФИКАТ", callback_data="gift_buy")],
            [InlineKeyboardButton(text="🎫 АКТИВИРОВАТЬ СЕРТИФИКАТ", callback_data="gift_activate")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "gift_buy")
@rate_limit(2.0)
async def gift_buy(cb: CallbackQuery, state: FSMContext):
    """Купить подарочный сертификат."""
    await state.set_state(GiftCertificateStates.waiting_amount)
    
    text = "🎁 *ПОКУПКА СЕРТИФИКАТА*\n\n"
    text += "Введите сумму сертификата (от 500 до 50000₽):"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gift_menu")]
        ])
    )
    await cb.answer()

@main_router.message(GiftCertificateStates.waiting_amount)
@rate_limit(2.0)
async def gift_amount_received(msg: Message, state: FSMContext):
    """Получение суммы сертификата."""
    try:
        amount = int(msg.text)
        if amount < 500 or amount > 50000:
            await msg.answer("❌ Сумма должна быть от 500 до 50000₽")
            return
    except ValueError:
        await msg.answer("❌ Введите число")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(GiftCertificateStates.waiting_recipient)
    
    await msg.answer(
        "🎁 Введите имя получателя сертификата:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gift_menu")]
        ])
    )

@main_router.message(GiftCertificateStates.waiting_recipient)
@rate_limit(2.0)
async def gift_recipient_received(msg: Message, state: FSMContext):
    """Получение имени получателя."""
    recipient = msg.text.strip()
    await state.update_data(recipient=recipient)
    await state.set_state(GiftCertificateStates.waiting_message)
    
    await msg.answer(
        "💌 Введите поздравление (или отправьте /skip чтобы пропустить):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ ПРОПУСТИТЬ", callback_data="gift_skip_message")],
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gift_menu")]
        ])
    )

@main_router.callback_query(F.data == "gift_skip_message")
@rate_limit(2.0)
async def gift_skip_message(cb: CallbackQuery, state: FSMContext):
    """Пропустить поздравление."""
    await state.update_data(message="")
    await create_gift_certificate_final(cb.message, state, cb.from_user.id)

async def create_gift_certificate_final(msg: Message, state: FSMContext, user_id: int):
    """Создание сертификата и отправка."""
    data = await state.get_data()
    amount = data.get('amount')
    recipient = data.get('recipient')
    message = data.get('message', '')
    
    code = await create_gift_certificate(user_id, amount, recipient, message)
    
    text = "✅ *СЕРТИФИКАТ СОЗДАН*\n\n"
    text += f"Сумма: {amount}₽\n"
    text += f"Получатель: {recipient}\n\n"
    text += f"Код сертификата:\n`{code}`\n\n"
    text += "Отправьте этот код получателю. Срок действия: 6 месяцев."
    
    await msg.answer(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 В МЕНЮ СЕРТИФИКАТОВ", callback_data="gift_menu")],
            [InlineKeyboardButton(text="← ГЛАВНОЕ МЕНЮ", callback_data="menu")]
        ])
    )
    await state.clear()

@main_router.message(GiftCertificateStates.waiting_message)
@rate_limit(2.0)
async def gift_message_received(msg: Message, state: FSMContext):
    """Получение поздравления."""
    await state.update_data(message=msg.text)
    await create_gift_certificate_final(msg, state, msg.from_user.id)

@main_router.callback_query(F.data == "gift_activate")
@rate_limit(2.0)
async def gift_activate(cb: CallbackQuery, state: FSMContext):
    """Активировать подарочный сертификат."""
    await state.set_state(GiftCertificateStates.waiting_code)
    
    text = "🎫 *АКТИВАЦИЯ СЕРТИФИКАТА*\n\n"
    text += "Введите код сертификата:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="gift_menu")]
        ])
    )
    await cb.answer()

@main_router.message(GiftCertificateStates.waiting_code)
@rate_limit(2.0)
async def gift_activate_code(msg: Message, state: FSMContext):
    """Активация сертификата по коду."""
    code = msg.text.strip().upper()
    
    amount = await apply_gift_certificate(code, msg.from_user.id)
    
    if amount:
        await msg.answer(
            f"✅ *СЕРТИФИКАТ АКТИВИРОВАН!*\n\n"
            f"На ваш счет зачислено {int(amount)} бонусов.\n\n"
            f"Используйте их при оформлении заказа!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 ПЕРЕЙТИ В КОРЗИНУ", callback_data="view_cart")],
                [InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]
            ])
        )
    else:
        await msg.answer(
            "❌ Сертификат не найден, уже использован или истек срок действия.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="gift_menu")]
            ])
        )
    
    await state.clear()

# ======================================================
# ДЕНЬ РОЖДЕНИЯ
# ======================================================

@main_router.callback_query(F.data == "set_birthday")
@rate_limit(2.0)
async def set_birthday(cb: CallbackQuery, state: FSMContext):
    """Установка даты рождения."""
    
    user_id = cb.from_user.id
    
    with db_cursor() as c:
        c.execute("SELECT birthday FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        
        if user and user['birthday']:
            text = f"🎂 *ДЕНЬ РОЖДЕНИЯ*\n\nВаш день рождения: {user['birthday']}\n\nХотите изменить?"
            await state.set_state(BirthdayStates.waiting_birthday)
        else:
            text = "🎂 *ДЕНЬ РОЖДЕНИЯ*\n\nУкажите дату рождения в формате ДД.ММ.ГГГГ\nНапример: 15.06.1990"
            await state.set_state(BirthdayStates.waiting_birthday)
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await cb.answer()

@main_router.message(BirthdayStates.waiting_birthday)
@rate_limit(2.0)
async def birthday_received(msg: Message, state: FSMContext):
    """Сохранение даты рождения."""
    date_text = msg.text.strip()
    
    # Простая проверка формата
    if not re.match(r'\d{2}\.\d{2}\.\d{4}', date_text):
        await msg.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")
        return
    
    with db_cursor() as c:
        c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", (date_text, msg.from_user.id))
    
    await state.clear()
    await msg.answer(
        "✅ Дата рождения сохранена! В ваш день рождения вы получите персональную скидку.",
        reply_markup=await get_categories_keyboard()
    )

# ======================================================
# УМНЫЙ АНАЛИТИК (ПОЛЬЗОВАТЕЛЬСКАЯ ВЕРСИЯ)
# ======================================================

@main_router.callback_query(F.data == "smart_analytics_menu")
@rate_limit(2.0)
async def user_smart_analytics(cb: CallbackQuery):
    """Пользовательская версия аналитики (рекомендации)"""
    
    with db_cursor() as c:
        c.execute("""SELECT item_id FROM order_items 
                     WHERE user_id = ? 
                     ORDER BY created_at DESC 
                     LIMIT 1""", (cb.from_user.id,))
        last_item = c.fetchone()
    
    text = "📈 *ПЕРСОНАЛЬНЫЕ РЕКОМЕНДАЦИИ*\n\n"
    
    if last_item:
        recommendations = await SmartAnalytics.get_recommendations(last_item['item_id'])
        if recommendations:
            text += "С этим товаром покупают:\n"
            for rec in recommendations:
                text += f"  • {rec['name']}\n"
        else:
            text += "Пока нет рекомендаций.\n\n"
    else:
        text += "Совершите первую покупку, чтобы получить рекомендации.\n\n"
    
    stones = await SmartAnalytics.get_popular_stones(5)
    if stones.get('current_month'):
        text += "\n*Популярное в этом месяце:*\n"
        for stone in stones['current_month'][:3]:
            text += f"  • {stone['emoji']} {stone['stone_name']}\n"
    
    await safe_edit(cb, text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Перейти в витрину", callback_data="showcase_bracelets")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()

# ======================================================
# САЙТ-ВИЗИТКА
# ======================================================

@main_router.callback_query(F.data == "visit_site")
@rate_limit(2.0)
async def visit_site(cb: CallbackQuery):
    """Ссылка на сайт-визитку."""
    
    text = "🌐 *САЙТ-ВИЗИТКА*\n\n"
    text += "Наш сайт находится в разработке.\n\n"
    text += "Скоро здесь будет ссылка на полноценный веб-сайт!"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await cb.answer()

# ======================================================
# ОБРАБОТЧИК ТОВАРОВ (item_)
# ======================================================

@main_router.callback_query(F.data.startswith("item_"))
@rate_limit(2.0)
async def item_detail(cb: CallbackQuery):
    """Детальная информация о товаре."""
    item_id = int(cb.data.split("_")[-1])
    
    name, price, item_type = ItemInfo.get_item_info(item_id)
    
    with db_cursor() as c:
        if item_type == 'showcase':
            real_id = item_id - 100000
            c.execute("""SELECT si.*, sc.name as collection_name
                        FROM showcase_items si
                        LEFT JOIN showcase_collections sc ON si.collection_id = sc.id
                        WHERE si.id = ?""", (real_id,))
            item = c.fetchone()
        else:
            c.execute("""SELECT * FROM bracelets WHERE id = ?""", (item_id,))
            item = c.fetchone()
    
    if not item:
        await cb.answer("❌ Товар не найден", show_alert=True)
        return
    
    text = f"💎 *{name}*\n\n"
    
    if item_type == 'showcase':
        if item['collection_name']:
            text += f"*Коллекция:* {item['collection_name']}\n"
        if item['description']:
            text += f"\n*Описание:*\n{item['description']}\n"
    else:
        if item['description']:
            text += f"*Описание:*\n{item['description']}\n"
    
    text += f"\n*Цена:* {ItemInfo.format_price(price)}"
    
    buttons = [
        [InlineKeyboardButton(text="🛒 ДОБАВИТЬ В КОРЗИНУ", callback_data=f"add_to_cart_{item_id}")],
        [InlineKeyboardButton(text="❤️ В ИЗБРАННОЕ", callback_data=f"add_to_wishlist_{item_id}")],
        [InlineKeyboardButton(text="← НАЗАД", callback_data="showcase_bracelets")]
    ]
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("add_to_cart_"))
@rate_limit(2.0)
async def add_to_cart_handler(cb: CallbackQuery):
    """Добавление товара в корзину."""
    item_id = int(cb.data.split("_")[-1])
    
    # Проверяем, существует ли товар
    name, price, _ = ItemInfo.get_item_info(item_id)
    if name.startswith("Товар #") and price == 0:
        await cb.answer("❌ Товар не найден", show_alert=True)
        return
    
    success = await add_to_cart(cb.from_user.id, item_id)
    
    if success:
        await cb.answer(f"✅ {name} добавлен в корзину!", show_alert=True)
    else:
        await cb.answer("❌ Ошибка при добавлении", show_alert=True)

@main_router.callback_query(F.data.startswith("add_to_wishlist_"))
@rate_limit(2.0)
async def add_to_wishlist_handler(cb: CallbackQuery):
    """Добавление товара в избранное."""
    item_id = int(cb.data.split("_")[-1])
    
    # Проверяем, существует ли товар
    name, price, _ = ItemInfo.get_item_info(item_id)
    if name.startswith("Товар #") and price == 0:
        await cb.answer("❌ Товар не найден", show_alert=True)
        return
    
    with db_cursor() as c:
        try:
            c.execute("""INSERT INTO wishlist (user_id, item_id, added_at)
                        VALUES (?, ?, ?)""",
                      (cb.from_user.id, item_id, datetime.now()))
            await cb.answer(f"❤️ {name} добавлен в избранное!", show_alert=True)
        except sqlite3.IntegrityError:
            await cb.answer("❌ Товар уже в избранном", show_alert=True)

# ======================================================
# АДМИНСКИЕ ХЕНДЛЕРЫ (ВСЕ ДОБАВЛЕНЫ)
# ======================================================

# АДМИН - КАТЕГОРИИ
@admin_router.callback_query(F.data == "admin_categories")
@rate_limit(2.0)
async def admin_categories(cb: CallbackQuery):
    """Управление категориями."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, name, emoji FROM categories ORDER BY id")
        cats = c.fetchall()
    
    text = "📋 *УПРАВЛЕНИЕ КАТЕГОРИЯМИ*\n\n"
    if cats:
        for cat in cats:
            text += f"{cat['emoji']} {cat['name']} (ID: {cat['id']})\n"
    else:
        text += "Категории отсутствуют"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ КАТЕГОРИЮ", callback_data="admin_add_category")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_category")
@rate_limit(2.0)
async def admin_add_category(cb: CallbackQuery, state: FSMContext):
    """Добавить категорию."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_category_name)
    await cb.message.edit_text(
        "➕ *ДОБАВИТЬ КАТЕГОРИЮ*\n\nВведите название категории:",
        parse_mode="Markdown"
    )
    await cb.answer()

# АДМИН - ВИТРИНА
@admin_router.callback_query(F.data == "admin_showcase")
@rate_limit(2.0)
async def admin_showcase(cb: CallbackQuery):
    """Управление витриной."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM showcase_items")
        count = c.fetchone()['cnt']
    
    text = f"💎 *УПРАВЛЕНИЕ ВИТРИНОЙ*\n\nТоваров в витрине: {count}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОВАР", callback_data="admin_add_showcase")],
            [InlineKeyboardButton(text="📋 СПИСОК ТОВАРОВ", callback_data="admin_list_showcase")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_showcase")
@rate_limit(2.0)
async def admin_add_showcase(cb: CallbackQuery, state: FSMContext):
    """Добавить товар в витрину."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_item_name)
    await cb.message.edit_text(
        "➕ *ДОБАВИТЬ ТОВАР*\n\nВведите название товара:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_list_showcase")
@rate_limit(2.0)
async def admin_list_showcase(cb: CallbackQuery):
    """Список товаров витрины."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, name, price FROM showcase_items ORDER BY created_at DESC LIMIT 20")
        items = c.fetchall()
    
    text = "💎 *ТОВАРЫ*\n\n" if items else "💎 *ТОВАРЫ*\n\nТоваров нет."
    for item in items:
        price = f"{int(item['price'])}₽" if item['price'] else "—"
        text += f"#{item['id']}: {item['name']} | {price}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_showcase")]
        ])
    )
    await cb.answer()

# АДМИН - УВЕДОМЛЕНИЯ О НОВИНКАХ
@admin_router.callback_query(F.data == "admin_notify_new")
@rate_limit(2.0)
async def admin_notify_new(cb: CallbackQuery):
    """Уведомить подписчиков о новинках."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM new_item_subscribers")
        count = c.fetchone()['cnt']
    
    text = f"🆕 *УВЕДОМЛЕНИЕ О НОВИНКАХ*\n\nПодписчиков: {count}\n\nОтправить уведомление?"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="admin_send_new_notif")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_send_new_notif")
@rate_limit(5.0)
async def admin_send_new_notif(cb: CallbackQuery):
    """Отправить уведомление о новинках."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await cb.message.edit_text("📤 Отправляю уведомления...")
    
    sent, failed = await PushNotificationManager.send_to_all(
        title="🆕 Новинки!",
        message="В витрину добавлены новые браслеты! Загляните прямо сейчас.",
        button_text="💎 Смотреть",
        button_data="showcase_bracelets"
    )
    
    await cb.message.edit_text(
        f"✅ *УВЕДОМЛЕНИЯ ОТПРАВЛЕНЫ*\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# АДМИН - ДИАГНОСТИКА
@admin_router.callback_query(F.data == "admin_diagnostics")
@rate_limit(2.0)
async def admin_diagnostics(cb: CallbackQuery):
    """Управление диагностикой."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM diagnostics WHERE sent = 0")
        pending = c.fetchone()['cnt']
    
    text = f"🩺 *УПРАВЛЕНИЕ ДИАГНОСТИКОЙ*\n\nНеобработанных заявок: {pending}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 СПИСОК ЗАЯВОК", callback_data="admin_diag_list")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_diag_list")
@rate_limit(2.0)
async def admin_diag_list(cb: CallbackQuery):
    """Список заявок на диагностику."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT d.id, u.first_name, d.created_at, d.sent
                    FROM diagnostics d
                    JOIN users u ON d.user_id = u.user_id
                    ORDER BY d.created_at DESC
                    LIMIT 20""")
        diags = c.fetchall()
    
    if not diags:
        text = "🩺 *ДИАГНОСТИКА*\n\nЗаявок нет."
    else:
        text = "🩺 *ЗАЯВКИ НА ДИАГНОСТИКУ*\n\n"
        for diag in diags:
            status = "✅" if diag['sent'] else "⏳"
            date_str = diag['created_at'][:10] if diag['created_at'] else ''
            text += f"{status} #{diag['id']} | {diag['first_name'] or 'User'} | {date_str}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_diagnostics")]
        ])
    )
    await cb.answer()

# АДМИН - ЗАКАЗЫ
@admin_router.callback_query(F.data == "admin_orders")
@rate_limit(2.0)
async def admin_orders(cb: CallbackQuery):
    """Управление заказами."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM orders WHERE status = 'pending'")
        pending = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM orders WHERE status = 'paid'")
        paid = c.fetchone()['cnt']
    
    text = f"📦 *УПРАВЛЕНИЕ ЗАКАЗАМИ*\n\nВ обработке: {pending}\nОплачено: {paid}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 СПИСОК ЗАКАЗОВ", callback_data="admin_orders_list")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_orders_list")
@rate_limit(2.0)
async def admin_orders_list(cb: CallbackQuery):
    """Список заказов."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT o.id, u.first_name, o.total_price, o.status, o.created_at
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    ORDER BY o.created_at DESC
                    LIMIT 20""")
        orders = c.fetchall()
    
    if not orders:
        text = "📦 *ЗАКАЗЫ*\n\nЗаказов пока нет."
    else:
        text = "📦 *ПОСЛЕДНИЕ 20 ЗАКАЗОВ*\n\n"
        for order in orders:
            status_emoji = {'pending': '⏳', 'paid': '✅', 'cancelled': '❌'}.get(order['status'], '📦')
            date_str = order['created_at'][:10] if order['created_at'] else ''
            text += f"{status_emoji} #{order['id']} | {order['first_name'] or 'ID'+str(order['id'])} | {int(order['total_price'])}₽ | {date_str}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_orders")]
        ])
    )
    await cb.answer()

# АДМИН - СТАТИСТИКА
@admin_router.callback_query(F.data == "admin_stats_v2")
@rate_limit(2.0)
async def admin_stats_v2(cb: CallbackQuery):
    """Расширенная статистика."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM users")
        users = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM orders WHERE status = 'paid'")
        orders = c.fetchone()['cnt']
        
        c.execute("SELECT SUM(total_price) as total FROM orders WHERE status = 'paid'")
        revenue = c.fetchone()['total'] or 0
    
    text = f"📊 *РАСШИРЕННАЯ СТАТИСТИКА*\n\n"
    text += f"Пользователей: {users}\n"
    text += f"Заказов: {orders}\n"
    text += f"Выручка: {int(revenue)}₽"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# АДМИН - ВОРОНКА
@admin_router.callback_query(F.data == "admin_funnel")
@rate_limit(2.0)
async def admin_funnel(cb: CallbackQuery):
    """Статистика воронки."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    stats = await FunnelTracker.get_stats(30)
    
    text = "📊 *ВОРОНКА ПРОДАЖ (30 дней)*\n\n"
    for event_type, label in FunnelTracker.EVENTS.items():
        count = stats.get(event_type, {}).get('users', 0)
        text += f"{label}: {count}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# АДМИН - РАССЫЛКА
@admin_router.callback_query(F.data == "admin_broadcast")
@rate_limit(2.0)
async def admin_broadcast(cb: CallbackQuery, state: FSMContext):
    """Массовая рассылка."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM users")
        users_count = c.fetchone()['cnt']
    
    await state.set_state(BroadcastStates.waiting_text)
    
    text = f"📢 *МАССОВАЯ РАССЫЛКА*\n\nПользователей: {users_count}\n\nВведите текст сообщения:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# АДМИН - FAQ
@admin_router.callback_query(F.data == "admin_faq")
@rate_limit(2.0)
async def admin_faq(cb: CallbackQuery):
    """Управление FAQ."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM faq WHERE active = 1")
        count = c.fetchone()['cnt']
    
    text = f"❓ *УПРАВЛЕНИЕ FAQ*\n\nАктивных вопросов: {count}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ВОПРОС", callback_data="admin_add_faq")],
            [InlineKeyboardButton(text="📋 СПИСОК ВОПРОСОВ", callback_data="admin_list_faq")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_faq")
@rate_limit(2.0)
async def admin_add_faq(cb: CallbackQuery, state: FSMContext):
    """Добавить вопрос FAQ."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(BaseInputStates.waiting_text)
    await state.update_data(action='add_faq')
    await cb.message.edit_text(
        "➕ *ДОБАВИТЬ FAQ*\n\nВведите вопрос:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_list_faq")
@rate_limit(2.0)
async def admin_list_faq(cb: CallbackQuery):
    """Список FAQ."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, question, active FROM faq ORDER BY sort_order LIMIT 20")
        faqs = c.fetchall()
    
    text = "❓ *FAQ*\n\n" if faqs else "❓ *FAQ*\n\nВопросов нет."
    for faq in faqs:
        status = "✅" if faq['active'] else "❌"
        text += f"{status} #{faq['id']}: {faq['question'][:40]}...\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_faq")]
        ])
    )
    await cb.answer()

# АДМИН - ПРОМОКОДЫ
@admin_router.callback_query(F.data == "admin_promos")
@rate_limit(2.0)
async def admin_promos(cb: CallbackQuery):
    """Управление промокодами."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM promocodes WHERE active = 1")
        count = c.fetchone()['cnt']
    
    text = f"🎟️ *УПРАВЛЕНИЕ ПРОМОКОДАМИ*\n\nАктивных промокодов: {count}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ СОЗДАТЬ ПРОМОКОД", callback_data="admin_add_promo")],
            [InlineKeyboardButton(text="📋 СПИСОК ПРОМОКОДОВ", callback_data="admin_list_promos")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_promo")
@rate_limit(2.0)
async def admin_add_promo(cb: CallbackQuery, state: FSMContext):
    """Добавить промокод."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(PromoAdminStates.waiting_code)
    await cb.message.edit_text(
        "➕ *СОЗДАТЬ ПРОМОКОД*\n\nВведите код промокода:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_list_promos")
@rate_limit(2.0)
async def admin_list_promos(cb: CallbackQuery):
    """Список промокодов."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT code, discount_pct, discount_rub, used_count, max_uses, active 
                    FROM promocodes ORDER BY created_at DESC LIMIT 20""")
        promos = c.fetchall()
    
    text = "🎟️ *ПРОМОКОДЫ*\n\n" if promos else "🎟️ *ПРОМОКОДЫ*\n\nПромокодов нет."
    for promo in promos:
        status = "✅" if promo['active'] else "❌"
        discount = f"{promo['discount_pct']}%" if promo['discount_pct'] else f"{promo['discount_rub']}₽"
        uses = f"{promo['used_count']}/{promo['max_uses']}" if promo['max_uses'] else f"{promo['used_count']}/∞"
        text += f"{status} {promo['code']} | {discount} | {uses}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_promos")]
        ])
    )
    await cb.answer()

# АДМИН - РАСПИСАНИЕ
@admin_router.callback_query(F.data == "admin_schedule")
@rate_limit(2.0)
async def admin_schedule(cb: CallbackQuery):
    """Управление расписанием."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM schedule_slots WHERE available = 1")
        available = c.fetchone()['cnt']
    
    text = f"⏰ *УПРАВЛЕНИЕ РАСПИСАНИЕМ*\n\nСвободных слотов: {available}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ СЛОТЫ", callback_data="admin_add_slots")],
            [InlineKeyboardButton(text="📋 СПИСОК СЛОТОВ", callback_data="admin_list_slots")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_slots")
@rate_limit(2.0)
async def admin_add_slots(cb: CallbackQuery):
    """Добавить слоты расписания."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    # Автоматическое добавление слотов на следующие 7 дней
    with db_cursor() as c:
        from datetime import timedelta
        today = datetime.now().date()
        
        for day_offset in range(1, 8):
            slot_date = (today + timedelta(days=day_offset)).strftime('%Y-%m-%d')
            for hour in ['10:00', '12:00', '14:00', '16:00', '18:00']:
                c.execute("""INSERT OR IGNORE INTO schedule_slots (slot_date, time_slot, available) 
                            VALUES (?, ?, 1)""", (slot_date, hour))
    
    await cb.answer("✅ Добавлено 35 слотов на 7 дней!", show_alert=True)
    await admin_schedule(cb)

@admin_router.callback_query(F.data == "admin_list_slots")
@rate_limit(2.0)
async def admin_list_slots(cb: CallbackQuery):
    """Список слотов расписания."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT slot_date, time_slot, available 
                    FROM schedule_slots 
                    WHERE slot_date >= date('now')
                    ORDER BY slot_date, time_slot LIMIT 20""")
        slots = c.fetchall()
    
    text = "⏰ *РАСПИСАНИЕ*\n\n" if slots else "⏰ *РАСПИСАНИЕ*\n\nСлотов нет."
    for slot in slots:
        status = "✅" if slot['available'] else "❌"
        text += f"{status} {slot['slot_date']} в {slot['time_slot']}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_schedule")]
        ])
    )
    await cb.answer()

# АДМИН - ИСТОРИИ
@admin_router.callback_query(F.data == "admin_stories")
@rate_limit(2.0)
async def admin_stories(cb: CallbackQuery):
    """Управление историями."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM stories WHERE approved = 0")
        pending = c.fetchone()['cnt']
    
    text = f"📖 *УПРАВЛЕНИЕ ИСТОРИЯМИ*\n\nНа модерации: {pending}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 СПИСОК ИСТОРИЙ", callback_data="admin_stories_list")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_stories_list")
@rate_limit(2.0)
async def admin_stories_list(cb: CallbackQuery):
    """Список историй."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT s.id, u.first_name, s.approved, s.created_at
                    FROM stories s
                    JOIN users u ON s.user_id = u.user_id
                    ORDER BY s.created_at DESC LIMIT 20""")
        stories = c.fetchall()
    
    text = "📖 *ИСТОРИИ*\n\n" if stories else "📖 *ИСТОРИИ*\n\nИсторий нет."
    for story in stories:
        status = "✅" if story['approved'] else "⏳"
        date_str = story['created_at'][:10] if story['created_at'] else ''
        text += f"{status} #{story['id']} | {story['first_name'] or 'User'} | {date_str}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_stories")]
        ])
    )
    await cb.answer()

# АДМИН - БАЗА ЗНАНИЙ
@admin_router.callback_query(F.data == "admin_knowledge")
@rate_limit(2.0)
async def admin_knowledge(cb: CallbackQuery):
    """Управление базой знаний."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM knowledge")
        count = c.fetchone()['cnt']
    
    text = f"📚 *УПРАВЛЕНИЕ БАЗОЙ ЗНАНИЙ*\n\nКамней в базе: {count}/31"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ КАМЕНЬ", callback_data="admin_add_stone")],
            [InlineKeyboardButton(text="📋 СПИСОК КАМНЕЙ", callback_data="admin_list_stones")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_stone")
@rate_limit(2.0)
async def admin_add_stone(cb: CallbackQuery, state: FSMContext):
    """Добавить камень в базу знаний."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(KnowledgeAdminStates.stone_name)
    await cb.message.edit_text(
        "➕ *ДОБАВИТЬ КАМЕНЬ*\n\nВведите название камня:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_list_stones")
@rate_limit(2.0)
async def admin_list_stones(cb: CallbackQuery):
    """Список камней в базе знаний."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, stone_name, emoji FROM knowledge ORDER BY stone_name LIMIT 31")
        stones = c.fetchall()
    
    text = f"📚 *БАЗА ЗНАНИЙ*\n\nКамней: {len(stones)}/31\n\n" if stones else "📚 *БАЗА ЗНАНИЙ*\n\nКамней нет."
    for stone in stones:
        emoji = stone['emoji'] or '💎'
        text += f"{emoji} {stone['stone_name']}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")]
        ])
    )
    await cb.answer()

# АДМИН - РЕЗУЛЬТАТЫ ТЕСТА
@admin_router.callback_query(F.data == "admin_quiz_results")
@rate_limit(2.0)
async def admin_quiz_results(cb: CallbackQuery):
    """Результаты викторины."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM quiz_started WHERE completed = 1")
        completed = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM quiz_started WHERE completed = 0")
        abandoned = c.fetchone()['cnt']
    
    text = f"🔮 *РЕЗУЛЬТАТЫ ВИКТОРИНЫ*\n\n"
    text += f"Завершено: {completed}\n"
    text += f"Не завершено: {abandoned}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# АДМИН - ПРИВЕТСТВИЕ
@admin_router.callback_query(F.data == "admin_welcome_text")
@rate_limit(2.0)
async def admin_welcome_text(cb: CallbackQuery, state: FSMContext):
    """Редактирование текста приветствия."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    settings = Cache.get_settings()
    welcome = settings.get('welcome_text', '')
    return_text = settings.get('return_text', '')
    
    text = f"✏️ *ТЕКСТЫ ПРИВЕТСТВИЯ*\n\n"
    text += f"*Новым пользователям:*\n{welcome[:100]}...\n\n"
    text += f"*Вернувшимся:*\n{return_text[:100]}..."
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", callback_data="admin_edit_welcome")],
            [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ ВОЗВРАЩЕНИЕ", callback_data="admin_edit_return")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_edit_welcome")
@rate_limit(2.0)
async def admin_edit_welcome(cb: CallbackQuery, state: FSMContext):
    """Редактировать текст приветствия."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(WelcomeTextStates.waiting_text)
    await cb.message.edit_text(
        "✏️ *ИЗМЕНИТЬ ПРИВЕТСТВИЕ*\n\nВведите новый текст приветствия для новых пользователей:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_edit_return")
@rate_limit(2.0)
async def admin_edit_return(cb: CallbackQuery, state: FSMContext):
    """Редактировать текст для вернувшихся."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(WelcomeTextStates.waiting_return_text)
    await cb.message.edit_text(
        "✏️ *ИЗМЕНИТЬ ТЕКСТ ВОЗВРАЩЕНИЯ*\n\nВведите новый текст для вернувшихся пользователей:",
        parse_mode="Markdown"
    )
    await cb.answer()

# АДМИН - КЭШБЭК
@admin_router.callback_query(F.data == "admin_cashback")
@rate_limit(2.0)
async def admin_cashback(cb: CallbackQuery):
    """Настройки кэшбэка."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT cashback_percent, min_order_amount, active FROM cashback_settings ORDER BY id DESC LIMIT 1")
        settings = c.fetchone()
    
    if settings:
        status = "✅ Активен" if settings['active'] else "❌ Отключен"
        text = f"💰 *НАСТРОЙКИ КЭШБЭКА*\n\n"
        text += f"Статус: {status}\n"
        text += f"Процент: {settings['cashback_percent']}%\n"
        text += f"Мин. сумма: {int(settings['min_order_amount'])}₽"
    else:
        text = "💰 *НАСТРОЙКИ КЭШБЭКА*\n\nНе настроено"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ИЗМЕНИТЬ", callback_data="admin_edit_cashback")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_edit_cashback")
@rate_limit(2.0)
async def admin_edit_cashback(cb: CallbackQuery, state: FSMContext):
    """Редактировать настройки кэшбэка."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(CashbackAdminStates.waiting_percent)
    await cb.message.edit_text(
        "✏️ *НАСТРОЙКИ КЭШБЭКА*\n\nВведите процент кэшбэка (0-100):",
        parse_mode="Markdown"
    )
    await cb.answer()

# АДМИН - ВИКТОРИНА (ТОТЕМ)
@admin_router.callback_query(F.data == "admin_totem")
@rate_limit(2.0)
async def admin_totem(cb: CallbackQuery):
    """Управление викториной."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM totem_questions WHERE active = 1")
        questions = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM totem_results")
        results = c.fetchone()['cnt']
    
    text = f"🎯 *УПРАВЛЕНИЕ ВИКТОРИНОЙ*\n\n"
    text += f"Активных вопросов: {questions}\n"
    text += f"Пройдено тестов: {results}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ДОБАВИТЬ ВОПРОС", callback_data="admin_add_totem_q")],
            [InlineKeyboardButton(text="📋 СПИСОК ВОПРОСОВ", callback_data="admin_list_totem_q")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_add_totem_q")
@rate_limit(2.0)
async def admin_add_totem_q(cb: CallbackQuery, state: FSMContext):
    """Добавить вопрос викторины."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await state.set_state(BaseInputStates.waiting_text)
    await state.update_data(action='add_totem_q')
    await cb.message.edit_text(
        "➕ *ДОБАВИТЬ ВОПРОС*\n\nВведите текст вопроса:",
        parse_mode="Markdown"
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_list_totem_q")
@rate_limit(2.0)
async def admin_list_totem_q(cb: CallbackQuery):
    """Список вопросов викторины."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT id, question, active FROM totem_questions ORDER BY sort_order")
        questions = c.fetchall()
    
    text = "🎯 *ВОПРОСЫ ВИКТОРИНЫ*\n\n" if questions else "🎯 *ВОПРОСЫ*\n\nВопросов нет."
    for q in questions:
        status = "✅" if q['active'] else "❌"
        text += f"{status} #{q['id']}: {q['question'][:40]}...\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_totem")]
        ])
    )
    await cb.answer()

# АДМИН - СЕРТИФИКАТЫ
@admin_router.callback_query(F.data == "admin_gifts")
@rate_limit(2.0)
async def admin_gifts(cb: CallbackQuery):
    """Управление подарочными сертификатами."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM gift_certificates WHERE status = 'active'")
        active = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM gift_certificates WHERE used_by IS NOT NULL")
        used = c.fetchone()['cnt']
    
    text = f"🎁 *УПРАВЛЕНИЕ СЕРТИФИКАТАМИ*\n\n"
    text += f"Активных: {active}\n"
    text += f"Использовано: {used}"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ СОЗДАТЬ СЕРТИФИКАТ", callback_data="admin_create_gift")],
            [InlineKeyboardButton(text="📋 СПИСОК СЕРТИФИКАТОВ", callback_data="admin_list_gifts")],
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

@admin_router.callback_query(F.data == "admin_create_gift")
@rate_limit(2.0)
async def admin_create_gift(cb: CallbackQuery):
    """Создать подарочный сертификат."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    # Автоматическое создание сертификата
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    amount = 1000  # Сумма по умолчанию
    
    with db_cursor() as c:
        c.execute("""INSERT INTO gift_certificates 
                    (code, amount, buyer_id, status, created_at, expires_at)
                    VALUES (?, ?, ?, 'active', ?, ?)""",
                  (code, amount, ADMIN_ID, datetime.now(), 
                   datetime.now() + timedelta(days=180)))
    
    await cb.answer(f"✅ Сертификат создан!\nКод: {code}\nСумма: {amount}₽", show_alert=True)
    await admin_gifts(cb)

@admin_router.callback_query(F.data == "admin_list_gifts")
@rate_limit(2.0)
async def admin_list_gifts(cb: CallbackQuery):
    """Список подарочных сертификатов."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("""SELECT code, amount, status, used_by FROM gift_certificates 
                    ORDER BY created_at DESC LIMIT 20""")
        gifts = c.fetchall()
    
    text = "🎁 *СЕРТИФИКАТЫ*\n\n" if gifts else "🎁 *СЕРТИФИКАТЫ*\n\nСертификатов нет."
    for gift in gifts:
        status = "✅" if gift['status'] == 'active' else "❌ использован"
        text += f"{gift['code']} | {int(gift['amount'])}₽ | {status}\n"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="admin_gifts")]
        ])
    )
    await cb.answer()

# АДМИН - ЭКСПОРТ ЗАКАЗОВ
@admin_router.callback_query(F.data == "export_orders")
@rate_limit(5.0)
async def export_orders(cb: CallbackQuery):
    """Экспорт заказов в CSV."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    await cb.message.edit_text("📥 Экспортирую заказы...")
    
    csv_data = await generate_orders_csv()
    
    await cb.message.answer_document(
        document=BufferedInputFile(
            csv_data,
            filename=f"orders_{datetime.now().strftime('%Y%m%d')}.csv"
        ),
        caption="📊 *Экспорт заказов*",
        parse_mode="Markdown"
    )
    
    await cb.message.delete()
    await cb.answer("✅ Экспортировано!", show_alert=True)

# АДМИН - PUSH-РАССЫЛКА
@admin_router.callback_query(F.data == "admin_push")
@rate_limit(2.0)
async def admin_push(cb: CallbackQuery, state: FSMContext):
    """Push-уведомления."""
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    
    with db_cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM new_item_subscribers")
        subscribers = c.fetchone()['cnt']
    
    await state.set_state(PushNotificationStates.waiting_title)
    
    text = f"🔔 *PUSH-РАССЫЛКА*\n\nПодписчиков: {subscribers}\n\nВведите заголовок уведомления:"
    
    await safe_edit(cb, text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="admin_panel")]
        ])
    )
    await cb.answer()

# ======================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ ПО УМОЛЧАНИЮ
# ======================================================

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

@main_router.message(StateFilter(None))
@rate_limit(2.0)
async def handle_any_message(msg: Message):
    """Обработчик всех необработанных сообщений (когда пользователь не в FSM)."""
    text = msg.text or ""
    
    # Игнорируем команды - они обрабатываются отдельно
    if text.startswith('/'):
        return
    
    kb = await get_categories_keyboard()
    await msg.answer(
        "👋 Выберите раздел из меню:",
        reply_markup=kb
    )

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Главная функция запуска бота."""
    print("\n" + "="*70)
    print("🚀 БОТ V5 - ПОЛНЫЙ ФУНКЦИОНАЛ ЗАПУСКАЕТСЯ (ИСПРАВЛЕННАЯ ВЕРСИЯ)")
    print("="*70 + "\n")
    
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 8,591+ СТРОК КОДА")
    print(f"📍 36 ТАБЛИЦ")
    print(f"📍 ВСЕ ХЕНДЛЕРЫ НА МЕСТЕ (61/61 КНОПОК)")
    print(f"📍 ЭКСКЛЮЗИВНЫЕ МОДУЛИ АКТИВИРОВАНЫ")
    print(f"📍 ИСПРАВЛЕНА ОШИБКА database is locked (строка 3128)")
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
    asyncio.create_task(cleanup_rate_cache())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")