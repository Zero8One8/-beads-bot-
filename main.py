"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ ДЛЯ RAILWAY

✅ ДОБАВЛЯТЬ КАТЕГОРИИ - через админ-панель
✅ ДОБАВЛЯТЬ КОНТЕНТ - через админ-панель
✅ ДОБАВЛЯТЬ ТРЕНИРОВКИ - через админ-панель
✅ ДОБАВЛЯТЬ МУЗЫКУ - через админ-панель
✅ ДОБАВЛЯТЬ УСЛУГИ - через админ-панель
✅ ДИАГНОСТИКА (загрузка фото) - через бот
✅ РЕФЕРАЛЬНАЯ СИСТЕМА (исправлен БАГ #4) - можно применять бонусы к заказу
✅ ЗАЩИТА ОТ ДВОЙНЫХ ЗАКАЗОВ (исправлен БАГ #3) - транзакции + rowcount + блокировки
✅ КЭШБЭК 5% (с управлением из админки) - начисляется автоматически на все покупки

ВСЁ БЕЗ КОДА! ТОЛЬКО АДМИН-ПАНЕЛЬ!
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sqlite3
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from collections import Counter

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

# ПЛАТЕЖИ - для реальной интеграции обновить эти переменные
YANDEX_KASSA_EMAIL = os.getenv('YANDEX_KASSA_EMAIL', 'your-email@yandex.kassa.com')
YANDEX_KASSA_SHOP_ID = os.getenv('YANDEX_KASSA_SHOP_ID', 'YOUR_SHOP_ID')
YANDEX_KASSA_API_KEY = os.getenv('YANDEX_KASSA_API_KEY', 'YOUR_API_KEY')

CRYPTO_WALLET_ADDRESS = os.getenv('CRYPTO_WALLET_ADDRESS', 'bc1qyour_bitcoin_address_here')
CRYPTO_WALLET_NETWORK = os.getenv('CRYPTO_WALLET_NETWORK', 'Bitcoin')

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

Path('storage').mkdir(exist_ok=True)
Path('storage/diagnostics').mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
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
# БД
# ═══════════════════════════════════════════════════════════════════════════

DB = 'storage/beads.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


async def get_setting(key: str, default: str = '') -> str:
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
    r = c.fetchone(); conn.close()
    return r[0] if r else default

async def set_setting(key: str, value: str):
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit(); conn.close()


def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INT PRIMARY KEY, username TEXT, first_name TEXT, created_at TIMESTAMP)''')
    
    # Категории
    c.execute('''CREATE TABLE IF NOT EXISTS categories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, emoji TEXT, desc TEXT)''')
    
    # Контент (текст в категориях)
    c.execute('''CREATE TABLE IF NOT EXISTS content 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INT, title TEXT, desc TEXT, created_at TIMESTAMP)''')
    
    # Тренировки
    c.execute('''CREATE TABLE IF NOT EXISTS workouts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, difficulty TEXT, created_at TIMESTAMP)''')
    
    # Музыка
    c.execute('''CREATE TABLE IF NOT EXISTS music 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, audio_url TEXT, created_at TIMESTAMP)''')
    
    # Услуги
    c.execute('''CREATE TABLE IF NOT EXISTS services 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, created_at TIMESTAMP)''')
    
    # Диагностика (фото)
    c.execute('''CREATE TABLE IF NOT EXISTS diagnostics 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, photo_count INT, notes TEXT, created_at TIMESTAMP, admin_result TEXT, sent BOOLEAN DEFAULT FALSE, photo1_file_id TEXT, photo2_file_id TEXT, followup_sent INT DEFAULT 0)''')
    
    # Браслеты
    c.execute('''CREATE TABLE IF NOT EXISTS bracelets 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, image_url TEXT, created_at TIMESTAMP)''')
    
    # Корзина
    c.execute('''CREATE TABLE IF NOT EXISTS cart 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, bracelet_id INT, quantity INT, added_at TIMESTAMP)''')
    
    # Заказы
    c.execute('''CREATE TABLE IF NOT EXISTS orders 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, total_price REAL, status TEXT, payment_method TEXT, created_at TIMESTAMP)''')
    
    # Отзывы
    c.execute('''CREATE TABLE IF NOT EXISTS reviews 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, bracelet_id INT, rating INT, text TEXT, created_at TIMESTAMP)''')
    
    # Подкатегории
    c.execute('''CREATE TABLE IF NOT EXISTS subcategories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, name TEXT, emoji TEXT, created_at TIMESTAMP)''')
    
    # Под-подкатегории
    c.execute('''CREATE TABLE IF NOT EXISTS subsubcategories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INT, name TEXT, emoji TEXT, created_at TIMESTAMP)''')
    
    # Админы
    c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INT, referred_id INT, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referral_balance (user_id INT PRIMARY KEY, balance REAL DEFAULT 0, total_earned REAL DEFAULT 0, referral_count INT DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, text TEXT, photo_file_id TEXT, approved BOOLEAN DEFAULT FALSE, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, created_at TIMESTAMP, sent_count INT DEFAULT 0)''')
    conn.commit()
    c.execute('''CREATE TABLE IF NOT EXISTS showcase_collections
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, emoji TEXT, desc TEXT,
                  sort_order INT DEFAULT 0, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS showcase_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, collection_id INT, name TEXT, desc TEXT,
                  price REAL, image_file_id TEXT, sort_order INT DEFAULT 0, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge (id INTEGER PRIMARY KEY AUTOINCREMENT, stone_name TEXT UNIQUE, emoji TEXT, properties TEXT, elements TEXT, zodiac TEXT, chakra TEXT, photo_file_id TEXT, created_at TIMESTAMP, short_desc TEXT, full_desc TEXT, color TEXT, stone_id TEXT, tasks TEXT, price_per_bead INTEGER, forms TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS quiz_results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, answers TEXT, recommended_stone TEXT, created_at TIMESTAMP)''')
    conn.commit()
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS quiz_started 
                 (user_id INT PRIMARY KEY, started_at TIMESTAMP, completed INT DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS diag_reminded 
                 (user_id INT PRIMARY KEY, reminded_at TIMESTAMP)''')
    conn.commit()
    # Дефолтное приветствие
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)''',
              ('welcome_text', '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nЯ помогу найти браслет или чётки, которые подойдут именно вам.\n\n🎁 СКИДКА 20% на первый заказ!\nПромокод: WELCOME20\n\nВыберите раздел 👇'))
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)''',
              ('return_text', '👋 С возвращением!\n\nВыбери раздел:'))
    conn.commit()
    for _sql in ["ALTER TABLE users ADD COLUMN welcome_sent BOOLEAN DEFAULT FALSE","ALTER TABLE users ADD COLUMN referred_by INT DEFAULT NULL","ALTER TABLE diagnostics ADD COLUMN followup_sent INT DEFAULT 0","ALTER TABLE knowledge ADD COLUMN short_desc TEXT","ALTER TABLE knowledge ADD COLUMN full_desc TEXT","ALTER TABLE knowledge ADD COLUMN color TEXT","ALTER TABLE knowledge ADD COLUMN stone_id TEXT","ALTER TABLE knowledge ADD COLUMN tasks TEXT","ALTER TABLE knowledge ADD COLUMN price_per_bead INTEGER","ALTER TABLE knowledge ADD COLUMN forms TEXT","ALTER TABLE knowledge ADD COLUMN notes TEXT"]:
        try: c.execute(_sql); conn.commit()
        except: pass
    
    # Удаляем папку Диагностика из БД если осталась
    try:
        c.execute("DELETE FROM categories WHERE name IN ('🩺 Диагностика', 'Диагностика')")
        conn.commit()
    except:
        pass

    # Импорт каталога камней (31 камень) при первом запуске
    try:
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Розовый кварц', '💎', 'love, healing, self_love', '💚', 'Камень безусловной любви', 'Розовый кварц - камень сердца. Мягко раскрывает сердце, исцеляет старые раны, помогает в отношениях с собой и другими. Самый мощный камень для работы с любовью и прощением.', 'розовый', 'rose_quartz', 'love, healing, self_love', 50, '6mm, 8mm, 10mm, 12mm', 'Универсален, безопасен, один из самых популярных'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Цитрин', '💎', 'money, confidence, joy', '🟡, 🟠', 'Камень денег и радости', 'Цитрин привлекает достаток и процветание. Усиливает личную силу, помогает верить в себя. Один из самых мощных камней для денежной энергии.', 'жёлтый', 'citrine', 'money, confidence, joy', 80, '6mm, 8mm, 10mm, 12mm', 'Один из лучших для денег, редкий натуральный'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Аметист', '💎', 'meditation, clarity, sobriety', '⚪, 💜', 'Камень медитаций и трезвости', 'Аметист - духовный камень. Поддерживает медитации, защищает от зависимостей, успокаивает ум. Классический камень для практик и внутренней работы.', 'фиолетовый', 'amethyst', 'meditation, clarity, sobriety', 60, '6mm, 8mm, 10mm, 12mm', 'Универсален, подходит всем знакам зодиака'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Лабрадорит', '💎', 'transformation, intuition, magic', '💜, ⚪', 'Камень трансформации', 'Лабрадорит раскрывает скрытые способности, помогает видеть то, что за пределами видимого. Камень магии и преобразования. Один из самых мощных для духовного развития.', 'серый с переливом', 'labradorite', 'transformation, intuition, magic', 100, '6mm, 8mm, 10mm', 'Драгоценный камень, требует бережного обращения'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Чёрный турмалин', '💎', 'protection, grounding, boundaries', '🔴', 'Камень защиты', 'Чёрный турмалин - сильнейший защитник. Создаёт энергетический щит, защищает от чужого влияния, заземляет энергию. Незаменим для чувствительных людей.', 'чёрный', 'black_tourmaline', 'protection, grounding, boundaries', 120, '6mm, 8mm, 10mm', 'Самый мощный защитник, работает на уровне корневой чакры'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Зелёный авантюрин', '💎', 'luck, prosperity, opportunity', '💚', 'Камень удачи', 'Зелёный авантюрин привлекает удачу и новые возможности. Помогает видеть пути вперёд, раскрывает двери. Камень процветания на материальном уровне.', 'зелёный', 'green_aventurine', 'luck, prosperity, opportunity', 40, '6mm, 8mm, 10mm, 12mm', 'Доступен, работает быстро, хороший для начинающих'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Лунный камень', '💎', 'intuition, feminine_energy, inner_light', '🟠, ⚪', 'Камень женской энергии', 'Лунный камень связан с луной и интуицией. Раскрывает внутреннюю мудрость, поддерживает женские энергии, помогает доверять интуиции.', 'молочный с сиянием', 'moonstone', 'intuition, feminine_energy, inner_light', 90, '6mm, 8mm, 10mm', 'Мощен для женщин, усиливает интуицию'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Тигровый глаз', '💎', 'courage, action, willpower', '🟡', 'Камень мужества', 'Тигровый глаз даёт силу и мужество. Помогает действовать смело, преодолевать страхи. Камень для воинов и лидеров.', 'коричневый с полосами', 'tiger_eye', 'courage, action, willpower', 150, '6mm, 8mm, 10mm, 12mm', 'Драгоценный, очень популярен, долговечен'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Горный хрусталь', '💎', 'amplification, clarity, programming', '🌈', 'Универсальный усилитель', 'Горный хрусталь - усилитель всех энергий. Можно программировать на любое намерение. Один из самых универсальных и мощных камней.', 'прозрачный', 'clear_quartz', 'amplification, clarity, programming', 35, '6mm, 8mm, 10mm, 12mm', 'Лучше всего использовать в центре браслета'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Гематит', '💎', 'grounding, protection, stability', '🔴', 'Камень заземления', 'Гематит заземляет, возвращает в реальность, защищает. Идеален для людей, которые часто витают в облаках. Стабилизирует энергию.', 'чёрный металлический', 'hematite', 'grounding, protection, stability', 70, '6mm, 8mm, 10mm, 12mm', 'Тяжелый, создаёт ощущение защиты'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Родонит', '💎', 'healing, trauma, self_care', '💚', 'Камень исцеления травм', 'Родонит помогает исцелить эмоциональные раны. Работает с давними болями и обидами. Нежный, но мощный камень для глубокой работы.', 'розовый с чёрными прожилками', 'rhodonite', 'healing, trauma, self_care', 85, '6mm, 8mm, 10mm', 'Отличен для глубокого исцеления'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Содалит', '💎', 'clarity, expression, truth', '💜, 🔵', 'Камень ясности и правды', 'Содалит развивает интуицию, помогает выразить правду. Успокаивает ум, улучшает ясность мышления. Камень для честного общения.', 'синий с белыми прожилками', 'sodalite', 'clarity, expression, truth', 65, '6mm, 8mm, 10mm', 'Помогает в общении, развивает интуицию'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Сердолик', '💎', 'creativity, passion, vitality', '🟠, 🟡', 'Камень творчества и страсти', 'Сердолик пробуждает творчество и жизненную энергию. Помогает воплощать идеи, даёт мотивацию. Камень для творческих людей.', 'оранжево-красный', 'carnelian', 'creativity, passion, vitality', 75, '6mm, 8mm, 10mm', 'Натуральный сердолик редкий, работает с подсознанием'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Лепидолит', '💎', 'calm, anxiety, transition', '💚, ⚪', 'Камень спокойствия', 'Лепидолит содержит литий - природное успокаивающее. Помогает при тревоге, поддерживает в переходные периоды. Мягкий и нежный камень.', 'фиолетовый-розовый', 'lepidolite', 'calm, anxiety, transition', 95, '6mm, 8mm', 'Натуральный литий, помогает при стрессе'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Флюорит', '💎', 'focus, organization, mental_clarity', '💜', 'Камень ясности ума', 'Флюорит улучшает концентрацию, организует мысли, помогает в обучении. Камень для студентов и интеллектуальной работы.', 'фиолетовый, зелёный, жёлтый', 'fluorite', 'focus, organization, mental_clarity', 110, '6mm, 8mm, 10mm', 'Хрупкий, требует бережного обращения, очень мощен для ума'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Синий авантюрин', '💎', 'communication, inner_peace, harmony', '🔵, 💜', 'Камень спокойного общения', 'Синий авантюрин помогает спокойно выражать себя, создаёт внутреннюю гармонию. Успокаивающий камень для нервной системы.', 'синий', 'aventurine_blue', 'communication, inner_peace, harmony', 55, '6mm, 8mm, 10mm', 'Редкий вид авантюрина, очень мягкий'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Обсидиан', '💎', 'protection, truth, grounding', '🔴', 'Камень правды', 'Обсидиан защищает от иллюзий, помогает видеть правду. Мощный защитник, но требует уважения. Камень для глубокой работы с тенью.', 'чёрный глянцевый', 'obsidian', 'protection, truth, grounding', 130, '6mm, 8mm, 10mm', 'Вулканический камень, очень мощен, требует опыта'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Нефрит', '💎', 'harmony, longevity, protection', '💚', 'Камень гармонии', 'Нефрит в восточной традиции - камень долголетия и гармонии. Защищает, приносит равновесие. Камень мудрости и стабильности.', 'зелёный', 'jade', 'harmony, longevity, protection', 140, '6mm, 8mm, 10mm', 'Драгоценный, ценится в восточной культуре'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Спектролит', '💎', 'magic, intuition, mystery', '💜, ⚪', 'Камень магии', 'Редкий вид лабрадорита с ярким переливом. Один из самых магических камней. Открывает двери в невидимые миры.', 'чёрный с радужным переливом', 'labradorite_spectrolite', 'magic, intuition, mystery', 200, '8mm, 10mm', 'Очень редкий и мощный, для опытных'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Кунцит', '💎', 'unconditional_love, peace, spiritual_love', '💚', 'Камень безусловной любви', 'Кунцит - камень духовной любви. Раскрывает сердце на глубоком уровне. Камень миролюбия и сострадания ко всему живому.', 'розово-фиолетовый', 'kunzite', 'unconditional_love, peace, spiritual_love', 180, '8mm, 10mm', 'Редкий, хрупкий, очень нежный и мощный'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Малахит', '💎', 'transformation, protection, prosperity', '💚, 🟡', 'Камень трансформации', 'Малахит - мощный трансформер. Защищает путешественников, помогает в больших переменах. Очень энергичный камень.', 'зелёный с чёрными полосами', 'malachite', 'transformation, protection, prosperity', 160, '10mm, 12mm', 'Ядовит в пыли, не лизать, работать осторожно'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Амазонит', '💎', 'truth, communication, boundaries', '🔵, 💚', 'Камень правдивого слова', 'Амазонит помогает говорить правду с добротой. Поддерживает здоровые границы в общении. Камень женщины-воина.', 'голубовато-зелёный', 'amazonite', 'truth, communication, boundaries', 70, '6mm, 8mm, 10mm', 'Помогает в конфликтах, работает с горлом'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Розовый турмалин (Турмалин)', '💎', 'divine_love, compassion, healing', '💚', 'Камень божественной любви', 'Розовый турмалин раскрывает божественную любовь в сердце. Очень нежный и мощный. Камень для глубокого исцеления сердца.', 'розовый', 'tourmaline_pink', 'divine_love, compassion, healing', 190, '8mm, 10mm', 'Редкий и дорогой, для преданных любви'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Шерл (чёрный турмалин сырой)', '💎', 'deep_protection, detox, grounding', '🔴', 'Мощная защита', 'Сырой чёрный турмалин - наиболее мощный вариант. Детоксирует энергию, глубоко защищает. Для опытных работников.', 'чёрный матовый', 'tourmaline_black_schorl', 'deep_protection, detox, grounding', 170, '10mm', 'Сырой, очень мощный, требует уважения'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Натуральный цитрин', '💎', 'money, abundance, joy', '🟡', 'Редкий натуральный цитрин', 'Редкий натуральный цитрин (не нагревается). Один из самых мощных для денег и радости. Ценный камень для истинной работы.', 'жёлтый натуральный', 'citrine_natural', 'money, abundance, joy', 220, '8mm, 10mm', 'Редкий и дорогой, настоящий цитрин'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Многоцветный турмалин', '💎', 'harmony, balance, wholeness', '🌈', 'Камень гармонии всех энергий', 'Редкий турмалин с несколькими цветами в одном кристалле. Гармонизирует все чакры сразу. Камень целостности и интеграции.', 'разноцветный', 'tourmaline_multicolor', 'harmony, balance, wholeness', 250, '10mm', 'Очень редкий, для продвинутых практиков'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Гранат', '💎', 'vitality, passion, grounding', '🔴, 🟠', 'Камень жизненной силы', 'Гранат пробуждает сексуальность и жизненную энергию. Камень страсти и земной силы. Помогает заземляться в тело.', 'красный-коричневый', 'garnet', 'vitality, passion, grounding', 145, '6mm, 8mm, 10mm', 'Драгоценный, помогает с либидо и энергией'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Ляпис-лазурь', '💎', 'wisdom, truth, inner_sight', '💜, 🔵', 'Камень небесной мудрости', 'Ляпис-лазурь - камень королей и мудрецов. Открывает третий глаз, связывает с высшей мудростью. Один из самых ценных камней.', 'глубокий синий с золотом', 'lapis_lazuli', 'wisdom, truth, inner_sight', 210, '8mm, 10mm', 'Очень дорогой, содержит золотой пирит'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Апатит синий', '💎', 'psychic_ability, clarity, communication', '🔵, 💜', 'Камень психических способностей', 'Синий апатит развивает психические способности, ясновидение, яснослышание. Помогает в медитации и внутреннем видении.', 'синий', 'apatite_blue', 'psychic_ability, clarity, communication', 125, '8mm, 10mm', 'Редкий, мощен для психического развития'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Кунцит сиреневый', '💎', 'divine_love, angels, spirituality', '💚, ⚪', 'Камень ангельской любви', 'Редкий сиреневый кунцит помогает связаться с ангельским царством. Очень высокая вибрация. Камень для духовных практик.', 'сиреневый-фиолетовый', 'kunzite_lilac', 'divine_love, angels, spirituality', 240, '8mm, 10mm', 'Хрупкий, редкий, для опытных практиков'))
        c.execute("INSERT OR IGNORE INTO knowledge (stone_name, emoji, properties, chakra, short_desc, full_desc, color, stone_id, tasks, price_per_bead, forms, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ('Арбузный турмалин', '💎', 'love_balance, yin_yang, integration', '💚', 'Камень баланса любви', 'Редкий турмалин с розовым центром и зелёной оболочкой - символ инь и ян. Баланс мужского и женского. Редкий и мощный камень.', 'розовый центр, зелёная оболочка', 'watermelon_tourmaline', 'love_balance, yin_yang, integration', 260, '10mm', 'Очень редкий, символ целостности'))
        conn.commit()
    except Exception as _e:
        logger.warning(f"stones import: {_e}")

    # Стандартные категории (OR IGNORE — не дублируются при перезапуске)
    try:
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🏋️ Практики', '🏋️', 'Физические упражнения'))
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎵 Музыка 432Hz', '🎵', 'Исцеляющая музыка'))
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎁 Готовые браслеты', '🎁', 'Готовые изделия'))
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('✨ Индивидуальный подбор', '✨', 'Подбор под вас'))
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('💍 Браслеты на заказ', '💍', 'Индивидуальный заказ браслета'))
        conn.commit()
    except:
        pass
    
    try:
        c.execute("INSERT INTO admins VALUES (?)", (ADMIN_ID,))
        conn.commit()
    except:
        pass


    # ── НОВЫЕ ТАБЛИЦЫ v7 ──
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
                  discount_pct INT DEFAULT 0, discount_rub INT DEFAULT 0,
                  max_uses INT DEFAULT 0, used_count INT DEFAULT 0,
                  active INT DEFAULT 1, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promo_uses
                 (user_id INT, code TEXT, used_at TIMESTAMP,
                  PRIMARY KEY (user_id, code))''')
    c.execute('''CREATE TABLE IF NOT EXISTS wishlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                  item_id INT, added_at TIMESTAMP,
                  UNIQUE(user_id, item_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS consultations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                  date TEXT, time_slot TEXT, topic TEXT,
                  status TEXT DEFAULT 'pending', created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedule_slots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT,
                  time_slot TEXT, available INT DEFAULT 1,
                  UNIQUE(date, time_slot))''')
    c.execute('''CREATE TABLE IF NOT EXISTS faq
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT,
                  answer TEXT, sort_order INT DEFAULT 0, active INT DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS crm_notes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                  note TEXT, created_at TIMESTAMP, admin_id INT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS new_item_subscribers
                 (user_id INT PRIMARY KEY, subscribed_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cart_reminders
                 (user_id INT PRIMARY KEY, last_reminder TIMESTAMP,
                  reminded INT DEFAULT 0)''')
    # Миграции orders
    try: c.execute("ALTER TABLE orders ADD COLUMN promo_code TEXT")
    except: pass
    try: c.execute("ALTER TABLE orders ADD COLUMN discount_rub REAL DEFAULT 0")
    except: pass
    conn.commit()

    # ── Stars ──
    c.execute('''CREATE TABLE IF NOT EXISTS stars_orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, item_id INT,
                  item_name TEXT, stars_amount INT, charge_id TEXT UNIQUE,
                  status TEXT DEFAULT 'paid', created_at TIMESTAMP)''')
    try: c.execute("ALTER TABLE showcase_items ADD COLUMN stars_price INTEGER DEFAULT 0")
    except: pass
    conn.commit()
    
    # ── ДОБАВЛЯЕМ ПОЛЯ ДЛЯ БОНУСОВ В ТАБЛИЦУ ЗАКАЗОВ (БАГ #4) ──
    try:
        c.execute("ALTER TABLE orders ADD COLUMN bonus_used REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN bonus_payment REAL DEFAULT 0")
    except:
        pass
    conn.commit()
    
    # ── ТАБЛИЦА ДЛЯ ИСТОРИИ БОНУСОВ ──
    c.execute('''CREATE TABLE IF NOT EXISTS bonus_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT,
                  amount REAL, operation TEXT, order_id INT,
                  created_at TIMESTAMP)''')
    conn.commit()
    
    # ── ТАБЛИЦА ДЛЯ БЛОКИРОВКИ ЗАКАЗОВ (БАГ #3) ──
    c.execute('''CREATE TABLE IF NOT EXISTS order_locks
                 (order_id INT PRIMARY KEY, locked_until TIMESTAMP,
                  user_id INT, created_at TIMESTAMP)''')
    conn.commit()
    
    # ── ТАБЛИЦА ДЛЯ НАСТРОЕК КЭШБЭКА (НОВОЕ) ──
    c.execute('''CREATE TABLE IF NOT EXISTS cashback_settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, cashback_percent INT DEFAULT 5,
                  min_order_amount REAL DEFAULT 0, active INT DEFAULT 1,
                  updated_at TIMESTAMP)''')
    # Вставляем дефолтную настройку, если нет
    c.execute("SELECT COUNT(*) FROM cashback_settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO cashback_settings (cashback_percent, min_order_amount, active, updated_at) VALUES (5, 0, 1, ?)",
                  (datetime.now(),))
    conn.commit()

    conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ ФУНКЦИИ ДЛЯ КЭШБЭКА
# ═══════════════════════════════════════════════════════════════════════════

async def get_cashback_settings():
    """Получить настройки кэшбэка"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT cashback_percent, min_order_amount, active FROM cashback_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    if row:
        return {"percent": row[0], "min_amount": row[1], "active": row[2]}
    return {"percent": 5, "min_amount": 0, "active": True}

async def apply_cashback(user_id: int, order_id: int, order_amount: float):
    """Начислить кэшбэк за заказ"""
    settings = await get_cashback_settings()
    if not settings["active"]:
        return 0
    
    if order_amount < settings["min_amount"]:
        return 0
    
    cashback_amount = round(order_amount * settings["percent"] / 100, 2)
    if cashback_amount <= 0:
        return 0
    
    conn = get_db()
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
        
        conn.commit()
        return cashback_amount
    except Exception as e:
        logger.error(f"Cashback error: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

async def update_cashback_settings(percent: int, min_amount: float = 0, active: bool = True):
    """Обновить настройки кэшбэка"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''UPDATE cashback_settings 
                     SET cashback_percent = ?, min_order_amount = ?, active = ?, updated_at = ?
                     WHERE id = 1''',
                  (percent, min_amount, 1 if active else 0, datetime.now()))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Update cashback error: {e}")
        return False
    finally:
        conn.close()

# ═══════════════════════════════════════════════════════════════════════════
# СОСТОЯНИЯ (для админ-панели)
# ═══════════════════════════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    # Категории
    add_category = State()
    add_category_emoji = State()
    # Контент
    add_content = State()
    select_content_cat = State()
    add_content_title = State()
    add_content_desc = State()
    # Тренировки
    add_workout = State()
    # Музыка
    add_music = State()
    add_music_name = State()
    add_music_file = State()
    # Услуги
    add_service = State()
    # Браслеты
    add_bracelet_name = State()
    add_bracelet_desc = State()
    add_bracelet_price = State()
    add_bracelet_image = State()
    # Подкатегории
    add_subcat_name = State()
    add_subcat_emoji = State()
    edit_subcat_name = State()
    # Под-подкатегории
    add_subsubcat_name = State()
    add_subsubcat_emoji = State()
    edit_subsubcat_name = State()
    # Редактирование
    edit_cat_name = State()

class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()

class ReviewStates(StatesGroup):
    waiting_rating = State()
    waiting_review_text = State()

class BroadcastStates(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()

class StoryStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()

class ContactStates(StatesGroup):
    waiting_message = State()

class KnowledgeAdminStates(StatesGroup):
    stone_name = State()
    stone_emoji = State()
    stone_properties = State()
    stone_elements = State()
    stone_zodiac = State()
    stone_chakra = State()
    stone_photo = State()

class QuizStates(StatesGroup):
    q1 = State()

class OrderBraceletStates(StatesGroup):
    q1_purpose = State()    # Для чего браслет
    q2_stones = State()     # Камни
    q3_size = State()       # Размер запястья
    q4_notes = State()      # Доп пожелания
    photo1 = State()        # Фото спереди
    photo2 = State()        # Фото сзади

class WelcomeTextStates(StatesGroup):
    waiting_text = State()
    waiting_return_text = State()

class OrderStatusStates(StatesGroup):
    waiting_status = State()

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ СОСТОЯНИЯ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ (БАГ #4)
# ═══════════════════════════════════════════════════════════════════════════

class BonusPaymentStates(StatesGroup):
    waiting_bonus_amount = State()

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ СОСТОЯНИЯ ДЛЯ КЭШБЭКА
# ═══════════════════════════════════════════════════════════════════════════

class CashbackAdminStates(StatesGroup):
    waiting_percent = State()
    waiting_min_amount = State()

# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def get_referral_percent(n):
    if n >= 16: return 15
    elif n >= 6: return 10
    elif n >= 1: return 5
    return 0

def get_referral_status(n):
    if n >= 16: return "👑 Амбассадор"
    elif n >= 6: return "⭐ Партнёр"
    elif n >= 1: return "🌱 Реферал"
    return "Новичок"

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ ФУНКЦИИ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ (БАГ #4)
# ═══════════════════════════════════════════════════════════════════════════

async def get_user_bonus_balance(user_id: int) -> float:
    """Получить текущий бонусный баланс пользователя"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT balance FROM referral_balance WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0

async def apply_bonus_to_order(user_id: int, order_id: int, bonus_amount: float):
    """Списать бонусы с баланса и применить к заказу"""
    conn = get_db()
    c = conn.cursor()
    try:
        # Начинаем транзакцию
        conn.execute("BEGIN IMMEDIATE")
        
        # Проверяем текущий баланс
        c.execute('SELECT balance FROM referral_balance WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if not row or row[0] < bonus_amount - 0.01:  # небольшая погрешность
            conn.rollback()
            conn.close()
            return False
        
        # Обновляем баланс
        c.execute('UPDATE referral_balance SET balance = balance - ? WHERE user_id = ?', 
                  (bonus_amount, user_id))
        
        # Обновляем заказ (помечаем сколько списано бонусами)
        c.execute('UPDATE orders SET bonus_used = ?, bonus_payment = ? WHERE id = ?', 
                  (bonus_amount, bonus_amount, order_id))
        
        # Сохраняем в историю
        c.execute('''INSERT INTO bonus_history 
                     (user_id, amount, operation, order_id, created_at) 
                     VALUES (?, ?, 'spend', ?, ?)''',
                  (user_id, -bonus_amount, order_id, datetime.now()))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Bonus apply error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

async def add_bonus_history(user_id: int, amount: float, operation: str, order_id: int = 0):
    """Добавить запись в историю бонусов"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO bonus_history 
                     (user_id, amount, operation, order_id, created_at) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (user_id, amount, operation, order_id, datetime.now()))
        conn.commit()
    except Exception as e:
        logger.error(f"Bonus history error: {e}")
    finally:
        conn.close()

async def notify_admin_bonus_usage(user_id: int, order_id: int, bonus_amount: float, final_price: float):
    """Уведомить админа об использовании бонусов"""
    if not ADMIN_ID:
        return
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
        u = c.fetchone()
        conn.close()
        name = u[0] if u else str(user_id)
        uname = f"@{u[1]}" if u and u[1] else "нет"
        
        await bot.send_message(
            ADMIN_ID,
            f"💰 ИСПОЛЬЗОВАНИЕ БОНУСОВ\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: {user_id}\n"
            f"📦 Заказ #{order_id}\n"
            f"💎 Списано бонусов: {bonus_amount:.0f} руб\n"
            f"💳 Итог к оплате: {final_price:.0f} руб",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
            ])
        )
    except Exception as e:
        logger.error(f"notify_admin_bonus: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЕ ФУНКЦИИ ДЛЯ ЗАЩИТЫ ОТ ДВОЙНЫХ ЗАКАЗОВ (БАГ #3)
# ═══════════════════════════════════════════════════════════════════════════

async def acquire_order_lock(order_id: int, user_id: int, timeout_seconds: int = 5) -> bool:
    """Попытаться заблокировать заказ для обработки"""
    conn = get_db()
    c = conn.cursor()
    try:
        conn.execute("BEGIN IMMEDIATE")
        
        # Проверяем, не заблокирован ли заказ
        c.execute('''SELECT locked_until FROM order_locks 
                     WHERE order_id = ? AND locked_until > datetime("now")''', (order_id,))
        if c.fetchone():
            conn.rollback()
            conn.close()
            return False
        
        # Удаляем старые блокировки
        c.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
        
        # Создаём новую блокировку
        c.execute('''INSERT INTO order_locks (order_id, locked_until, user_id, created_at)
                     VALUES (?, datetime("now", ?), ?, ?)''',
                  (order_id, f'+{timeout_seconds} seconds', user_id, datetime.now()))
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Order lock error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

async def release_order_lock(order_id: int):
    """Снять блокировку с заказа"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Release lock error: {e}")
    finally:
        conn.close()

async def notify_admin_order(user_id, order_id, total, method):
    try:
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
        u = c.fetchone(); conn.close()
        name = u[0] if u else str(user_id)
        uname = f"@{u[1]}" if u and u[1] else "нет"
        await bot.send_message(ADMIN_ID, f"🛒 НОВЫЙ ЗАКАЗ #{order_id}\n\n👤 {name} ({uname})\n💰 {total:.0f} руб\n💳 {method}")
    except Exception as e: logger.error(f"notify_order: {e}")

async def notify_admin_diagnostic(user_id, notes, photo1_id, photo2_id):
    try:
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
        u = c.fetchone(); conn.close()
        name = u[0] if u else str(user_id)
        uname = f"@{u[1]}" if u and u[1] else "нет"
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        ])
        await bot.send_message(ADMIN_ID,
            f"🩺 НОВАЯ ДИАГНОСТИКА\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: {user_id}\n\n"
            f"📝 Заметки: {notes}",
            reply_markup=kb)
        if photo1_id: await bot.send_photo(ADMIN_ID, photo1_id, caption="📸 Фото 1")
        if photo2_id: await bot.send_photo(ADMIN_ID, photo2_id, caption="📸 Фото 2")
    except Exception as e: logger.error(f"notify_diag: {e}")

async def notify_admin_quiz(user_id: int, stone: str, qz_type: str):
    """Уведомить админа о прохождении теста"""
    if not ADMIN_ID: return
    try:
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
        u = c.fetchone(); conn.close()
        name = u[0] if u else str(user_id)
        uname = f"@{u[1]}" if u and u[1] else "нет"
        type_labels = {
            'f_lost': '👩 Женщина — ищет себя',
            'f_grow': '👩 Женщина — развивается',
            'm_down': '👨 Мужчина — всё навалилось',
            'm_up': '👨 Мужчина — рвётся вперёд',
        }
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        ])
        await bot.send_message(ADMIN_ID,
            f"🔮 ПРОШЁЛ ТЕСТ\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: {user_id}\n"
            f"📊 Тип: {type_labels.get(qz_type, qz_type)}\n"
            f"💎 Рекомендован: {stone}\n\n"
            f"⏳ Ещё не прошёл диагностику",
            reply_markup=kb)
    except Exception as e: logger.error(f"notify_quiz: {e}")

async def get_categories_keyboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}")] for cat in cats]
    buttons.append([types.InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")])
    buttons.append([types.InlineKeyboardButton(text="📖 ИСТОРИИ КЛИЕНТОВ", callback_data="show_stories")])
    buttons.append([types.InlineKeyboardButton(text="🤝 МОЯ РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="my_referral")])
    buttons.append([types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С МАСТЕРОМ", callback_data="contact_master")])
    buttons.append([types.InlineKeyboardButton(text="💎 ВИТРИНА БРАСЛЕТОВ", callback_data="showcase_bracelets")])
    buttons.append([types.InlineKeyboardButton(text="🔮 УЗНАТЬ СВОЙ КАМЕНЬ", callback_data="quiz_start")])
    buttons.append([types.InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ О КАМНЯХ", callback_data="knowledge_list")])
    buttons.append([types.InlineKeyboardButton(text="🔍 ФИЛЬТР ВИТРИНЫ", callback_data="filter_bracelets")])
    buttons.append([types.InlineKeyboardButton(text="📦 МОИ ЗАКАЗЫ", callback_data="my_orders")])
    buttons.append([types.InlineKeyboardButton(text="⭐ МОИ ПОКУПКИ (Stars)", callback_data="my_stars_orders")])
    buttons.append([types.InlineKeyboardButton(text="❤️ ИЗБРАННОЕ", callback_data="my_wishlist"),
                    types.InlineKeyboardButton(text="❓ FAQ", callback_data="faq")])
    buttons.append([types.InlineKeyboardButton(text="📅 ЗАПИСЬ НА КОНСУЛЬТАЦИЮ", callback_data="book_consult")])
    buttons.append([types.InlineKeyboardButton(text="🔔 НОВИНКИ", callback_data="subscribe_new"),
                    types.InlineKeyboardButton(text="🎟️ ПРОМОКОД", callback_data="enter_promo")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def admin_panel_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [types.InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="admin_showcase"),
         types.InlineKeyboardButton(text="🆕 Новинки→подписчикам", callback_data="admin_notify_new")],
        [types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics"),
         types.InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="admin_orders")],
        [types.InlineKeyboardButton(text="📊 СТАТИСТИКА+", callback_data="admin_stats_v2"),
         types.InlineKeyboardButton(text="📊 Базовая", callback_data="admin_stats")],
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
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - УПРАВЛЕНИЕ КЭШБЭКОМ (НОВОЕ)
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_cashback")
async def admin_cashback(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    settings = await get_cashback_settings()
    status = "✅ ВКЛЮЧЁН" if settings["active"] else "❌ ВЫКЛЮЧЕН"
    
    text = (
        f"💰 УПРАВЛЕНИЕ КЭШБЭКОМ\n\n"
        f"Текущие настройки:\n"
        f"• Процент кэшбэка: {settings['percent']}%\n"
        f"• Минимальная сумма заказа: {settings['min_amount']:.0f} руб\n"
        f"• Статус: {status}\n\n"
        f"Кэшбэк начисляется автоматически после подтверждения заказа.\n"
        f"Бонусы можно потратить на следующие покупки."
    )
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Изменить процент", callback_data="cashback_percent")],
        [types.InlineKeyboardButton(text="💰 Изменить мин. сумму", callback_data="cashback_min")],
        [types.InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data="cashback_toggle")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "cashback_percent")
async def cashback_percent_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    settings = await get_cashback_settings()
    await safe_edit(cb, f"💰 Введите новый процент кэшбэка (сейчас {settings['percent']}%):")
    await state.set_state(CashbackAdminStates.waiting_percent)
    await cb.answer()

@admin_router.message(CashbackAdminStates.waiting_percent)
async def cashback_percent_save(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        percent = int(msg.text.strip())
        if percent < 0 or percent > 100:
            await msg.answer("❌ Процент должен быть от 0 до 100")
            return
        
        settings = await get_cashback_settings()
        await update_cashback_settings(percent, settings["min_amount"], settings["active"])
        
        await msg.answer(f"✅ Процент кэшбэка изменён на {percent}%",
                        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                            [types.InlineKeyboardButton(text="← К КЭШБЭКУ", callback_data="admin_cashback")],
                        ]))
    except ValueError:
        await msg.answer("❌ Введите целое число")
    finally:
        await state.clear()

@admin_router.callback_query(F.data == "cashback_min")
async def cashback_min_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    settings = await get_cashback_settings()
    await safe_edit(cb, f"💰 Введите минимальную сумму заказа для начисления кэшбэка (сейчас {settings['min_amount']:.0f} руб):")
    await state.set_state(CashbackAdminStates.waiting_min_amount)
    await cb.answer()

@admin_router.message(CashbackAdminStates.waiting_min_amount)
async def cashback_min_save(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    
    try:
        min_amount = float(msg.text.strip().replace(',', '.'))
        if min_amount < 0:
            await msg.answer("❌ Сумма не может быть отрицательной")
            return
        
        settings = await get_cashback_settings()
        await update_cashback_settings(settings["percent"], min_amount, settings["active"])
        
        await msg.answer(f"✅ Минимальная сумма изменена на {min_amount:.0f} руб",
                        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                            [types.InlineKeyboardButton(text="← К КЭШБЭКУ", callback_data="admin_cashback")],
                        ]))
    except ValueError:
        await msg.answer("❌ Введите число")
    finally:
        await state.clear()

@admin_router.callback_query(F.data == "cashback_toggle")
async def cashback_toggle(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    settings = await get_cashback_settings()
    new_status = not settings["active"]
    await update_cashback_settings(settings["percent"], settings["min_amount"], new_status)
    
    status_text = "включён" if new_status else "выключен"
    await cb.answer(f"✅ Кэшбэк {status_text}", show_alert=True)
    await admin_cashback(cb)

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message(CommandStart())
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    user_id = msg.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT user_id, welcome_sent FROM users WHERE user_id = ?', (user_id,))
    existing = c.fetchone()
    is_new = existing is None
    ref_id = None
    if msg.text and len(msg.text.split()) > 1:
        try:
            ref_id = int(msg.text.split()[1].replace('ref', ''))
            if ref_id == user_id: ref_id = None
        except: ref_id = None
    if is_new:
        c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, created_at, welcome_sent, referred_by) VALUES (?, ?, ?, ?, ?, ?)',
                  (user_id, msg.from_user.username, msg.from_user.first_name, datetime.now(), False, ref_id))
        conn.commit()
        if ref_id:
            c.execute('SELECT user_id FROM users WHERE user_id = ?', (ref_id,))
            if c.fetchone():
                c.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)', (ref_id, user_id, datetime.now()))
                c.execute('INSERT INTO referral_balance (user_id, referral_count, balance, total_earned) VALUES (?, 1, 100, 100) ON CONFLICT(user_id) DO UPDATE SET referral_count = referral_count + 1, balance = balance + 100, total_earned = total_earned + 100', (ref_id,))
                conn.commit()
                try: await bot.send_message(ref_id, "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь! Вам начислено 100 бонусов!")
                except: pass
    else:
        c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, created_at) VALUES (?, ?, ?, ?)',
                  (user_id, msg.from_user.username, msg.from_user.first_name, datetime.now()))
        conn.commit()
    conn.close()
    if is_admin(user_id):
        await msg.answer("👋 АДМИНИСТРАТОР!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")],
            [types.InlineKeyboardButton(text="👥 МЕНЮ", callback_data="menu")],
        ]))
    else:
        kb = await get_categories_keyboard()
        if is_new:
            welcome_text = await get_setting('welcome_text', '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nВыберите раздел 👇')
            await msg.answer(welcome_text, reply_markup=kb)
            conn = get_db(); c = conn.cursor()
            c.execute('UPDATE users SET welcome_sent = TRUE WHERE user_id = ?', (user_id,))
            conn.commit(); conn.close()
        else:
            return_text = await get_setting('return_text', '👋 С возвращением! Выбери раздел:')
            await msg.answer(return_text, reply_markup=kb)

@main_router.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    await msg.answer("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())


@main_router.callback_query(F.data == "diag_start")
async def diag_start_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(cb, 
        "📸 ДИАГНОСТИКА\n\n"
        "Мастер подберёт камни лично для вас на основе фото.\n\n"
        "Нужно два фото:\n\n"
        "1️⃣ Фото СПЕРЕДИ во весь рост\n"
        "   • Глаза смотрят прямо в камеру\n"
        "   • Обязательно без очков\n\n"
        "2️⃣ Фото СЗАДИ во весь рост\n\n"
        "Загружайте первое фото 👇",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

@main_router.callback_query(F.data.startswith("dg_gender_"))
async def dg_gender(cb: types.CallbackQuery, state: FSMContext):
    gender = cb.data.split("_")[-1]
    await state.update_data(dg_gender=gender)
    if gender == "f":
        await safe_edit(cb, 
            "Шаг 2 из 4 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💔 Больно — что-то важное ушло или рассыпалось", callback_data="dg_type_f_lost")],
                [types.InlineKeyboardButton(text="🌱 Развиваюсь — ищу себя и свой путь", callback_data="dg_type_f_grow")],
            ])
        )
    else:
        await safe_edit(cb, 
            "Шаг 2 из 4 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🌑 Всё навалилось — не вывожу", callback_data="dg_type_m_down")],
                [types.InlineKeyboardButton(text="⚡ Рвусь вперёд — нужна сила", callback_data="dg_type_m_up")],
            ])
        )
    await cb.answer()

@main_router.callback_query(F.data == "dg_type_f_lost")
async def dg_f_lost_q1(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_type="f_lost")
    await safe_edit(cb, 
        "Шаг 3 из 4 — Что сейчас внутри?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="😔 Пусто — как будто что-то важное ушло вместе с ним", callback_data="dg_q1_empty")],
            [types.InlineKeyboardButton(text="😤 Злость и обида — на него, на себя, на всё", callback_data="dg_q1_anger")],
            [types.InlineKeyboardButton(text="😰 Страх — а вдруг так теперь всегда", callback_data="dg_q1_fear")],
            [types.InlineKeyboardButton(text="😶 Онемела — не чувствую ни боли ни радости", callback_data="dg_q1_numb")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "dg_type_f_grow")
async def dg_f_grow_q1(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_type="f_grow")
    await safe_edit(cb, 
        "Шаг 3 из 4 — Что сейчас важнее всего усилить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💫 Интуицию и ясность мышления", callback_data="dg_q1_intuition")],
            [types.InlineKeyboardButton(text="💰 Материальный поток и изобилие", callback_data="dg_q1_money")],
            [types.InlineKeyboardButton(text="❤️ Женскую энергию и притяжение", callback_data="dg_q1_feminine")],
            [types.InlineKeyboardButton(text="🛡 Защиту и чистоту пространства", callback_data="dg_q1_protect")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "dg_type_m_down")
async def dg_m_down_q1(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_type="m_down")
    await safe_edit(cb, 
        "Шаг 3 из 4 — Что сейчас происходит?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💸 Деньги не идут — работаю, а результата нет", callback_data="dg_q1_nomoney")],
            [types.InlineKeyboardButton(text="💔 Всё рассыпалось — отношения, планы, смыслы", callback_data="dg_q1_collapsed")],
            [types.InlineKeyboardButton(text="😶 Апатия — встаю и не понимаю зачем", callback_data="dg_q1_apathy")],
            [types.InlineKeyboardButton(text="🌑 Ощущение что жизнь идёт мимо меня", callback_data="dg_q1_passing")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "dg_type_m_up")
async def dg_m_up_q1(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_type="m_up")
    await safe_edit(cb, 
        "Шаг 3 из 4 — Что хотите усилить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💰 Денежный поток и деловую удачу", callback_data="dg_q1_cashflow")],
            [types.InlineKeyboardButton(text="🧠 Ясность ума и скорость решений", callback_data="dg_q1_clarity")],
            [types.InlineKeyboardButton(text="⚡ Физическую силу и выносливость", callback_data="dg_q1_strength")],
            [types.InlineKeyboardButton(text="🛡 Защиту от конкурентов и завистников", callback_data="dg_q1_shield")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("dg_q1_"))
async def dg_q1_answer(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_q1=cb.data)
    data = await state.get_data()
    dg_type = data.get("dg_type","")
    if dg_type == "f_lost":
        q,opts = "Шаг 4 из 4 — Как давно вам так?",[
            ("🗓 Недавно — ещё острая боль","dg_q2_recent"),
            ("📆 Несколько месяцев — вроде живу, но не живу","dg_q2_months"),
            ("🗃 Больше года — уже забыла какой была раньше","dg_q2_year"),
            ("❓ Давно — не помню себя лёгкой и счастливой","dg_q2_always"),
        ]
    elif dg_type == "f_grow":
        q,opts = "Шаг 4 из 4 — Что мешает идти быстрее?",[
            ("⚡ Нет энергии — быстро выгораю","dg_q2_energy"),
            ("🌀 Сомнения и внутренние блоки","dg_q2_blocks"),
            ("👁 Чужое влияние — люди тянут назад","dg_q2_people"),
            ("🌫 Что-то держит, не могу понять что","dg_q2_unknown"),
        ]
    elif dg_type == "m_down":
        q,opts = "Шаг 4 из 4 — Как давно это длится?",[
            ("🗓 Недавно — конкретный удар выбил из колеи","dg_q2_recent"),
            ("📆 Несколько месяцев — постепенно накапливалось","dg_q2_months"),
            ("🗃 Больше года — уже норма, но внутри пусто","dg_q2_year"),
            ("❓ Всегда так — никогда не было по-настоящему хорошо","dg_q2_always"),
        ]
    else:
        q,opts = "Шаг 4 из 4 — Что мешает расти быстрее?",[
            ("🌀 Внутренние сомнения и страх ошибки","dg_q2_doubt"),
            ("👥 Люди вокруг тянут или предают","dg_q2_people"),
            ("⚡ Энергия есть, но быстро выгораю","dg_q2_burnout"),
            ("🌫 Что-то невидимое тормозит — не пойму что","dg_q2_unknown"),
        ]
    await safe_edit(cb, q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t, callback_data=d)] for t,d in opts
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("dg_q2_"))
async def dg_q2_done(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_q2=cb.data)
    await safe_edit(cb, 
        "✅ Отлично! Картина складывается.\n\n"
        "Последний шаг — загрузите два фото.\n\n"
        "📸 Фото 1: ваши ладони\n"
        "📸 Фото 2: ваше лицо или любое фото которое хотите показать\n\n"
        "Мастер подберёт камни лично для вас. Ответ в течение 24 часов.\n\n"
        "Загружайте первое фото 👇"
    )
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

@admin_router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await safe_edit(cb, "⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())
    await cb.answer()

@main_router.callback_query(F.data == "menu")
async def menu_cb(cb: types.CallbackQuery):
    kb = await get_categories_keyboard()
    await safe_edit(cb, "Выбери раздел:", reply_markup=kb)
    await cb.answer()

@main_router.callback_query(F.data.startswith("cat_"))
async def show_category(cb: types.CallbackQuery, state: FSMContext):
    try:
        cat_id = int(cb.data.split("_")[1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    if not cat:
        conn.close(); await cb.answer("Категория не найдена", show_alert=True); return

    # Перехват: Браслеты на заказ
    if cat and '💍' in cat[0]:
        conn.close()
        await safe_edit(cb, 
            "💍 БРАСЛЕТЫ НА ЗАКАЗ\n\n"
            "Мастер создаст браслет специально для вас.\n\n"
            "Начнём? 👇",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Да, начать", callback_data="order_bracelet_start")],
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
            ])
        )
        await cb.answer(); return

    # Перехват: Музыка 432Hz — показываем треки из таблицы music
    if cat and '🎵' in cat[0]:
        c.execute('SELECT id, name, duration, audio_url FROM music ORDER BY created_at DESC')
        tracks = c.fetchall(); conn.close()
        if not tracks:
            await safe_edit(cb, 
                f"{cat[1]} {cat[0]}\n\nТреков пока нет.",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
            await cb.answer(); return
        text = f"{cat[1]} {cat[0]}\n\nВыбери трек:"
        buttons = [[types.InlineKeyboardButton(
            text=f"🎵 {t[1]}" + (f" ({t[2]//60}:{t[2]%60:02d})" if t[2] else ""),
            callback_data=f"play_track_{t[0]}")] for t in tracks]
        buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
        await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        await cb.answer(); return
    
    # СНАЧАЛА проверяю есть ли подкатегории для этой категории
    c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (cat_id,))
    subcats = c.fetchall()
    
    # ПОТОМ проверяю контент
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (cat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{cat[1]} {cat[0]}\n\n"
    buttons = []
    
    # ЛОГИКА: если есть подкатегории - показываю их. Если контента нет - показываю сообщение
    if subcats:
        # Есть подкатегории - показываю список подкатегорий
        for subcat in subcats:
            text += f"{subcat[2]} {subcat[1]}\n"
            buttons.append([types.InlineKeyboardButton(text=f"{subcat[2]} {subcat[1]}", callback_data=f"subcat_{subcat[0]}")])
    elif content:
        # Нет подкатегорий, но есть контент - показываю контент
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        # Нет ни подкатегорий ни контента
        text += "📭 Контента нет"
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# АДМИН — КАТЕГОРИИ (единый раздел)
# ═══════════════════════════════════════════════════════════════════════════

async def cat_admin_menu(target, cat_id: int = None):
    """Универсальный рендер: список категорий или содержимое одной категории."""
    conn = get_db(); c = conn.cursor()
    is_msg = isinstance(target, types.Message)

    if cat_id is None:
        # Список всех категорий
        c.execute("SELECT id, name, emoji FROM categories ORDER BY id")
        cats = c.fetchall(); conn.close()
        text = "📋 КАТЕГОРИИ\n\n✏️ — управление  🗑 — удалить"
        buttons = []
        for cid, name, emoji in cats:
            em = emoji or "📁"
            buttons.append([
                types.InlineKeyboardButton(text=f"{em} {name}", callback_data=f"cadm_open_{cid}"),
                types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_del_{cid}"),
            ])
        buttons.append([types.InlineKeyboardButton(text="➕ Новая категория", callback_data="cadm_new")])
        buttons.append([types.InlineKeyboardButton(text="← ADMIN", callback_data="admin_panel")])
        kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        if is_msg: await target.answer(text, reply_markup=kb)
        else: await target.message.edit_text(text, reply_markup=kb)
        return

    # Содержимое одной категории
    c.execute("SELECT name, emoji FROM categories WHERE id=?", (cat_id,))
    cat = c.fetchone()
    if not cat: conn.close(); return
    name, emoji = cat
    em = emoji or "📁"

    c.execute("SELECT id, name, emoji FROM subcategories WHERE parent_id=? ORDER BY id", (cat_id,))
    subcats = c.fetchall()
    c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (cat_id,))
    contents = c.fetchall()
    c.execute("SELECT id, name FROM music ORDER BY created_at DESC LIMIT 20")
    music_list = c.fetchall() if "🎵" in name else []
    conn.close()

    is_music = "🎵" in name
    text = f"{em} {name}\n"

    buttons = []
    # Подкатегории
    for sid, sname, semoji in subcats:
        sem = semoji or "📁"
        buttons.append([
            types.InlineKeyboardButton(text=f"  {sem} {sname}", callback_data=f"cadm_sub_{sid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_delsub_{sid}_{cat_id}"),
        ])
    # Контент
    for cid, title in contents:
        buttons.append([
            types.InlineKeyboardButton(text=f"  📝 {title}", callback_data=f"cadm_content_{cid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cid}_{cat_id}"),
        ])
    # Треки (для музыки)
    if is_music:
        for mid, mname in music_list:
            buttons.append([
                types.InlineKeyboardButton(text=f"  🎵 {mname}", callback_data=f"cadm_track_{mid}"),
                types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_deltrack_{mid}_{cat_id}"),
            ])

    # Действия
    buttons.append([types.InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_rename_{cat_id}")])
    if is_music:
        buttons.append([types.InlineKeyboardButton(text="➕ Добавить трек", callback_data=f"cadm_addtrack_{cat_id}")])
    else:
        buttons.append([
            types.InlineKeyboardButton(text="➕ Подпапку", callback_data=f"cadm_addsub_{cat_id}"),
            types.InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontent_{cat_id}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="← К КАТЕГОРИЯМ", callback_data="admin_categories")])
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    if is_msg: await target.answer(text, reply_markup=kb)
    else: await target.message.edit_text(text, reply_markup=kb)


async def subcat_admin_menu(target, sub_id: int, parent_cat_id: int):
    """Содержимое подкатегории."""
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, emoji FROM subcategories WHERE id=?", (sub_id,))
    sub = c.fetchone()
    if not sub: conn.close(); return
    name, emoji = sub
    em = emoji or "📁"

    c.execute("SELECT id, name, emoji FROM subsubcategories WHERE parent_id=? ORDER BY id", (sub_id,))
    subsubs = c.fetchall()
    c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (sub_id,))
    contents = c.fetchall()
    conn.close()

    text = f"{em} {name}\n"
    buttons = []
    for ssid, ssname, ssemoji in subsubs:
        ssem = ssemoji or "📄"
        buttons.append([
            types.InlineKeyboardButton(text=f"  {ssem} {ssname}", callback_data=f"cadm_ssub_{ssid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_delssub_{ssid}_{sub_id}_{parent_cat_id}"),
        ])
    for cid, title in contents:
        buttons.append([
            types.InlineKeyboardButton(text=f"  📝 {title}", callback_data=f"cadm_content_{cid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cid}_{sub_id}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_renamesub_{sub_id}_{parent_cat_id}")])
    buttons.append([
        types.InlineKeyboardButton(text="➕ Под-подпапку", callback_data=f"cadm_addssub_{sub_id}_{parent_cat_id}"),
        types.InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontentsub_{sub_id}_{parent_cat_id}"),
    ])
    buttons.append([types.InlineKeyboardButton(text="← К КАТЕГОРИИ", callback_data=f"cadm_open_{parent_cat_id}")])
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    is_msg = isinstance(target, types.Message)
    if is_msg: await target.answer(text, reply_markup=kb)
    else: await target.message.edit_text(text, reply_markup=kb)


async def ssub_admin_menu(target, ssub_id: int, sub_id: int, cat_id: int):
    """Содержимое под-подкатегории."""
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, emoji FROM subsubcategories WHERE id=?", (ssub_id,))
    ssub = c.fetchone()
    if not ssub: conn.close(); return
    name, emoji = ssub
    c.execute("SELECT id, title FROM content WHERE cat_id=? ORDER BY id", (ssub_id,))
    contents = c.fetchall(); conn.close()
    em = emoji or "📄"
    text = f"{em} {name}\n"
    buttons = []
    for cid, title in contents:
        buttons.append([
            types.InlineKeyboardButton(text=f"  📝 {title}", callback_data=f"cadm_content_{cid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"cadm_delcontent_{cid}_{ssub_id}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cadm_renamessub_{ssub_id}_{sub_id}_{cat_id}")])
    buttons.append([types.InlineKeyboardButton(text="➕ Контент", callback_data=f"cadm_addcontentssub_{ssub_id}_{sub_id}_{cat_id}")])
    buttons.append([types.InlineKeyboardButton(text="← К ПОДПАПКЕ", callback_data=f"cadm_sub_{sub_id}_{cat_id}")])
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    is_msg = isinstance(target, types.Message)
    if is_msg: await target.answer(text, reply_markup=kb)
    else: await target.message.edit_text(text, reply_markup=kb)


# ── Открыть управление категориями ──
@admin_router.callback_query(F.data == "admin_categories")
async def admin_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    await cat_admin_menu(cb)
    await cb.answer()

# ── Открыть категорию ──
@admin_router.callback_query(F.data.startswith("cadm_open_"))
async def cadm_open(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await cat_admin_menu(cb, cat_id)
    await cb.answer()

# ── Удалить категорию ──
@admin_router.callback_query(F.data.startswith("cadm_del_"))
async def cadm_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    cat = c.fetchone()
    if not cat: conn.close(); await cb.answer("Не найдено", show_alert=True); return
    c.execute("SELECT id FROM subcategories WHERE parent_id=?", (cat_id,))
    subs = c.fetchall()
    for (sid,) in subs:
        c.execute("DELETE FROM subsubcategories WHERE parent_id=?", (sid,))
        c.execute("DELETE FROM content WHERE cat_id=?", (sid,))
    c.execute("DELETE FROM subcategories WHERE parent_id=?", (cat_id,))
    c.execute("DELETE FROM content WHERE cat_id=?", (cat_id,))
    c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    conn.commit(); conn.close()
    await cb.answer(f"✅ Удалено: {cat[0]}", show_alert=True)
    await cat_admin_menu(cb)

# ── Новая категория ──
@admin_router.callback_query(F.data == "cadm_new")
async def cadm_new(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    await safe_edit(cb, "📁 Новая категория\n\nВведи название:")
    await state.set_state(AdminStates.add_category)
    await cb.answer()

@admin_router.message(AdminStates.add_category)
async def cadm_save_new(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    name = msg.text.strip()
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?,?,?)", (name, "📁", ""))
        conn.commit()
        await msg.answer(f"✅ Категория '{name}' создана!")
    except Exception as e:
        await msg.answer(f"❌ {e}")
    finally:
        conn.close()
    await state.clear()
    await cat_admin_menu(msg)

# ── Переименовать категорию ──
@admin_router.callback_query(F.data.startswith("cadm_rename_"))
async def cadm_rename(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(cadm_rename_cat=cat_id)
    await safe_edit(cb, "✏️ Введи новое название категории:")
    await state.set_state(AdminStates.edit_cat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_cat_name)
async def cadm_save_rename(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    cat_id = data.get("cadm_rename_cat")
    if not cat_id: await state.clear(); return
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE categories SET name=? WHERE id=?", (msg.text.strip(), cat_id))
    conn.commit(); conn.close()
    await msg.answer(f"✅ Переименовано!")
    await state.clear()
    await cat_admin_menu(msg, cat_id)

# ── Добавить подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_addsub_"))
async def cadm_addsub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(cadm_addsub_cat=cat_id)
    await safe_edit(cb, "📁 Новая подпапка\n\nВведи название:")
    await state.set_state(AdminStates.add_subcat_name)
    await cb.answer()

@admin_router.message(AdminStates.add_subcat_name)
async def cadm_save_subcat(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    cat_id = data.get("cadm_addsub_cat")
    name = msg.text.strip()
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO subcategories (parent_id, name, emoji, created_at) VALUES (?,?,?,?)",
                  (cat_id, name, "📁", __import__("datetime").datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Подпапка '{name}' создана!")
    except Exception as e:
        await msg.answer(f"❌ {e}")
    finally:
        conn.close()
    await state.clear()
    await cat_admin_menu(msg, cat_id)

# ── Открыть подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_sub_"))
async def cadm_sub(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    # cadm_sub_SUBID или cadm_sub_SUBID_CATID
    sub_id = int(parts[2])
    if len(parts) > 3:
        cat_id = int(parts[3])
    else:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT parent_id FROM subcategories WHERE id=?", (sub_id,))
        r = c.fetchone(); conn.close()
        cat_id = r[0] if r else 0
    await subcat_admin_menu(cb, sub_id, cat_id)
    await cb.answer()

# ── Удалить подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_delsub_"))
async def cadm_delsub(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    sub_id = int(parts[2]); cat_id = int(parts[3])
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name FROM subcategories WHERE id=?", (sub_id,))
    sub = c.fetchone()
    c.execute("DELETE FROM subsubcategories WHERE parent_id=?", (sub_id,))
    c.execute("DELETE FROM content WHERE cat_id=?", (sub_id,))
    c.execute("DELETE FROM subcategories WHERE id=?", (sub_id,))
    conn.commit(); conn.close()
    await cb.answer(f"✅ Удалено: {sub[0] if sub else ''}", show_alert=True)
    await cat_admin_menu(cb, cat_id)

# ── Переименовать подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_renamesub_"))
async def cadm_renamesub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    sub_id = int(parts[2]); cat_id = int(parts[3])
    await state.update_data(cadm_rename_sub=sub_id, cadm_rename_sub_cat=cat_id)
    await safe_edit(cb, "✏️ Введи новое название подпапки:")
    await state.set_state(AdminStates.edit_subcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subcat_name)
async def cadm_save_renamesub(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    sub_id = data.get("cadm_rename_sub"); cat_id = data.get("cadm_rename_sub_cat")
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE subcategories SET name=? WHERE id=?", (msg.text.strip(), sub_id))
    conn.commit(); conn.close()
    await msg.answer("✅ Переименовано!")
    await state.clear()
    await subcat_admin_menu(msg, sub_id, cat_id)

# ── Добавить под-подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_addssub_"))
async def cadm_addssub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    sub_id = int(parts[2]); cat_id = int(parts[3])
    await state.update_data(cadm_addssub_sub=sub_id, cadm_addssub_cat=cat_id)
    await safe_edit(cb, "📄 Новая под-подпапка\n\nВведи название:")
    await state.set_state(AdminStates.add_subsubcat_name)
    await cb.answer()

@admin_router.message(AdminStates.add_subsubcat_name)
async def cadm_save_ssub(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    sub_id = data.get("cadm_addssub_sub"); cat_id = data.get("cadm_addssub_cat")
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?,?,?,?)",
                  (sub_id, msg.text.strip(), "📄", __import__("datetime").datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Создано!")
    except Exception as e:
        await msg.answer(f"❌ {e}")
    finally:
        conn.close()
    await state.clear()
    await subcat_admin_menu(msg, sub_id, cat_id)

# ── Открыть под-подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_ssub_"))
async def cadm_ssub(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    ssub_id = int(parts[2])
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT parent_id FROM subsubcategories WHERE id=?", (ssub_id,))
    r = c.fetchone()
    sub_id = r[0] if r else 0
    c.execute("SELECT parent_id FROM subcategories WHERE id=?", (sub_id,))
    r2 = c.fetchone(); conn.close()
    cat_id = r2[0] if r2 else 0
    await ssub_admin_menu(cb, ssub_id, sub_id, cat_id)
    await cb.answer()

# ── Удалить под-подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_delssub_"))
async def cadm_delssub(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    ssub_id = int(parts[2]); sub_id = int(parts[3]); cat_id = int(parts[4])
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name FROM subsubcategories WHERE id=?", (ssub_id,))
    ss = c.fetchone()
    c.execute("DELETE FROM content WHERE cat_id=?", (ssub_id,))
    c.execute("DELETE FROM subsubcategories WHERE id=?", (ssub_id,))
    conn.commit(); conn.close()
    await cb.answer(f"✅ {ss[0] if ss else ''} удалено", show_alert=True)
    await subcat_admin_menu(cb, sub_id, cat_id)

# ── Переименовать под-подкатегорию ──
@admin_router.callback_query(F.data.startswith("cadm_renamessub_"))
async def cadm_renamessub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    ssub_id = int(parts[2]); sub_id = int(parts[3]); cat_id = int(parts[4])
    await state.update_data(cadm_r_ssub=ssub_id, cadm_r_sub=sub_id, cadm_r_cat=cat_id)
    await safe_edit(cb, "✏️ Введи новое название:")
    await state.set_state(AdminStates.edit_subsubcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subsubcat_name)
async def cadm_save_renamessub(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    ssub_id = data["cadm_r_ssub"]; sub_id = data["cadm_r_sub"]; cat_id = data["cadm_r_cat"]
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE subsubcategories SET name=? WHERE id=?", (msg.text.strip(), ssub_id))
    conn.commit(); conn.close()
    await msg.answer("✅ Переименовано!")
    await state.clear()
    await ssub_admin_menu(msg, ssub_id, sub_id, cat_id)

# ── Добавить контент (в любую папку) ──
@admin_router.callback_query(F.data.startswith("cadm_addcontent_"))
async def cadm_addcontent(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(cadm_content_cat=cat_id, cadm_content_level="cat")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.add_content_title)
    await cb.answer()

@admin_router.callback_query(F.data.startswith("cadm_addcontentsub_"))
async def cadm_addcontentsub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    sub_id = int(parts[2]); cat_id = int(parts[3])
    await state.update_data(cadm_content_cat=sub_id, cadm_content_parent=cat_id, cadm_content_level="sub")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.add_content_title)
    await cb.answer()

@admin_router.callback_query(F.data.startswith("cadm_addcontentssub_"))
async def cadm_addcontentssub(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    ssub_id = int(parts[2]); sub_id = int(parts[3]); cat_id = int(parts[4])
    await state.update_data(cadm_content_cat=ssub_id, cadm_content_parent=sub_id, cadm_content_grandparent=cat_id, cadm_content_level="ssub")
    await safe_edit(cb, "📝 Добавить контент\n\nВведи заголовок:")
    await state.set_state(AdminStates.add_content_title)
    await cb.answer()

@admin_router.message(AdminStates.add_content_title)
async def cadm_content_title(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.update_data(cadm_content_title=msg.text.strip())
    await msg.answer("Введи текст контента:")
    await state.set_state(AdminStates.add_content_desc)

@admin_router.message(AdminStates.add_content_desc)
async def cadm_content_desc(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    cat_id = data["cadm_content_cat"]
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO content (cat_id, title, desc, created_at) VALUES (?,?,?,?)",
                  (cat_id, data["cadm_content_title"], msg.text.strip(), __import__("datetime").datetime.now()))
        conn.commit()
        await msg.answer("✅ Контент добавлен!")
    except Exception as e:
        await msg.answer(f"❌ {e}")
    finally:
        conn.close()
    level = data.get("cadm_content_level", "cat")
    await state.clear()
    if level == "cat":
        await cat_admin_menu(msg, cat_id)
    elif level == "sub":
        await subcat_admin_menu(msg, cat_id, data.get("cadm_content_parent", 0))
    else:
        await ssub_admin_menu(msg, cat_id, data.get("cadm_content_parent", 0), data.get("cadm_content_grandparent", 0))

# ── Удалить контент ──
@admin_router.callback_query(F.data.startswith("cadm_delcontent_"))
async def cadm_delcontent(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    content_id = int(parts[2]); back_id = int(parts[3])
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM content WHERE id=?", (content_id,))
    # Определяем куда вернуться
    in_cat = c.execute("SELECT id FROM categories WHERE id=?", (back_id,)).fetchone()
    if not in_cat:
        r = c.execute("SELECT parent_id FROM subcategories WHERE id=?", (back_id,)).fetchone()
        parent_cat = r[0] if r else 0
    conn.commit(); conn.close()
    await cb.answer("✅ Удалено", show_alert=True)
    if in_cat:
        await cat_admin_menu(cb, back_id)
    else:
        await subcat_admin_menu(cb, back_id, parent_cat)

# ── Просмотр контента ──
@admin_router.callback_query(F.data.startswith("cadm_content_"))
async def cadm_view_content(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        content_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT title, desc, cat_id FROM content WHERE id=?", (content_id,))
    item = c.fetchone(); conn.close()
    if not item: await cb.answer("Не найдено", show_alert=True); return
    title, desc, cat_id = item
    await safe_edit(cb, 
        f"📝 {title}\n\n{desc}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cadm_delcontent_{content_id}_{cat_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data=f"cadm_open_{cat_id}")],
        ])
    )
    await cb.answer()

# ── Добавить трек (музыка) ──
@admin_router.callback_query(F.data.startswith("cadm_addtrack_"))
async def cadm_addtrack(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(cadm_track_cat=cat_id)
    await safe_edit(cb, "🎵 Новый трек\n\nВведи название трека:")
    await state.set_state(AdminStates.add_music_name)
    await cb.answer()

@admin_router.message(AdminStates.add_music_name)
async def cadm_music_name(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.update_data(cadm_music_name=msg.text.strip())
    await msg.answer("🎵 Теперь отправь аудиофайл (MP3, OGG, WAV):")
    await state.set_state(AdminStates.add_music_file)

@admin_router.message(AdminStates.add_music_file)
async def cadm_music_file(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    if not msg.audio and not msg.document:
        await msg.answer("❌ Отправь аудиофайл!"); return
    data = await state.get_data()
    file_id = msg.audio.file_id if msg.audio else msg.document.file_id
    duration = msg.audio.duration if msg.audio else 0
    name = data.get("cadm_music_name", "Трек")
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO music (name, desc, duration, audio_url, created_at) VALUES (?,?,?,?,?)",
                  (name, name, duration or 0, file_id, __import__("datetime").datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Трек '{name}' добавлен!")
    except Exception as e:
        await msg.answer(f"❌ {e}")
    finally:
        conn.close()
    cat_id = data.get("cadm_track_cat", 0)
    await state.clear()
    await cat_admin_menu(msg, cat_id)

# ── Удалить трек ──
@admin_router.callback_query(F.data.startswith("cadm_deltrack_"))
async def cadm_deltrack(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    track_id = int(parts[2]); cat_id = int(parts[3])
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM music WHERE id=?", (track_id,))
    conn.commit(); conn.close()
    await cb.answer("✅ Трек удалён", show_alert=True)
    await cat_admin_menu(cb, cat_id)

# ── Просмотр трека (для удаления) ──
@admin_router.callback_query(F.data.startswith("cadm_track_"))
async def cadm_view_track(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try:
        track_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, duration FROM music WHERE id=?", (track_id,))
    t = c.fetchone()
    if not t: conn.close(); await cb.answer("Не найдено", show_alert=True); return
    name, dur = t
    c.execute("SELECT id FROM categories WHERE name LIKE '%🎵%' OR name LIKE '%Музыка%'")
    r = c.fetchone()
    conn.close()
    cat_id = r[0] if r else 0
    dur_str = f"{dur//60}:{dur%60:02d}" if dur else "?"
    await safe_edit(cb, 
        f"🎵 {name}\n⏱ {dur_str}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑 Удалить трек", callback_data=f"cadm_deltrack_{track_id}_{cat_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data=f"cadm_open_{cat_id}")],
        ])
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - УСЛУГИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_services")
async def admin_services(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, price FROM services')
    services = c.fetchall()
    conn.close()
    
    text = "💼 УСЛУГИ:\n\n"
    if services:
        for s in services:
            text += f"• {s[0]} - {s[1]} руб\n"
    else:
        text += "Услуг нет"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_service")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_service")
async def add_service_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название услуги:")
    await state.set_state(AdminStates.add_service)
    await cb.answer()

@admin_router.message(AdminStates.add_service)
async def add_service_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO services (name, desc, price, created_at) VALUES (?, ?, ?, ?)",
                 (name, "Описание услуги", 1000, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Услуга '{name}' добавлена!")
        logger.info(f"Услуга '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ДИАГНОСТИКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_diagnostics")
async def admin_diagnostics(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM diagnostics WHERE sent = FALSE')
    count = c.fetchone()[0]
    conn.close()
    
    text = f"🩺 ДИАГНОСТИКА\n\nОжидающих проверки: {count}"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "edit_categories")
async def edit_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id, name, emoji FROM categories')
    cats = c.fetchall(); conn.close()
    text = "✏️ КАТЕГОРИИ\n✏️ — переименовать  🗑 — удалить\n\n"
    buttons = []
    for cat in cats:
        text += f"{cat[2]} {cat[1]}\n"
        buttons.append([
            types.InlineKeyboardButton(text=f"✏️ {cat[2]} {cat[1]}", callback_data=f"edit_cat_{cat[0]}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"delete_cat_{cat[0]}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="cadm_new")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("edit_cat_"))
async def edit_cat_name(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(edit_cat_id=cat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    conn.close()
    if not cat:
        await cb.answer("Категория не найдена", show_alert=True); return
    await safe_edit(cb, f"✏️ Текущее название: {cat[0]}\n\nНапиши новое название:")
    await state.set_state(AdminStates.edit_cat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_cat_name)
async def update_cat_name(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'edit_cat_id' in data:
        # Это редактирование
        cat_id = data['edit_cat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE categories SET name = ? WHERE id = ?', (msg.text, cat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Категория обновлена на: {msg.text}")
        await state.clear()
    else:
        # Это добавление новой (старая логика)
        await state.update_data(category_name=msg.text)
        await msg.answer("Введи ЭМОДЗИ (например: 🎵):")

# ═══════════════════════════════════════════════════════════════════════════
# ПОДКАТЕГОРИИ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "manage_subcategories")
async def manage_subcategories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    # Показываю ВСЕ категории для управления подкатегориями
    c.execute('SELECT id, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    if not cats:
        await safe_edit(cb, "📭 Категорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()
        return
    
    text = "📚 УПРАВЛЕНИЕ ПОДКАТЕГОРИЯМИ ВСЕХ КАТЕГОРИЙ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"{cat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"manage_subcat_{cat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subcat_"))
async def manage_subcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(subcat_parent_id=cat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (cat_id,))
    subcats = c.fetchall()
    conn.close()
    
    text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
    buttons = []
    
    if subcats:
        for subcat in subcats:
            text += f"{subcat[2]} {subcat[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {subcat[1]}", callback_data=f"edit_subcat_{subcat[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{subcat[0]}")
            ])
    else:
        text += "📭 Подкатегорий нет\n"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{cat_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
    ])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subcat_"))
async def add_subcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        cat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(add_subcat_parent_id=cat_id)
    
    await safe_edit(cb, "📝 Введи название подкатегории:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_bracelet_name)
async def handle_add_name(msg: types.Message, state: FSMContext):
    """Универсальный обработчик для названия подкатегории/под-подкатегории/браслета"""
    data = await state.get_data()
    
    # Проверяю что добавляется
    if 'add_subsubcat_parent_id' in data and data.get('step') == 'name':
        # Это добавление под-подкатегории - переход на эмодзи
        await state.update_data(subsubcat_name=msg.text, step='emoji')
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        # Остаемся в том же State
    elif 'add_subsubcat_parent_id' in data and data.get('step') == 'emoji':
        # Сохраняю под-подкатегорию
        parent_id = data['add_subsubcat_parent_id']
        name = data['subsubcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория добавлена: {emoji} {name}")
        await state.clear()
    elif 'add_subcat_parent_id' in data:
        # Это добавление подкатегории
        await state.update_data(subcat_name=msg.text)
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        await state.set_state(AdminStates.add_bracelet_desc)
    elif 'edit_subsubcat_id' in data:
        # Редактирование под-подкатегории
        subsubcat_id = data['edit_subsubcat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE subsubcategories SET name = ? WHERE id = ?', (msg.text, subsubcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория обновлена на: {msg.text}")
        await state.clear()
    elif 'edit_subcat_id' in data:
        # Редактирование подкатегории
        subcat_id = data['edit_subcat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE subcategories SET name = ? WHERE id = ?', (msg.text, subcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория обновлена на: {msg.text}")
        await state.clear()
    elif 'edit_cat_id' in data:
        # Редактирование категории
        cat_id = data['edit_cat_id']
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE categories SET name = ? WHERE id = ?', (msg.text, cat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Категория обновлена на: {msg.text}")
        await state.clear()
    else:
        # Это добавление браслета - переход на описание
        await state.update_data(bracelet_name=msg.text)
        await msg.answer("📄 Введи ОПИСАНИЕ:")
        await state.set_state(AdminStates.add_bracelet_desc)

@admin_router.message(AdminStates.add_subcat_emoji)
async def add_subcat_emoji(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'add_subcat_parent_id' in data:
        # Это добавление подкатегории
        parent_id = data['add_subcat_parent_id']
        name = data['subcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория добавлена: {emoji} {name}")
        await state.clear()
    else:
        # Старая логика
        await state.update_data(bracelet_desc=msg.text)
        await msg.answer("💵 Введи ЦЕНУ (число):")
        await state.set_state(AdminStates.add_bracelet_price)

@admin_router.callback_query(F.data.startswith("edit_subcat_"))
async def edit_subcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    conn.close()
    if not subcat:
        await cb.answer("Подкатегория не найдена", show_alert=True); return
    await state.update_data(edit_subcat_id=subcat_id)
    await safe_edit(cb, f"✏️ Текущее название: {subcat[0]}\n\nНапиши новое:")
    await state.set_state(AdminStates.edit_subcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subcat_name)
async def update_subcat_name(msg: types.Message, state: FSMContext):
    """Обновить название подкатегории"""
    data = await state.get_data()
    
    if 'edit_subcat_id' not in data:
        await msg.answer("❌ Ошибка. Попробуй ещё раз через меню.")
        await state.clear()
        return
    
    try:
        subcat_id = data['edit_subcat_id']
        new_name = msg.text
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаю parent_id для возврата в меню
        c.execute('SELECT parent_id FROM subcategories WHERE id = ?', (subcat_id,))
        result = c.fetchone()
        
        if not result:
            await msg.answer("❌ Подкатегория не найдена!")
            conn.close()
            await state.clear()
            return
        
        parent_id = result[0]
        
        # Обновляю название
        c.execute('UPDATE subcategories SET name = ? WHERE id = ?', (new_name, subcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Подкатегория переименована на: {new_name}")
        
        # Возвращаюсь в меню подкатегорий этой категории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM categories WHERE id = ?', (parent_id,))
        cat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (parent_id,))
        subcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОДКАТЕГОРИИ - {cat[0] if cat else 'Категория'}:\n\n"
        buttons = []
        
        if subcats:
            for sc in subcats:
                text += f"{sc[2]} {sc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {sc[1]}", callback_data=f"edit_subcat_{sc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{sc[0]}")
                ])
        else:
            text += "📭 Подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
        ])
        
        await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении подкатегории: {e}")
        await msg.answer(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        await state.clear()

@admin_router.callback_query(F.data.startswith("delete_subcat_"))
async def delete_subcat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name, parent_id FROM subcategories WHERE id = ?', (subcat_id,))
        subcat = c.fetchone()
        
        if not subcat:
            await cb.answer("❌ Подкатегория не найдена!", show_alert=True)
            conn.close()
            return
        
        subcat_name = subcat[0]
        parent_id = subcat[1]
        
        # Удаляю все под-подкатегории этой подкатегории
        c.execute('DELETE FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
        
        # Удаляю саму подкатегорию
        c.execute('DELETE FROM subcategories WHERE id = ?', (subcat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Подкатегория '{subcat_name}' удалена!", show_alert=True)
        
        # Возвращаюсь в меню управления подкатегориями этой категории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM categories WHERE id = ?', (parent_id,))
        cat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subcategories WHERE parent_id = ?', (parent_id,))
        subcats = c.fetchall()
        conn.close()
        cat_name = cat[0] if cat else "Категория"
        text = f"✏️ ПОДКАТЕГОРИИ - {cat_name}:\n\n"
        buttons = []
        
        if subcats:
            for sc in subcats:
                text += f"{sc[2]} {sc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {sc[1]}", callback_data=f"edit_subcat_{sc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subcat_{sc[0]}")
                ])
        else:
            text += "📭 Подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subcategories")],
        ])
        
        await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении подкатегории {subcat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# ПОД-ПОДКАТЕГОРИИ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "manage_subsubcategories")
async def manage_subsubcategories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name FROM subcategories')
    subcats = c.fetchall()
    conn.close()
    
    if not subcats:
        await safe_edit(cb, "📭 Подкатегорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
        await cb.answer()
        return
    
    text = "📚 УПРАВЛЕНИЕ ПОД-ПОДКАТЕГОРИЯМИ:\n\n"
    buttons = []
    
    for subcat in subcats:
        text += f"{subcat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {subcat[1]}", callback_data=f"manage_subsubcat_{subcat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subsubcat_"))
async def manage_subsubcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(subsubcat_parent_id=subcat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
    subsubcats = c.fetchall()
    conn.close()
    
    text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
    buttons = []
    
    if subsubcats:
        for subsubcat in subsubcats:
            text += f"{subsubcat[2]} {subsubcat[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {subsubcat[1]}", callback_data=f"edit_subsubcat_{subsubcat[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{subsubcat[0]}")
            ])
    else:
        text += "📭 Под-подкатегорий нет\n"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{subcat_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
    ])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subsubcat_"))
async def add_subsubcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(add_subsubcat_parent_id=subcat_id, step='name')
    
    await safe_edit(cb, "📝 Введи название под-подкатегории:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_subsubcat_name)
async def add_subsubcat_name(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if 'add_subsubcat_parent_id' in data and data.get('step') == 'name':
        # Это добавление под-подкатегории
        await state.update_data(subsubcat_name=msg.text, step='emoji')
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        # Остаемся в том же State
    elif 'add_subsubcat_parent_id' in data and data.get('step') == 'emoji':
        # Сохраняю под-подкатегорию
        parent_id = data['add_subsubcat_parent_id']
        name = data['subsubcat_name']
        emoji = msg.text
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO subsubcategories (parent_id, name, emoji, created_at) VALUES (?, ?, ?, ?)',
                  (parent_id, name, emoji, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория добавлена: {emoji} {name}")
        await state.clear()
    elif 'add_subcat_parent_id' in data:
        # Это добавление подкатегории (старая логика)
        await state.update_data(subcat_name=msg.text)
        await msg.answer("🎨 Введи ЭМОДЗИ (например: 🎁):")
        await state.set_state(AdminStates.add_bracelet_desc)
    else:
        # Другие операции
        await state.update_data(bracelet_name=msg.text)
        await msg.answer("📄 Введи ОПИСАНИЕ:")
        await state.set_state(AdminStates.add_bracelet_desc)

@admin_router.callback_query(F.data.startswith("edit_subsubcat_"))
async def edit_subsubcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subsubcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    conn.close()
    if not subsubcat:
        await cb.answer("Под-подкатегория не найдена", show_alert=True); return
    await state.update_data(edit_subsubcat_id=subsubcat_id)
    await safe_edit(cb, f"✏️ Текущее название: {subsubcat[0]}\n\nНапиши новое:")
    await state.set_state(AdminStates.edit_subsubcat_name)
    await cb.answer()

@admin_router.message(AdminStates.edit_subsubcat_name)
async def update_subsubcat_name(msg: types.Message, state: FSMContext):
    """Обновить название под-подкатегории"""
    data = await state.get_data()
    
    if 'edit_subsubcat_id' not in data:
        await msg.answer("❌ Ошибка. Попробуй ещё раз через меню.")
        await state.clear()
        return
    
    try:
        subsubcat_id = data['edit_subsubcat_id']
        new_name = msg.text
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаю parent_id для возврата в меню
        c.execute('SELECT parent_id FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        result = c.fetchone()
        
        if not result:
            await msg.answer("❌ Под-подкатегория не найдена!")
            conn.close()
            await state.clear()
            return
        
        parent_id = result[0]
        
        # Обновляю название
        c.execute('UPDATE subsubcategories SET name = ? WHERE id = ?', (new_name, subsubcat_id))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ Под-подкатегория переименована на: {new_name}")
        
        # Возвращаюсь в меню под-подкатегорий этой подкатегории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM subcategories WHERE id = ?', (parent_id,))
        subcat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (parent_id,))
        subsubcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0] if subcat else 'Категория'}:\n\n"
        buttons = []
        
        if subsubcats:
            for ssc in subsubcats:
                text += f"{ssc[2]} {ssc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {ssc[1]}", callback_data=f"edit_subsubcat_{ssc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{ssc[0]}")
                ])
        else:
            text += "📭 Под-подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
        ])
        
        await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении под-подкатегории: {e}")
        await msg.answer(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        await state.clear()

@admin_router.callback_query(F.data.startswith("delete_subsubcat_"))
async def delete_subsubcat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    try:
        subsubcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name, parent_id FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        subsubcat = c.fetchone()
        
        if not subsubcat:
            await cb.answer("❌ Под-подкатегория не найдена!", show_alert=True)
            conn.close()
            return
        
        subsubcat_name = subsubcat[0]
        parent_id = subsubcat[1]
        
        # Удаляю саму под-подкатегорию
        c.execute('DELETE FROM subsubcategories WHERE id = ?', (subsubcat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Под-подкатегория '{subsubcat_name}' удалена!", show_alert=True)
        
        # Возвращаюсь в меню управления под-подкатегориями этой подкатегории
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT name FROM subcategories WHERE id = ?', (parent_id,))
        subcat = c.fetchone()
        c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (parent_id,))
        subsubcats = c.fetchall()
        conn.close()
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0] if subcat else 'Категория'}:\n\n"
        buttons = []
        
        if subsubcats:
            for ssc in subsubcats:
                text += f"{ssc[2]} {ssc[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {ssc[1]}", callback_data=f"edit_subsubcat_{ssc[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_subsubcat_{ssc[0]}")
                ])
        else:
            text += "📭 Под-подкатегорий нет\n"
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data=f"add_subsubcat_{parent_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="manage_subsubcategories")],
        ])
        
        await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении под-подкатегории {subsubcat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# БРАСЛЕТЫ - УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_bracelets")
async def admin_bracelets(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM bracelets')
    count = c.fetchone()[0]
    conn.close()
    
    text = f"💎 БРАСЛЕТЫ\n\nВсего браслетов: {count}"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ БРАСЛЕТ", callback_data="add_bracelet")],
        [types.InlineKeyboardButton(text="📋 СПИСОК", callback_data="list_bracelets")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_bracelet")
async def add_bracelet_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    await safe_edit(cb, "💎 ДОБАВИТЬ БРАСЛЕТ\n\n📝 Введи НАЗВАНИЕ:")
    await state.set_state(AdminStates.add_bracelet_name)
    await cb.answer()

@admin_router.message(AdminStates.add_bracelet_desc)
async def add_bracelet_price(msg: types.Message, state: FSMContext):
    await state.update_data(bracelet_desc=msg.text)
    await msg.answer("💵 Введи ЦЕНУ (число):")
    await state.set_state(AdminStates.add_bracelet_price)

@admin_router.message(AdminStates.add_bracelet_price)
async def add_bracelet_image(msg: types.Message, state: FSMContext):
    try:
        price = float(msg.text)
        await state.update_data(bracelet_price=price)
        await msg.answer("🖼️ Загрузи ФОТО браслета:")
        await state.set_state(AdminStates.add_bracelet_image)
    except:
        await msg.answer("❌ Введи корректную цену (число):")

@admin_router.message(AdminStates.add_bracelet_image)
async def save_bracelet(msg: types.Message, state: FSMContext):
    if msg.photo:
        data = await state.get_data()
        photo_id = msg.photo[-1].file_id
        
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO bracelets (name, desc, price, image_url, created_at) VALUES (?, ?, ?, ?, ?)',
                  (data['bracelet_name'], data['bracelet_desc'], data['bracelet_price'], photo_id, datetime.now()))
        conn.commit()
        conn.close()
        
        await msg.answer(f"✅ БРАСЛЕТ ДОБАВЛЕН!\n\n💎 {data['bracelet_name']}\n📄 {data['bracelet_desc']}\n💵 {data['bracelet_price']}₽")
        await state.clear()
    else:
        await msg.answer("❌ Загрузи фото (не текст):")

@admin_router.callback_query(F.data == "list_bracelets")
async def list_bracelets(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, price FROM bracelets')
    bracelets = c.fetchall()
    conn.close()
    
    if not bracelets:
        await safe_edit(cb, "📭 Браслетов нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_bracelets")],
        ]))
    else:
        text = "💎 СПИСОК БРАСЛЕТОВ:\n\n"
        for b in bracelets:
            text += f"ID: {b[0]} | {b[1]} | {b[2]}₽\n"
        await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_bracelets")],
        ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА - МИНИ-ВОРОНКА
# ═══════════════════════════════════════════════════════════════════════════

@diag_router.message(DiagnosticStates.waiting_photo1)
async def diag_photo1(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo1=photo.file_id)
    await msg.answer("✅ Фото спереди получено!\n\nТеперь загрузите фото СЗАДИ во весь рост 👇")
    await state.set_state(DiagnosticStates.waiting_photo2)

@diag_router.message(DiagnosticStates.waiting_photo2)
async def diag_photo2(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo2=photo.file_id)
    await msg.answer("✅ Оба фото получены! Отлично!\n\nЕсть что-то важное о себе что хотите добавить? Напишите или отправьте 'пропустить':")
    await state.set_state(DiagnosticStates.waiting_notes)

@diag_router.message(DiagnosticStates.waiting_notes)
async def diag_notes(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = msg.from_user.id
    notes = msg.text if msg.text.lower() != 'пропустить' else "Нет заметок"
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO diagnostics (user_id, photo_count, notes, created_at, photo1_file_id, photo2_file_id) VALUES (?, ?, ?, ?, ?, ?)",
                 (user_id, 2, notes, datetime.now(), data.get("photo1"), data.get("photo2")))
        conn.commit()
        
        if ADMIN_ID and ADMIN_ID != 0:
            await notify_admin_diagnostic(user_id, notes, data.get('photo1'), data.get('photo2'))
        
        await msg.answer("✅ СПАСИБО!\n\nДиагностика отправлена! Результаты в течение 24 часов! 💚")
        logger.info(f"Диагностика от {user_id} сохранена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка диагностики: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# БРАСЛЕТЫ - КАТАЛОГ И КОРЗИНА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("subcat_"))
async def show_subcategory(cb: types.CallbackQuery):
    try:
        subcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    if not subcat:
        conn.close(); await cb.answer("Подкатегория не найдена", show_alert=True); return
    
    # Сначала проверяю есть ли под-подкатегории
    c.execute('SELECT id, name, emoji FROM subsubcategories WHERE parent_id = ?', (subcat_id,))
    subsubcats = c.fetchall()
    
    # Потом проверяю контент
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (subcat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{subcat[1]} {subcat[0]}\n\n"
    buttons = []
    
    # ЛОГИКА: если есть под-подкатегории - показываю их. Если контента нет - показываю сообщение
    if subsubcats:
        # Есть под-подкатегории - показываю список
        for subsubcat in subsubcats:
            text += f"{subsubcat[2]} {subsubcat[1]}\n"
            buttons.append([types.InlineKeyboardButton(text=f"{subsubcat[2]} {subsubcat[1]}", callback_data=f"subsubcat_{subsubcat[0]}")])
    elif content:
        # Нет под-подкатегорий, но есть контент - показываю контент
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        # Нет ни под-подкатегорий ни контента
        text += "📭 Контента нет"
    
    # Кнопка назад → в родительскую категорию
    conn_p = get_db(); c_p = conn_p.cursor()
    c_p.execute("SELECT parent_id FROM subcategories WHERE id=?", (subcat_id,))
    p = c_p.fetchone(); conn_p.close()
    back_cb = f"cat_{p[0]}" if p else "menu"
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data=back_cb)])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("subsubcat_"))
async def show_subsubcategory(cb: types.CallbackQuery):
    try:
        subsubcat_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    if not subsubcat:
        conn.close(); await cb.answer("Раздел не найден", show_alert=True); return
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (subsubcat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{subsubcat[1]} {subsubcat[0]}\n\n"
    
    if content:
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        text += "📭 Контента нет"
    
    # Кнопка назад — в родительскую подкатегорию
    conn_p = get_db(); c_p = conn_p.cursor()
    c_p.execute("SELECT parent_id FROM subsubcategories WHERE id=?", (subsubcat_id,))
    parent = c_p.fetchone(); conn_p.close()
    back_cb = f"subcat_{parent[0]}" if parent else "menu"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data=back_cb)],
    ]))
    await cb.answer()

async def show_subcat_bracelets(cb: types.CallbackQuery):
    # Это устаревшая функция - заменена на show_subcategory
    await show_subcategory(cb)

@main_router.callback_query(F.data.startswith("bracelets_cat"))
async def show_bracelets(cb: types.CallbackQuery):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, desc, price, image_url FROM bracelets')
    bracelets = c.fetchall()
    conn.close()
    
    if not bracelets:
        await safe_edit(cb, "📭 Браслетов нет в наличии", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        await cb.answer()
        return
    
    # Показываю список браслетов
    text = "💎 БРАСЛЕТЫ:\n\n"
    buttons = []
    
    for b in bracelets:
        text += f"ID: {b[0]} | {b[1]} | {b[3]}₽\n"
        buttons.append([types.InlineKeyboardButton(text=f"💎 {b[1]} ({b[3]}₽)", callback_data=f"view_bracelet_{b[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("view_bracelet_"))
async def view_bracelet(cb: types.CallbackQuery):
    try:
        bracelet_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, desc, price, image_url FROM bracelets WHERE id = ?', (bracelet_id,))
    b = c.fetchone()
    conn.close()
    
    if not b:
        await cb.answer("❌ Браслет не найден", show_alert=True)
        return
    
    await cb.message.answer_photo(
        photo=b[4],
        caption=f"💎 {b[1]}\n\n📄 {b[2]}\n\n💵 Цена: {b[3]}₽",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛒 В КОРЗИНУ", callback_data=f"add_to_cart_{b[0]}")],
            [types.InlineKeyboardButton(text="⭐ ОТЗЫВЫ", callback_data=f"reviews_{b[0]}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="bracelets_cat")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(cb: types.CallbackQuery):
    try:
        bracelet_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    
    # Проверяю есть ли уже в корзине
    c.execute('SELECT id, quantity FROM cart WHERE user_id = ? AND bracelet_id = ?', (user_id, bracelet_id))
    existing = c.fetchone()
    
    if existing:
        c.execute('UPDATE cart SET quantity = quantity + 1 WHERE id = ?', (existing[0],))
    else:
        c.execute('INSERT INTO cart (user_id, bracelet_id, quantity, added_at) VALUES (?, ?, ?, ?)',
                  (user_id, bracelet_id, 1, datetime.now()))
    
    conn.commit()
    conn.close()
    
    await cb.answer("✅ Браслет добавлен в корзину!", show_alert=True)

@main_router.callback_query(F.data == "view_cart")
async def view_cart(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    if not rows:
        conn.close()
        await safe_edit(cb, "🛒 Корзина пуста", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💎 Перейти в витрину", callback_data="showcase_bracelets")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        await cb.answer(); return

    total = 0.0
    text = "🛒 КОРЗИНА:\n\n"
    buttons = []
    for cart_id, bracelet_id, qty in rows:
        if bracelet_id >= 100000:
            # Товар из витрины
            real_id = bracelet_id - 100000
            c.execute("SELECT name, price FROM showcase_items WHERE id=?", (real_id,))
            row = c.fetchone()
            name = row[0] if row else f"Товар #{real_id}"
            price = (row[1] or 0.0) if row else 0.0
            icon = "💎"
        else:
            # Старый браслет
            c.execute("SELECT name, price FROM bracelets WHERE id=?", (bracelet_id,))
            row = c.fetchone()
            name = row[0] if row else f"Браслет #{bracelet_id}"
            price = (row[1] or 0.0) if row else 0.0
            icon = "📿"
        line_total = price * qty
        total += line_total
        price_str = f"{price:.0f}₽" if price else "цена уточняется"
        text += f"{icon} {name}\n{qty} шт. × {price_str} = {line_total:.0f}₽\n\n"
        buttons.append([types.InlineKeyboardButton(
            text=f"❌ {name[:25]}", callback_data=f"remove_cart_{cart_id}")])
    conn.close()
    
    # Получаем текущий баланс бонусов
    bonus_balance = await get_user_bonus_balance(user_id)
    bonus_line = f"\n💰 Доступно бонусов: {bonus_balance:.0f}₽" if bonus_balance > 0 else ""
    
    text += f"\n💰 ИТОГО: {total:.0f}₽{bonus_line}"
    
    payment_buttons = []
    if bonus_balance > 0 and total > 0:
        payment_buttons.append([types.InlineKeyboardButton(text=f"💎 Оплатить бонусами (до {min(bonus_balance, total):.0f}₽)", callback_data="pay_bonus")])
    payment_buttons.extend([
        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
    ])
    
    buttons.extend(payment_buttons)
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# НОВЫЙ МЕТОД ОПЛАТЫ - БОНУСАМИ (БАГ #4)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "pay_bonus")
async def pay_bonus_start(cb: types.CallbackQuery, state: FSMContext):
    """Начало оплаты бонусами"""
    user_id = cb.from_user.id
    
    # Получаем стоимость корзины
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
    cart_rows = c.fetchall()
    
    if not cart_rows:
        conn.close()
        await cb.answer("Корзина пуста", show_alert=True)
        return
    
    total = 0.0
    for bracelet_id, qty in cart_rows:
        if bracelet_id >= 100000:
            c.execute("SELECT price FROM showcase_items WHERE id=?", (bracelet_id - 100000,))
        else:
            c.execute("SELECT price FROM bracelets WHERE id=?", (bracelet_id,))
        prow = c.fetchone()
        total += (prow[0] or 0.0) * qty if prow else 0.0
    
    # Получаем баланс бонусов
    bonus_balance = await get_user_bonus_balance(user_id)
    conn.close()
    
    max_bonus = min(bonus_balance, total)
    
    if max_bonus <= 0:
        await cb.answer("Недостаточно бонусов для оплаты", show_alert=True)
        return
    
    # Сохраняем данные в state
    await state.update_data(bonus_total=total, bonus_max=max_bonus, bonus_balance=bonus_balance)
    
    await safe_edit(
        cb,
        f"💎 ОПЛАТА БОНУСАМИ\n\n"
        f"💰 Сумма заказа: {total:.0f}₽\n"
        f"💎 Ваш бонусный баланс: {bonus_balance:.0f}₽\n\n"
        f"Введите сумму в рублях, которую хотите списать бонусами\n"
        f"(от 1 до {max_bonus:.0f}):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"Списать всё ({max_bonus:.0f}₽)", callback_data="bonus_all")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await state.set_state(BonusPaymentStates.waiting_bonus_amount)
    await cb.answer()

@main_router.callback_query(F.data == "bonus_all")
async def bonus_all(cb: types.CallbackQuery, state: FSMContext):
    """Списать все доступные бонусы"""
    data = await state.get_data()
    max_bonus = data.get('bonus_max', 0)
    total = data.get('bonus_total', 0)
    
    if max_bonus <= 0:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    bonus_amount = max_bonus
    
    # Применяем бонусы
    await process_bonus_payment(cb.message, cb.from_user.id, bonus_amount, total, state, is_cb=True)
    await cb.answer()

@main_router.message(BonusPaymentStates.waiting_bonus_amount)
async def bonus_amount_input(msg: types.Message, state: FSMContext):
    """Обработка введённой суммы бонусов"""
    try:
        bonus_amount = float(msg.text.strip().replace(',', '.'))
    except ValueError:
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
    
    await process_bonus_payment(msg, msg.from_user.id, bonus_amount, total, state, is_cb=False)

async def process_bonus_payment(target, user_id: int, bonus_amount: float, total: float, state: FSMContext, is_cb: bool):
    """Общая логика обработки оплаты бонусами"""
    
    # Итоговая сумма к доплате
    final_price = max(0, total - bonus_amount)
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Проверяем актуальный баланс (на всякий случай)
        c.execute('SELECT balance FROM referral_balance WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if not row or row[0] < bonus_amount - 0.01:
            if is_cb:
                await target.edit_text("❌ Недостаточно бонусов. Баланс изменился.")
            else:
                await target.answer("❌ Недостаточно бонусов. Баланс изменился.")
            await state.clear()
            conn.close()
            return
        
        # Создаём заказ
        c.execute(
            """INSERT INTO orders 
               (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user_id, final_price, 'pending', 'bonus', datetime.now(), None, 0, bonus_amount, bonus_amount)
        )
        order_id = c.lastrowid
        
        # Списание бонусов
        success = await apply_bonus_to_order(user_id, order_id, bonus_amount)
        
        if not success:
            conn.rollback()
            conn.close()
            if is_cb:
                await target.edit_text("❌ Ошибка при списании бонусов")
            else:
                await target.answer("❌ Ошибка при списании бонусов")
            await state.clear()
            return
        
        # Очищаем корзину
        c.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
        
        conn.commit()
        
        # Уведомления
        await notify_admin_bonus_usage(user_id, order_id, bonus_amount, final_price)
        
        # Ответ пользователю
        if final_price > 0:
            text = (
                f"✅ БОНУСЫ ПРИМЕНЕНЫ!\n\n"
                f"💎 Списано бонусов: {bonus_amount:.0f}₽\n"
                f"💰 Осталось к оплате: {final_price:.0f}₽\n\n"
                f"Выберите способ оплаты оставшейся суммы:"
            )
            if is_cb:
                await target.edit_text(
                    text,
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
                        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
                        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
                    ])
                )
            else:
                await target.answer(
                    text,
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
                        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
                        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
                    ])
                )
        else:
            # Полная оплата бонусами
            c.execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
            conn.commit()
            
            if is_cb:
                await target.edit_text(
                    f"✅ ЗАКАЗ #{order_id} ПОЛНОСТЬЮ ОПЛАЧЕН БОНУСАМИ!\n\n"
                    f"💎 Списано бонусов: {bonus_amount:.0f}₽\n\n"
                    f"Мастер получил уведомление и скоро свяжется с вами.",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
                    ])
                )
            else:
                await target.answer(
                    f"✅ ЗАКАЗ #{order_id} ПОЛНОСТЬЮ ОПЛАЧЕН БОНУСАМИ!\n\n"
                    f"💎 Списано бонусов: {bonus_amount:.0f}₽\n\n"
                    f"Мастер получил уведомление и скоро свяжется с вами.",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
                    ])
                )
        
    except Exception as e:
        logger.error(f"Bonus payment error: {e}")
        conn.rollback()
        if is_cb:
            await target.edit_text("❌ Ошибка при обработке платежа")
        else:
            await target.answer("❌ Ошибка при обработке платежа")
    finally:
        conn.close()
        await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ОСТАЛЬНЫЕ МЕТОДЫ ОПЛАТЫ (МОДИФИЦИРОВАНЫ ДЛЯ РАБОТЫ С БОНУСАМИ)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("remove_cart_"))
async def remove_from_cart(cb: types.CallbackQuery):
    try:
        cart_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM cart WHERE id = ?', (cart_id,))
    conn.commit()
    conn.close()
    
    await cb.answer("✅ Удалено из корзины!", show_alert=True)
    # Переказываю корзину
    await view_cart(cb)

@main_router.callback_query(F.data == "checkout")
async def checkout(cb: types.CallbackQuery, state: FSMContext):
    # Получаем баланс бонусов для отображения
    bonus_balance = await get_user_bonus_balance(cb.from_user.id)
    bonus_line = f"\n💎 У вас {bonus_balance:.0f} бонусов - можно оплатить!" if bonus_balance > 0 else ""
    
    await safe_edit(cb, 
        f"💳 СПОСОБ ОПЛАТЫ:{bonus_line}\n\n"
        "1. 💰 Яндекс.Касса\n"
        "2. ₿ Криптовалюта\n"
        "3. 💎 Бонусы (если есть)", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
            [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
        ] + ([
            [types.InlineKeyboardButton(text="💎 ОПЛАТИТЬ БОНУСАМИ", callback_data="pay_bonus")]
        ] if bonus_balance > 0 else []) + [
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "pay_yandex")
async def pay_yandex(cb: types.CallbackQuery, state: FSMContext):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    # Считаем total по ОБЕИМ таблицам: bracelets и showcase_items
    c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
    cart_rows = c.fetchall()
    total = 0.0
    promo_code = None; discount_rub = 0.0
    
    # Проверяем, не был ли уже применён бонус (через state)
    data = await state.get_data()
    bonus_used = data.get('bonus_used', 0.0)
    
    # Промокод из state
    try:
        promo_code = data.get('promo_code')
        promo_pct = data.get('promo_pct', 0)
        promo_rub = data.get('promo_rub', 0)
    except Exception:
        promo_code = None; promo_pct = 0; promo_rub = 0
        
    for bracelet_id, qty in cart_rows:
        if bracelet_id >= 100000:
            c.execute("SELECT price FROM showcase_items WHERE id=?", (bracelet_id - 100000,))
        else:
            c.execute("SELECT price FROM bracelets WHERE id=?", (bracelet_id,))
        prow = c.fetchone()
        total += (prow[0] or 0.0) * qty if prow else 0.0
    
    # Применяем промокод
    if promo_code:
        if promo_pct:
            discount_rub = round(total * promo_pct / 100, 2)
        elif promo_rub:
            discount_rub = min(float(promo_rub), total)
        total = max(0.0, total - discount_rub)
        # Фиксируем использование промокода
        c.execute("INSERT OR IGNORE INTO promo_uses (user_id, code, used_at) VALUES (?,?,?)",
                  (user_id, promo_code, datetime.now()))
        c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code=?", (promo_code,))
    
    # Применяем бонусы (если были)
    final_total = max(0.0, total - bonus_used)
    
    c.execute(
        """INSERT INTO orders 
           (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, final_total, 'pending', 'yandex', datetime.now(), promo_code, discount_rub, bonus_used, bonus_used)
    )
    order_id = c.lastrowid
    
    # Если были бонусы - списываем их
    if bonus_used > 0:
        await apply_bonus_to_order(user_id, order_id, bonus_used)
    
    conn.commit(); conn.close()
    await notify_admin_order(user_id, order_id, final_total, "Яндекс.Касса")
    
    disc_line = f"\n🎟️ Скидка по промокоду: -{discount_rub:.0f}₽" if discount_rub > 0 else ""
    bonus_line = f"\n💎 Оплачено бонусами: -{bonus_used:.0f}₽" if bonus_used > 0 else ""
    
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма к оплате: {final_total:.0f}₽{disc_line}{bonus_line}\n\n📝 РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ:\n"
    
    if YANDEX_KASSA_EMAIL != 'your-email@yandex.kassa.com':
        payment_text += f"Яндекс.Касса: {YANDEX_KASSA_EMAIL}\nShop ID: {YANDEX_KASSA_SHOP_ID}"
    else:
        payment_text += "⚠️ Реквизиты Яндекс.Кассы не настроены.\nОбновите YANDEX_KASSA_EMAIL в переменных окружения."
    
    # Очищаем бонус из state
    await state.update_data(bonus_used=0.0)
    
    await safe_edit(cb, payment_text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "pay_crypto")
async def pay_crypto(cb: types.CallbackQuery, state: FSMContext):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
    cart_rows = c.fetchall()
    total = 0.0
    promo_code = None; discount_rub = 0.0
    
    # Проверяем, не был ли уже применён бонус
    data = await state.get_data()
    bonus_used = data.get('bonus_used', 0.0)
    
    try:
        promo_code = data.get('promo_code')
        promo_pct = data.get('promo_pct', 0)
        promo_rub_val = data.get('promo_rub', 0)
    except Exception:
        promo_code = None; promo_pct = 0; promo_rub_val = 0
        
    for bracelet_id, qty in cart_rows:
        if bracelet_id >= 100000:
            c.execute("SELECT price FROM showcase_items WHERE id=?", (bracelet_id - 100000,))
        else:
            c.execute("SELECT price FROM bracelets WHERE id=?", (bracelet_id,))
        prow = c.fetchone()
        total += (prow[0] or 0.0) * qty if prow else 0.0
    
    if promo_code:
        if promo_pct:
            discount_rub = round(total * promo_pct / 100, 2)
        elif promo_rub_val:
            discount_rub = min(float(promo_rub_val), total)
        total = max(0.0, total - discount_rub)
        c.execute("INSERT OR IGNORE INTO promo_uses (user_id, code, used_at) VALUES (?,?,?)",
                  (user_id, promo_code, datetime.now()))
        c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code=?", (promo_code,))
    
    # Применяем бонусы
    final_total = max(0.0, total - bonus_used)
    
    c.execute(
        """INSERT INTO orders 
           (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub, bonus_used, bonus_payment) 
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, final_total, 'pending', 'crypto', datetime.now(), promo_code, discount_rub, bonus_used, bonus_used)
    )
    order_id = c.lastrowid
    
    # Если были бонусы - списываем их
    if bonus_used > 0:
        await apply_bonus_to_order(user_id, order_id, bonus_used)
    
    conn.commit(); conn.close()
    
    disc_line = f"\n🎟️ Скидка по промокоду: -{discount_rub:.0f}₽" if discount_rub > 0 else ""
    bonus_line = f"\n💎 Оплачено бонусами: -{bonus_used:.0f}₽" if bonus_used > 0 else ""
    
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма к оплате: {final_total:.0f}₽{disc_line}{bonus_line}\n\n"
    
    if CRYPTO_WALLET_ADDRESS != 'bc1qyour_bitcoin_address_here':
        payment_text += f"₿ {CRYPTO_WALLET_NETWORK} адрес:\n{CRYPTO_WALLET_ADDRESS}"
    else:
        payment_text += "⚠️ Адрес кошелька не настроен.\nОбновите CRYPTO_WALLET_ADDRESS в переменных окружения."
    
    # Очищаем бонус из state
    await state.update_data(bonus_used=0.0)
    
    await safe_edit(cb, payment_text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ИСПРАВЛЕННЫЙ МЕТОД ПОДТВЕРЖДЕНИЯ ЗАКАЗА (БАГ #3) + КЭШБЭК
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(cb: types.CallbackQuery, state: FSMContext):
    # Антиспам - если быстро нажимают, пропускаем
    if is_rate_limited(cb.from_user.id, "confirm", 2.0):
        await cb.answer("⏳ Заказ уже обрабатывается...", show_alert=False)
        return
    
    try:
        order_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True)
        return
    
    # Пытаемся заблокировать заказ
    if not await acquire_order_lock(order_id, cb.from_user.id):
        await cb.answer("⏳ Заказ уже обрабатывается другим запросом", show_alert=True)
        return
    
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Начинаем транзакцию с блокировкой строки
        conn.execute("BEGIN IMMEDIATE")
        
        # Проверяем статус заказа с блокировкой
        c.execute("SELECT status, user_id, total_price FROM orders WHERE id = ?", (order_id,))
        order = c.fetchone()
        
        if not order:
            conn.rollback()
            await cb.answer("Заказ не найден", show_alert=True)
            return
        
        if order[0] == 'confirmed':
            conn.rollback()
            await cb.answer("Заказ уже подтверждён", show_alert=True)
            return
        
        if order[0] == 'cancelled':
            conn.rollback()
            await cb.answer("Заказ отменён", show_alert=True)
            return
        
        # Обновляем статус
        c.execute("UPDATE orders SET status = ? WHERE id = ?", ('confirmed', order_id))
        
        # Проверяем, что обновилась ровно одна строка
        if c.rowcount == 0:
            conn.rollback()
            await cb.answer("Ошибка при подтверждении", show_alert=True)
            return
        
        # Очищаем корзину
        c.execute("DELETE FROM cart WHERE user_id = ?", (cb.from_user.id,))
        
        # Сбрасываем флаг напоминания корзины
        c.execute("DELETE FROM cart_reminders WHERE user_id = ?", (cb.from_user.id,))
        
        # Очищаем промокод из state
        try:
            await state.update_data(promo_code=None, promo_pct=0, promo_rub=0, bonus_used=0.0)
        except Exception:
            pass
        
        # Сохраняем информацию для кэшбэка
        user_id = order[1]
        order_amount = order[2]
        
        conn.commit()
        
        # Начисляем кэшбэк (после коммита заказа)
        cashback_amount = await apply_cashback(user_id, order_id, order_amount)
        cashback_text = f"\n💰 Вам начислено {cashback_amount:.0f} бонусов за покупку!" if cashback_amount > 0 else ""
        
        await safe_edit(cb, 
            f"✅ Заказ #{order_id} подтверждён!\n\n"
            f"Мастер получил уведомление и скоро свяжется с вами. Спасибо за покупку! 🪨"
            f"{cashback_text}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="⭐ ОСТАВИТЬ ОТЗЫВ", callback_data="leave_review")],
                [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")],
            ])
        )
        
        # Уведомляем админа о начислении кэшбэка, если он был
        if cashback_amount > 0 and ADMIN_ID:
            try:
                conn2 = get_db()
                c2 = conn2.cursor()
                c2.execute('SELECT first_name, username FROM users WHERE user_id = ?', (user_id,))
                u = c2.fetchone()
                conn2.close()
                name = u[0] if u else str(user_id)
                uname = f"@{u[1]}" if u and u[1] else "нет"
                
                await bot.send_message(
                    ADMIN_ID,
                    f"💰 НАЧИСЛЕН КЭШБЭК\n\n"
                    f"👤 {name} ({uname})\n"
                    f"🆔 ID: {user_id}\n"
                    f"📦 Заказ #{order_id}\n"
                    f"💎 Сумма кэшбэка: {cashback_amount:.0f} руб",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
                    ])
                )
            except Exception as e:
                logger.error(f"Cashback admin notify error: {e}")
        
    except Exception as e:
        logger.error(f"Confirm order error: {e}")
        if conn:
            conn.rollback()
        await cb.answer("❌ Ошибка при подтверждении заказа", show_alert=True)
    finally:
        if conn:
            conn.close()
        # Снимаем блокировку
        await release_order_lock(order_id)

# ═══════════════════════════════════════════════════════════════════════════
# ОСТАЛЬНЫЕ МЕТОДЫ (БЕЗ ИЗМЕНЕНИЙ)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "leave_review")
async def leave_review(cb: types.CallbackQuery, state: FSMContext):
    # Получаю bracelet_id из контекста или из callback_data
    await state.update_data(from_confirmation=True)
    await safe_edit(cb, "⭐ ОЦЕНКА:\n\n1 - очень плохо\n5 - отлично",
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐", callback_data="rate_1"),
         types.InlineKeyboardButton(text="⭐⭐", callback_data="rate_2"),
         types.InlineKeyboardButton(text="⭐⭐⭐", callback_data="rate_3")],
        [types.InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="rate_4"),
         types.InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="rate_5")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("rate_"))
async def save_rating(cb: types.CallbackQuery, state: FSMContext):
    try:
        rating = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(rating=rating)
    await safe_edit(cb, "📝 Напиши свой отзыв (текст):")
    await state.set_state(ReviewStates.waiting_review_text)
    await cb.answer()

@main_router.message(ReviewStates.waiting_review_text)
async def save_review_text(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = msg.from_user.id
    rating = data['rating']
    
    # Беру последний заказанный браслет или 1 по умолчанию
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT bracelet_id FROM cart WHERE user_id = ? LIMIT 1', (user_id,))
    result = c.fetchone()
    bracelet_id = result[0] if result else 1
    
    c.execute('INSERT INTO reviews (user_id, bracelet_id, rating, text, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, bracelet_id, rating, msg.text, datetime.now()))
    conn.commit()
    conn.close()
    
    await msg.answer("✅ Спасибо за отзыв!")
    await state.clear()

@main_router.callback_query(F.data.startswith("reviews_"))
async def show_reviews(cb: types.CallbackQuery):
    try:
        bracelet_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT rating, text FROM reviews WHERE bracelet_id = ? ORDER BY created_at DESC LIMIT 10', (bracelet_id,))
    reviews = c.fetchall()
    conn.close()
    
    if not reviews:
        text = "📭 Отзывов нет"
    else:
        text = "⭐ ОТЗЫВЫ:\n\n"
        for r in reviews:
            stars = "⭐" * r[0]
            text += f"{stars}\n{r[1]}\n\n"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# СВЯЗАТЬСЯ С МАСТЕРОМ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "contact_master")
async def contact_master(cb: types.CallbackQuery):
    await safe_edit(cb, 
        "📞 СВЯЗЬ С МАСТЕРОМ\n\nНапишите ваш вопрос — мастер ответит в ближайшее время:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💬 Написать сообщение", callback_data="send_to_master")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "send_to_master")
async def send_to_master_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✍️ Напишите ваш вопрос мастеру:")
    await state.set_state(ContactStates.waiting_message)
    await cb.answer()

@main_router.message(ContactStates.waiting_message)
async def send_to_master_finish(msg: types.Message, state: FSMContext):
    user = msg.from_user
    try:
        await bot.send_message(ADMIN_ID,
            f"📩 СООБЩЕНИЕ ОТ КЛИЕНТА\n\n👤 {user.first_name} (@{user.username or 'нет'})\nID: {user.id}\n\n💬 {msg.text}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="↩️ Ответить", url=f"tg://user?id={user.id}")],
            ])
        )
        await msg.answer("✅ Сообщение отправлено мастеру!")
    except Exception as e:
        logger.error(f"send_to_master: {e}")
        await msg.answer("✅ Сообщение отправлено!")
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# РЕФЕРАЛЬНАЯ СИСТЕМА (ДОПОЛНЕНА ИСТОРИЕЙ)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "my_referral")
async def my_referral(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT referral_count, balance, total_earned FROM referral_balance WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    
    # Получаем историю операций
    c.execute('SELECT amount, operation, order_id, created_at FROM bonus_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 5', (user_id,))
    history = c.fetchall()
    conn.close()
    
    ref_count = row[0] if row else 0
    balance = row[1] if row else 0
    total_earned = row[2] if row else 0
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    
    history_text = ""
    if history:
        history_text = "\n📊 Последние операции:\n"
        for amount, op, order_id, date in history:
            date_str = str(date)[:16]
            if op == 'earn':
                history_text += f"➕ +{abs(amount):.0f}₽ (реферал) {date_str}\n"
            elif op == 'spend':
                history_text += f"➖ -{abs(amount):.0f}₽ (заказ #{order_id}) {date_str}\n"
            elif op == 'cashback':
                history_text += f"💰 +{abs(amount):.0f}₽ (кэшбэк) {date_str}\n"
    
    await safe_edit(cb, 
        f"🤝 РЕФЕРАЛЬНАЯ ПРОГРАММА + КЭШБЭК\n\n"
        f"Ваш статус: {get_referral_status(ref_count)}\n"
        f"Приглашено друзей: {ref_count}\n\n"
        f"💰 Ваш бонусный баланс: {balance:.0f} руб\n"
        f"📈 Заработано всего: {total_earned:.0f} руб\n"
        f"{history_text}\n\n"
        f"🎁 За каждого приглашённого друга — 100 руб на баланс\n"
        f"💰 За каждую покупку — 5% кэшбэком\n"
        f"Баланс применяется как скидка при следующем заказе\n\n"
        f"🔗 Ваша ссылка:\n{ref_link}\n\n"
        f"📊 УРОВНИ БОНУСА:\n"
        f"1-5 друзей → +100 руб за каждого\n"
        f"6-15 друзей → +150 руб за каждого\n"
        f"16+ друзей → +200 руб + 👑 Амбассадор",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# СТАТИСТИКА АДМИН (ДОПОЛНЕНА БОНУСАМИ И КЭШБЭКОМ)
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')"); new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) >= DATE('now', '-7 days')"); new_week = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders"); total_orders = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"); orders_today = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(total_price),0) FROM orders WHERE status='confirmed'"); total_rev = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(total_price),0) FROM orders WHERE status='confirmed' AND DATE(created_at)=DATE('now')"); rev_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM diagnostics"); total_diag = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM referrals"); total_refs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bracelets"); total_br = c.fetchone()[0]
    
    # Статистика по бонусам
    c.execute("SELECT COUNT(*) FROM referral_balance WHERE balance > 0"); users_with_bonus = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(balance),0) FROM referral_balance"); total_bonus = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(bonus_used),0) FROM orders WHERE bonus_used > 0"); total_bonus_used = c.fetchone()[0]
    
    # Статистика по кэшбэку
    c.execute("SELECT COUNT(*) FROM bonus_history WHERE operation='cashback'"); cashback_count = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM bonus_history WHERE operation='cashback'"); total_cashback = c.fetchone()[0]
    
    settings = await get_cashback_settings()
    cashback_status = "включён" if settings["active"] else "выключен"
    
    conn.close()
    
    await safe_edit(cb, 
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Пользователей: {total_users} (+{new_today} сегодня, +{new_week} за неделю)\n"
        f"🛒 Заказов: {total_orders} ({orders_today} сегодня)\n"
        f"💰 Выручка: {total_rev:.0f} руб ({rev_today:.0f} сегодня)\n"
        f"🩺 Диагностик: {total_diag}\n"
        f"🤝 Рефералов: {total_refs}\n"
        f"💎 Браслетов: {total_br}\n\n"
        f"💰 БОНУСНАЯ СИСТЕМА:\n"
        f"👥 Пользователей с бонусами: {users_with_bonus}\n"
        f"💎 Накоплено бонусов: {total_bonus:.0f}₽\n"
        f"💸 Использовано бонусов: {total_bonus_used:.0f}₽\n\n"
        f"💰 КЭШБЭК (5%, {cashback_status}):\n"
        f"📊 Начислено раз: {cashback_count}\n"
        f"💎 Всего начислено: {total_cashback:.0f}₽",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "="*60)
    print("🚀 БОТ С ПОЛНЫМ ФУНКЦИОНАЛОМ ЗАПУСКАЕТСЯ")
    print("="*60 + "\n")
    
    dp.include_router(main_router)
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    
    # Railway использует polling (не webhook)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 ПОЛНЫЙ ФУНКЦИОНАЛ ВКЛЮЧЁН")
    print(f"📍 БАГ #3 (двойные заказы) - ИСПРАВЛЕН")
    print(f"📍 БАГ #4 (реферальная система) - ИСПРАВЛЕНА")
    print(f"📍 КЭШБЭК 5% - ДОБАВЛЕН (с управлением из админки)")
    print("\n" + "="*60 + "\n")
    
    # Middleware антиспам — встраивается на уровне диспетчера
    @dp.callback_query.middleware()
    async def rate_limit_middleware(handler, event, data):
        user_id = event.from_user.id
        if is_rate_limited(user_id, "cb", 0.7):
            await event.answer("⏳", show_alert=False)
            return
        return await handler(event, data)

    asyncio.create_task(send_quiz_reminders())
    asyncio.create_task(send_diag_followup())
    asyncio.create_task(send_cart_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")