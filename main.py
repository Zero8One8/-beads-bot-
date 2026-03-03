"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ ДЛЯ RAILWAY

✅ ДОБАВЛЯТЬ КАТЕГОРИИ - через админ-панель
✅ ДОБАВЛЯТЬ КОНТЕНТ - через админ-панель
✅ ДОБАВЛЯТЬ ТРЕНИРОВКИ - через админ-панель
✅ ДОБАВЛЯТЬ МУЗЫКУ - через админ-панель
✅ ДОБАВЛЯТЬ УСЛУГИ - через админ-панель
✅ ДИАГНОСТИКА (загрузка фото) - через бот

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

    conn.close()

init_db()

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
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])

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
                try: await bot.send_message(ref_id, "🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!")
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
    text += f"\n💰 ИТОГО: {total:.0f}₽"
    buttons.extend([
        [types.InlineKeyboardButton(text="💳 ОФОРМИТЬ ЗАКАЗ", callback_data="checkout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

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
    await safe_edit(cb, "💳 СПОСОБ ОПЛАТЫ:\n\n1. 💰 Яндекс.Касса\n2. ₿ Криптовалюта", 
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
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
    # Промокод из state
    try:
        data = await state.get_data()
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
    c.execute("INSERT INTO orders (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub) VALUES (?,?,?,?,?,?,?)",
              (user_id, total, 'pending', 'yandex', datetime.now(), promo_code, discount_rub))
    order_id = c.lastrowid
    conn.commit(); conn.close()
    await notify_admin_order(user_id, order_id, total, "Яндекс.Касса")
    disc_line = f"\n🎟️ Скидка по промокоду: -{discount_rub:.0f}₽" if discount_rub > 0 else ""
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total:.0f}₽{disc_line}\n\n📝 РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ:\n"
    
    if YANDEX_KASSA_EMAIL != 'your-email@yandex.kassa.com':
        payment_text += f"Яндекс.Касса: {YANDEX_KASSA_EMAIL}\nShop ID: {YANDEX_KASSA_SHOP_ID}"
    else:
        payment_text += "⚠️ Реквизиты Яндекс.Кассы не настроены.\nОбновите YANDEX_KASSA_EMAIL в переменных окружения."
    
    await safe_edit(cb, payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "pay_crypto")
async def pay_crypto(cb: types.CallbackQuery, state: FSMContext):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT bracelet_id, quantity FROM cart WHERE user_id=?", (user_id,))
    cart_rows = c.fetchall()
    total = 0.0
    promo_code = None; discount_rub = 0.0
    try:
        data = await state.get_data()
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
    c.execute("INSERT INTO orders (user_id, total_price, status, payment_method, created_at, promo_code, discount_rub) VALUES (?,?,?,?,?,?,?)",
              (user_id, total, 'pending', 'crypto', datetime.now(), promo_code, discount_rub))
    order_id = c.lastrowid
    conn.commit(); conn.close()
    
    disc_line = f"\n🎟️ Скидка по промокоду: -{discount_rub:.0f}₽" if discount_rub > 0 else ""
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total:.0f}₽{disc_line}\n\n"
    
    if CRYPTO_WALLET_ADDRESS != 'bc1qyour_bitcoin_address_here':
        payment_text += f"₿ {CRYPTO_WALLET_NETWORK} адрес:\n{CRYPTO_WALLET_ADDRESS}"
    else:
        payment_text += "⚠️ Адрес кошелька не настроен.\nОбновите CRYPTO_WALLET_ADDRESS в переменных окружения."
    
    await safe_edit(cb, payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(cb: types.CallbackQuery, state: FSMContext):
    try:
        order_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    # Проверяем что заказ не подтверждали уже (защита от двойного нажатия)
    c.execute("SELECT status FROM orders WHERE id=?", (order_id,))
    order = c.fetchone()
    if order and order[0] == 'confirmed':
        conn.close()
        await cb.answer("Заказ уже подтверждён", show_alert=True); return
    c.execute("UPDATE orders SET status=? WHERE id=?", ('confirmed', order_id))
    # Очищаем корзину
    c.execute("DELETE FROM cart WHERE user_id=?", (cb.from_user.id,))
    # Сбрасываем флаг напоминания корзины
    c.execute("DELETE FROM cart_reminders WHERE user_id=?", (cb.from_user.id,))
    # Очищаем промокод из state
    try:
        await state.update_data(promo_code=None, promo_pct=0, promo_rub=0)
    except Exception:
        pass
    conn.commit(); conn.close()
    await safe_edit(cb, f"✅ Заказ #{order_id} подтверждён!\n\nМастер получил уведомление и скоро свяжется с вами. Спасибо за покупку! 🪨",
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ ОСТАВИТЬ ОТЗЫВ", callback_data="leave_review")],
        [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")],
    ]))
    await cb.answer()

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
# ОСТАЛЬНОЕ
# ═══════════════════════════════════════════════════════════════════════════



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
# РЕФЕРАЛЬНАЯ СИСТЕМА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "my_referral")
async def my_referral(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT referral_count, balance, total_earned FROM referral_balance WHERE user_id = ?', (user_id,))
    row = c.fetchone(); conn.close()
    ref_count = row[0] if row else 0
    balance = row[1] if row else 0
    total_earned = row[2] if row else 0
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    await safe_edit(cb, 
        f"🤝 РЕФЕРАЛЬНАЯ ПРОГРАММА\n\n"
        f"Ваш статус: {get_referral_status(ref_count)}\n"
        f"Приглашено друзей: {ref_count}\n\n"
        f"💰 Ваш бонусный баланс: {balance:.0f} руб\n"
        f"📈 Заработано всего: {total_earned:.0f} руб\n\n"
        f"🎁 За каждого приглашённого друга — 100 руб на баланс\n"
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
# СТАТИСТИКА АДМИН
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
    conn.close()
    await safe_edit(cb, 
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Пользователей: {total_users} (+{new_today} сегодня, +{new_week} за неделю)\n"
        f"🛒 Заказов: {total_orders} ({orders_today} сегодня)\n"
        f"💰 Выручка: {total_rev:.0f} руб ({rev_today:.0f} сегодня)\n"
        f"🩺 Диагностик: {total_diag}\n"
        f"🤝 Рефералов: {total_refs}\n"
        f"💎 Браслетов: {total_br}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# РАССЫЛКА АДМИН
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    await safe_edit(cb, "📢 РАССЫЛКА\n\nНапишите текст сообщения:")
    await state.set_state(BroadcastStates.waiting_text)
    await cb.answer()

@admin_router.message(BroadcastStates.waiting_text)
async def admin_broadcast_confirm(msg: types.Message, state: FSMContext):
    await state.update_data(broadcast_text=msg.text)
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); count = c.fetchone()[0]; conn.close()
    await msg.answer(
        f"📢 Текст:\n{msg.text}\n\n👥 Получателей: {count}\n\nОтправить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")],
            [types.InlineKeyboardButton(text="❌ ОТМЕНА", callback_data="admin_panel")],
        ])
    )
    await state.set_state(BroadcastStates.waiting_confirm)

@admin_router.callback_query(F.data == "broadcast_confirm")
async def admin_broadcast_send(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM users"); users = c.fetchall(); conn.close()
    sent = 0; failed = 0
    await cb.message.edit_text(f"📤 Отправляю {len(users)} пользователям...")
    for user in users:
        try:
            await bot.send_message(user[0], f"📢 СООБЩЕНИЕ ОТ МАСТЕРА\n\n{text}")
            sent += 1; await asyncio.sleep(0.05)
        except: failed += 1
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO broadcasts (text, created_at, sent_count) VALUES (?, ?, ?)", (text, datetime.now(), sent))
    conn.commit(); conn.close()
    await cb.message.edit_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА\n\n📤 Отправлено: {sent}\n❌ Не доставлено: {failed}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ИСТОРИИ КЛИЕНТОВ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "show_stories")
async def show_stories_cb(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT s.text, s.photo_file_id, u.first_name FROM stories s JOIN users u ON s.user_id = u.user_id WHERE s.approved = TRUE ORDER BY s.created_at DESC LIMIT 5")
    stories = c.fetchall(); conn.close()
    if not stories:
        await cb.message.edit_text("📖 ИСТОРИИ КЛИЕНТОВ\n\nПока историй нет. Будьте первым!",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✍️ Поделиться историей", callback_data="add_story")],
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
            ]))
    else:
        await cb.message.edit_text("📖 ИСТОРИИ КЛИЕНТОВ", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        for story in stories:
            caption = f"👤 {story[2]}\n\n{story[0]}"
            try:
                if story[1]: await cb.message.answer_photo(photo=story[1], caption=caption)
                else: await cb.message.answer(caption)
            except: await cb.message.answer(caption)
        await cb.message.answer("✍️ Поделитесь своей историей!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✍️ Поделиться", callback_data="add_story")],
        ]))
    await cb.answer()

@main_router.callback_query(F.data == "add_story")
async def add_story_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✍️ Расскажите как наши браслеты или услуги помогли вам:")
    await state.set_state(StoryStates.waiting_text)
    await cb.answer()

@main_router.message(StoryStates.waiting_text)
async def add_story_text(msg: types.Message, state: FSMContext):
    await state.update_data(story_text=msg.text)
    await msg.answer("📸 Прикрепите фото или нажмите кнопку:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➡️ Без фото", callback_data="story_no_photo")],
    ]))
    await state.set_state(StoryStates.waiting_photo)

@main_router.message(StoryStates.waiting_photo)
async def add_story_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else None
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO stories (user_id, text, photo_file_id, approved, created_at) VALUES (?, ?, ?, FALSE, ?)",
              (msg.from_user.id, data["story_text"], photo_id, datetime.now()))
    conn.commit(); conn.close()
    try:
        await bot.send_message(ADMIN_ID, f"📖 НОВАЯ ИСТОРИЯ\n\n👤 {msg.from_user.first_name}\n\n{data['story_text']}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_story_{msg.from_user.id}")],
            ]))
    except: pass
    await msg.answer("✅ История отправлена на проверку!")
    await state.clear()

@main_router.callback_query(F.data == "story_no_photo")
async def story_no_photo(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO stories (user_id, text, photo_file_id, approved, created_at) VALUES (?, ?, NULL, FALSE, ?)",
              (cb.from_user.id, data["story_text"], datetime.now()))
    conn.commit(); conn.close()
    try:
        await bot.send_message(ADMIN_ID, f"📖 НОВАЯ ИСТОРИЯ\n\n👤 {cb.from_user.first_name}\n\n{data['story_text']}",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"approve_story_{cb.from_user.id}")],
            ]))
    except: pass
    await safe_edit(cb, "✅ История отправлена на проверку!")
    await state.clear(); await cb.answer()

@admin_router.callback_query(F.data.startswith("approve_story_"))
async def approve_story(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    try:
        user_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE stories SET approved = TRUE WHERE user_id = ? AND approved = FALSE", (user_id,))
    conn.commit(); conn.close()
    await cb.answer("✅ История одобрена!", show_alert=True)

@admin_router.callback_query(F.data == "admin_stories")
async def admin_stories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stories WHERE approved = FALSE"); pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stories WHERE approved = TRUE"); approved_count = c.fetchone()[0]
    conn.close()
    await safe_edit(cb, 
        f"📖 ИСТОРИИ КЛИЕНТОВ\n\nОжидают проверки: {pending}\nОдобрено: {approved_count}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТ "КАКОЙ КАМЕНЬ ПОДХОДИТ ИМЕННО ВАМ"
# ═══════════════════════════════════════════════════════════════════════════

# ⚠️  TODO: ЛОГИКА ПОДБОРА КАМНЕЙ
# Сейчас используется временная матрица (пол + тип + q3 + q4 → камень)
# Нужно заменить на реальную логику мастера
# Ищи: QUIZ_STONES = { и заменяй значения
QUIZ_STONES = {
    ("f_lost","empty","recent"):    ("Розовый кварц","💗","Камень нежного исцеления сердца","Он мягко растопит боль и напомнит вам о вашей ценности"),
    ("f_lost","empty","months"):    ("Лунный камень","🤍","Камень возвращения к себе","Он поможет снова почувствовать себя живой и настоящей"),
    ("f_lost","empty","year"):      ("Аметист","💜","Камень глубокого исцеления","Он очистит накопившуюся боль и вернёт внутренний свет"),
    ("f_lost","empty","always"):    ("Аметист","💜","Камень духовной трансформации","Он поможет переписать сценарий и начать жить по-настоящему"),
    ("f_lost","anger","recent"):    ("Гранат","❤️","Камень трансформации сильных эмоций","Он направит вашу силу в нужное русло"),
    ("f_lost","anger","months"):    ("Тигровый глаз","🟠","Камень уверенности и ясности","Он поможет видеть ситуацию трезво и двигаться дальше"),
    ("f_lost","anger","year"):      ("Обсидиан","⚫","Камень честности с собой","Он поможет отпустить то, что давно пора отпустить"),
    ("f_lost","anger","always"):    ("Обсидиан","⚫","Камень глубинной трансформации","Он вскроет корень и поможет изменить паттерн навсегда"),
    ("f_lost","fear","recent"):     ("Лунный камень","🤍","Камень мягкой защиты и интуиции","Он окутает вас безопасностью и укажет верный путь"),
    ("f_lost","fear","months"):     ("Аквамарин","💙","Камень спокойной силы","Он успокоит шторм внутри и даст ощущение опоры"),
    ("f_lost","fear","year"):       ("Аметист","💜","Камень покоя и защиты","Он создаст барьер между вами и вашими страхами"),
    ("f_lost","fear","always"):     ("Лабрадор","🔵","Камень магической защиты","Он защитит вашу чувствительную природу от мира"),
    ("f_lost","numb","recent"):     ("Сердолик","🔶","Камень пробуждения чувств","Он мягко разбудит то, что онемело внутри"),
    ("f_lost","numb","months"):     ("Гранат","❤️","Камень возвращения к жизни","Он зажжёт искру там, где сейчас темно"),
    ("f_lost","numb","year"):       ("Цитрин","💛","Камень радости и тепла","Он будет напоминать каждый день — жизнь прекрасна"),
    ("f_lost","numb","always"):     ("Сердолик","🔶","Камень жизненной силы","Он пробудит вашу силу которая всегда была внутри"),
    ("f_grow","intuition","energy"):("Лабрадор","🔵","Камень магической интуиции","Он резко усилит ваши способности чувствовать и предвидеть"),
    ("f_grow","intuition","blocks"):("Аметист","💜","Камень ясности и мудрости","Он растворит туман в голове и откроет третий глаз"),
    ("f_grow","intuition","people"):("Лабрадор","🔵","Камень невидимости и защиты","Он скроет вашу силу от тех кто хочет её забрать"),
    ("f_grow","intuition","unknown"):("Горный хрусталь","🔮","Камень чистого канала","Он уберёт всё лишнее и позволит слышать себя чётко"),
    ("f_grow","money","energy"):    ("Цитрин","💛","Камень денежного потока","Он привлечёт изобилие и откроет новые возможности"),
    ("f_grow","money","blocks"):    ("Тигровый глаз","🟠","Камень деловой удачи","Он уберёт блоки и придаст уверенности в действиях"),
    ("f_grow","money","people"):    ("Пирит","✨","Камень притяжения богатства","Он создаст поле изобилия вокруг вас"),
    ("f_grow","money","unknown"):   ("Цитрин","💛","Камень трансформации в достаток","Он найдёт и уберёт скрытый блок на деньги"),
    ("f_grow","feminine","energy"): ("Гранат","❤️","Камень женской силы и страсти","Он пробудит вашу магнетическую женскую природу"),
    ("f_grow","feminine","blocks"): ("Розовый кварц","💗","Камень открытого сердца","Он снимет панцирь и позволит снова притягивать любовь"),
    ("f_grow","feminine","people"): ("Лабрадор","🔵","Камень защиты женской энергии","Он защитит вашу нежность от чужих вторжений"),
    ("f_grow","feminine","unknown"):("Лунный камень","🤍","Камень женских циклов и силы","Он настроит вас на вашу природу и глубинный ритм"),
    ("f_grow","protect","energy"):  ("Чёрный турмалин","🖤","Камень мощной защиты","Он создаст непробиваемый щит вокруг вашего пространства"),
    ("f_grow","protect","blocks"):  ("Обсидиан","⚫","Камень очищения пространства","Он вычистит чужую энергию и сбросит чужие программы"),
    ("f_grow","protect","people"):  ("Чёрный турмалин","🖤","Камень отражения негатива","Он будет отражать чужую зависть и злой умысел"),
    ("f_grow","protect","unknown"): ("Лабрадор","🔵","Камень магического барьера","Он скроет вас от чужих глаз и нежелательных влияний"),
    ("m_down","nomoney","recent"):  ("Цитрин","💛","Камень быстрого сдвига в деньгах","Он запустит финансовый поток уже в ближайшее время"),
    ("m_down","nomoney","months"):  ("Тигровый глаз","🟠","Камень терпеливой силы","Он даст выдержку и приведёт деньги через правильные действия"),
    ("m_down","nomoney","year"):    ("Пирит","✨","Камень притяжения изобилия","Он сломает хронический паттерн нехватки"),
    ("m_down","nomoney","always"):  ("Цитрин","💛","Камень трансформации денежного блока","Он найдёт корень проблемы и уберёт его"),
    ("m_down","collapsed","recent"):("Обсидиан","⚫","Камень честного взгляда на ситуацию","Он даст ясность и покажет путь из руин"),
    ("m_down","collapsed","months"):("Тигровый глаз","🟠","Камень восстановления силы воли","Он вернёт веру в себя и способность действовать"),
    ("m_down","collapsed","year"):  ("Гранат","❤️","Камень возрождения","Он разожжёт огонь в том что казалось потухшим"),
    ("m_down","collapsed","always"):("Гранат","❤️","Камень кардинальных перемен","Он даст энергию полностью переписать свою историю"),
    ("m_down","apathy","recent"):   ("Сердолик","🔶","Камень пробуждения мотивации","Он быстро вернёт желание действовать и двигаться"),
    ("m_down","apathy","months"):   ("Гранат","❤️","Камень восстановления жизненной силы","Он вернёт вкус к жизни и желание побеждать"),
    ("m_down","apathy","year"):     ("Тигровый глаз","🟠","Камень пробуждения воина","Он напомнит вам кто вы есть на самом деле"),
    ("m_down","apathy","always"):   ("Гранат","❤️","Камень глубинного пробуждения","Он найдёт и зажжёт вашу внутреннюю искру"),
    ("m_down","passing","recent"):  ("Лабрадор","🔵","Камень открытия пути","Он уберёт невидимые преграды и откроет нужные двери"),
    ("m_down","passing","months"):  ("Аметист","💜","Камень поиска своего пути","Он даст ясность в вопросе кто вы и куда идёте"),
    ("m_down","passing","year"):    ("Лабрадор","🔵","Камень судьбоносных встреч","Он притянет людей и события которые изменят всё"),
    ("m_down","passing","always"):  ("Обсидиан","⚫","Камень разрыва с прошлым","Он поможет сделать шаг который вы так долго откладывали"),
    ("m_up","cashflow","doubt"):    ("Цитрин","💛","Камень уверенного изобилия","Он уберёт сомнения в том что вы достойны большого"),
    ("m_up","cashflow","people"):   ("Обсидиан","⚫","Камень защиты капитала","Он создаст барьер от тех кто хочет забрать ваше"),
    ("m_up","cashflow","burnout"):  ("Цитрин","💛","Камень стабильного потока","Он обеспечит постоянный приток без выгорания"),
    ("m_up","cashflow","unknown"):  ("Пирит","✨","Камень денежного магнита","Он найдёт и устранит скрытый блок на большие деньги"),
    ("m_up","clarity","doubt"):     ("Горный хрусталь","🔮","Камень кристальной ясности ума","Он уберёт туман и даст чёткость в решениях"),
    ("m_up","clarity","people"):    ("Тигровый глаз","🟠","Камень проницательности","Он позволит видеть людей насквозь и не ошибаться"),
    ("m_up","clarity","burnout"):   ("Аквамарин","💙","Камень холодного разума","Он охладит голову и вернёт стратегическое мышление"),
    ("m_up","clarity","unknown"):   ("Лабрадор","🔵","Камень интуитивных решений","Он даст доступ к знанию которое сложно объяснить логически"),
    ("m_up","strength","doubt"):    ("Гранат","❤️","Камень несгибаемой силы","Он даст физическую и психологическую выносливость"),
    ("m_up","strength","people"):   ("Чёрный турмалин","🖤","Камень неуязвимости","Он сделает вас недосягаемым для чужих атак"),
    ("m_up","strength","burnout"):  ("Сердолик","🔶","Камень неиссякаемой энергии","Он будет постоянно подпитывать вашу жизненную силу"),
    ("m_up","strength","unknown"):  ("Гранат","❤️","Камень активации внутреннего воина","Он пробудит вашу природную силу в полную мощь"),
    ("m_up","shield","doubt"):      ("Обсидиан","⚫","Камень непробиваемой защиты","Он закроет вас от тех кто боится вашего роста"),
    ("m_up","shield","people"):     ("Чёрный турмалин","🖤","Камень отражения зависти","Он вернёт весь негатив обратно к источнику"),
    ("m_up","shield","burnout"):    ("Лабрадор","🔵","Камень невидимости для врагов","Он скроет ваши планы от недоброжелателей"),
    ("m_up","shield","unknown"):    ("Обсидиан","⚫","Камень глубинной защиты","Он найдёт и нейтрализует источник угрозы"),
}

@main_router.callback_query(F.data == "quiz_start")
async def quiz_start(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # Отмечаем что пользователь начал тест (completed=0)
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO quiz_started (user_id, started_at, completed) VALUES (?,?,?)",
              (cb.from_user.id, datetime.now(), 0))
    conn.commit(); conn.close()
    await safe_edit(cb, 
        "🔮 ТЕСТ: КАКОЙ КАМЕНЬ ПОДХОДИТ ИМЕННО ВАМ?\n\n"
        "5 шагов. Отвечайте честно — чем точнее, тем точнее результат.\n\n"
        "Шаг 1 из 5 — Кто вы?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="👩 Женщина", callback_data="qz_g_f")],
            [types.InlineKeyboardButton(text="👨 Мужчина", callback_data="qz_g_m")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("qz_g_"))
async def qz_gender(cb: types.CallbackQuery, state: FSMContext):
    gender = cb.data.split("_")[-1]
    await state.update_data(qz_type_prefix=gender)
    if gender == "f":
        await safe_edit(cb, "Шаг 2 из 5 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💔 Больно — что-то важное ушло или рассыпалось", callback_data="qz_t_f_lost")],
                [types.InlineKeyboardButton(text="🌱 Развиваюсь — ищу себя и свой путь", callback_data="qz_t_f_grow")],
            ]))
    else:
        await safe_edit(cb, "Шаг 2 из 5 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🌑 Всё навалилось — не вывожу", callback_data="qz_t_m_down")],
                [types.InlineKeyboardButton(text="⚡ Рвусь вперёд — нужна дополнительная сила", callback_data="qz_t_m_up")],
            ]))
    await cb.answer()

@main_router.callback_query(F.data == "qz_t_f_lost")
async def qz_f_lost(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_type="f_lost")
    await safe_edit(cb, "Шаг 3 из 5 — Что сейчас внутри?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="😔 Пусто — как будто что-то важное ушло вместе с ним", callback_data="qz_q3_empty")],
            [types.InlineKeyboardButton(text="😤 Злость и обида — на него, на себя, на всё", callback_data="qz_q3_anger")],
            [types.InlineKeyboardButton(text="😰 Страх — а вдруг так теперь всегда", callback_data="qz_q3_fear")],
            [types.InlineKeyboardButton(text="😶 Онемела — не чувствую ни боли ни радости", callback_data="qz_q3_numb")],
        ]))
    await cb.answer()

@main_router.callback_query(F.data == "qz_t_f_grow")
async def qz_f_grow(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_type="f_grow")
    await safe_edit(cb, "Шаг 3 из 5 — Что сейчас важнее всего усилить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💫 Интуицию и ясность мышления", callback_data="qz_q3_intuition")],
            [types.InlineKeyboardButton(text="💰 Материальный поток и изобилие", callback_data="qz_q3_money")],
            [types.InlineKeyboardButton(text="❤️ Женскую энергию и притяжение", callback_data="qz_q3_feminine")],
            [types.InlineKeyboardButton(text="🛡 Защиту и чистоту пространства", callback_data="qz_q3_protect")],
        ]))
    await cb.answer()

@main_router.callback_query(F.data == "qz_t_m_down")
async def qz_m_down(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_type="m_down")
    await safe_edit(cb, "Шаг 3 из 5 — Что сейчас происходит?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💸 Деньги не идут — работаю, а результата нет", callback_data="qz_q3_nomoney")],
            [types.InlineKeyboardButton(text="💔 Всё рассыпалось — отношения, планы, смыслы", callback_data="qz_q3_collapsed")],
            [types.InlineKeyboardButton(text="😶 Апатия — встаю и не понимаю зачем", callback_data="qz_q3_apathy")],
            [types.InlineKeyboardButton(text="🌑 Ощущение что жизнь идёт мимо меня", callback_data="qz_q3_passing")],
        ]))
    await cb.answer()

@main_router.callback_query(F.data == "qz_t_m_up")
async def qz_m_up(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_type="m_up")
    await safe_edit(cb, "Шаг 3 из 5 — Что хотите усилить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💰 Денежный поток и деловую удачу", callback_data="qz_q3_cashflow")],
            [types.InlineKeyboardButton(text="🧠 Ясность ума и скорость решений", callback_data="qz_q3_clarity")],
            [types.InlineKeyboardButton(text="⚡ Физическую силу и выносливость", callback_data="qz_q3_strength")],
            [types.InlineKeyboardButton(text="🛡 Защиту от конкурентов и завистников", callback_data="qz_q3_shield")],
        ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("qz_q3_"))
async def qz_q3(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_q3=cb.data.replace("qz_q3_",""))
    data = await state.get_data()
    qz_type = data.get("qz_type","f_lost")
    if qz_type in ("f_lost","f_grow"):
        q = "Шаг 4 из 5 — Бывает ли ощущение — стараетесь, а всё как в стену?"
        opts = [("🪨 Да постоянно — будто что-то блокирует","qz_q4_wall"),
                ("🌊 Волнами — то лучше, то снова стопорится","qz_q4_waves"),
                ("🌫 Есть ощущение чужого взгляда или влияния","qz_q4_eyeon"),
                ("🌱 Просто нужна точка опоры","qz_q4_ground")]
    else:
        q = "Шаг 4 из 5 — Бывает ощущение что сколько ни вкладываешь — всё уходит?"
        opts = [("🪨 Да — как дыра, деньги энергия время исчезают","qz_q4_drain"),
                ("🎯 Стараюсь, но что-то постоянно сбивает","qz_q4_sabotage"),
                ("👤 Есть люди рядом которые тянут вниз","qz_q4_vampires"),
                ("🌫 Просто нет почвы под ногами","qz_q4_noground")]
    await safe_edit(cb, q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t, callback_data=d)] for t,d in opts]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("qz_q4_"))
async def qz_q4(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_q4=cb.data.replace("qz_q4_",""))
    data = await state.get_data()
    qz_type = data.get("qz_type","f_lost")
    if qz_type in ("f_lost","f_grow"):
        q = "Шаг 5 из 5 — Чего вы хотите прямо сейчас — честно?"
        opts = [("🔥 Снова почувствовать себя живой и желанной","qz_q5_alive"),
                ("🛡 Защититься — от боли, людей, чужого влияния","qz_q5_protect"),
                ("💫 Отпустить прошлое и двигаться дальше","qz_q5_release"),
                ("🤍 Просто внутреннего покоя","qz_q5_peace")]
    else:
        q = "Шаг 5 из 5 — Чего вы хотите прямо сейчас — честно?"
        opts = [("⚡ Вернуть энергию и желание действовать","qz_q5_energy"),
                ("🛡 Защититься — от людей, потерь, влияния","qz_q5_protect"),
                ("💰 Сдвинуть деньги и дела с мёртвой точки","qz_q5_money"),
                ("🧭 Найти направление — понять куда идти","qz_q5_direction")]
    await safe_edit(cb, q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t, callback_data=d)] for t,d in opts]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("qz_q5_"))
async def qz_result(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qz_type = data.get("qz_type","f_lost")
    q3 = data.get("qz_q3","")
    q4 = data.get("qz_q4","")
    stone, emoji, desc, why = QUIZ_STONES.get((qz_type,q3,q4), ("Горный хрусталь","🔮","Камень чистоты и усиления","Он усилит любой запрос и очистит путь к цели"))
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO quiz_results (user_id, answers, recommended_stone, created_at) VALUES (?,?,?,?)",
              (cb.from_user.id, f"{qz_type}|{q3}|{q4}", stone, datetime.now()))
    c.execute("INSERT OR REPLACE INTO quiz_started (user_id, started_at, completed) VALUES (?,?,?)",
              (cb.from_user.id, datetime.now(), 1))
    conn.commit(); conn.close()
    if ADMIN_ID:
        asyncio.create_task(notify_admin_quiz(cb.from_user.id, stone, qz_type))
    # Ищем фото камня в базе знаний
    conn2 = get_db(); c2 = conn2.cursor()
    c2.execute("SELECT photo_file_id FROM knowledge WHERE stone_name=? OR stone_name LIKE ?",
               (stone, f"%{stone.split()[0]}%"))
    krow = c2.fetchone(); conn2.close()
    photo_id = krow[0] if krow and krow[0] else None

    result_text = (
        f"🔮 ВАШ КАМЕНЬ — {stone} {emoji}\n\n{desc}\n\n✨ {why}\n\n"
        f"Это экспресс-результат. Для точного подбора — пройдите диагностику по фото."
    )
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🩺 ПРОЙТИ ПОЛНУЮ ДИАГНОСТИКУ", callback_data="diag_start")],
        [types.InlineKeyboardButton(text="💎 ПОСМОТРЕТЬ ВИТРИНУ", callback_data="showcase_bracelets")],
        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
    ])
    try:
        if photo_id:
            await cb.message.answer_photo(photo=photo_id, caption=result_text[:1024], reply_markup=kb)
            await cb.message.delete()
        else:
            await cb.message.edit_text(result_text, reply_markup=kb)
    except Exception:
        try:
            await cb.message.answer(result_text, reply_markup=kb)
        except Exception:
            pass
    await state.clear(); await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ВИТРИНА БРАСЛЕТОВ
# ═══════════════════════════════════════════════════════════════════════════


@main_router.callback_query(F.data == "knowledge_list")
async def knowledge_list(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name")
    stones = c.fetchall(); conn.close()
    if not stones:
        await safe_edit(cb, "📚 БАЗА ЗНАНИЙ О КАМНЯХ\n\nБаза пока пустая!",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    buttons = [[types.InlineKeyboardButton(text=f"{s[1]} {s[2]}", callback_data=f"stone_info_{s[0]}")] for s in stones]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    await safe_edit(cb, "📚 БАЗА ЗНАНИЙ О КАМНЯХ\n\nВыберите камень:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("stone_info_"))
async def stone_detail(cb: types.CallbackQuery):
    try:
        stone_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT stone_name, emoji, properties, chakra, photo_file_id, short_desc, full_desc, color, price_per_bead, forms, notes FROM knowledge WHERE id=?", (stone_id,))
    s = c.fetchone(); conn.close()
    if not s: await cb.answer("Не найдено", show_alert=True); return
    name, emoji, props, chakra, photo_id, short_desc, full_desc, color, price, forms, notes = s
    # Строим красивую карточку
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
        lines.append(f"📿 Размеры бусин: {forms}")
    if price:
        lines.append(f"💰 Цена за бусину: {price} руб")
    if notes:
        lines.append(f"\n💡 {notes}")
    text = "\n".join(lines)[:3000]
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💍 ЗАКАЗАТЬ БРАСЛЕТ", callback_data="order_bracelet_start")],
        [types.InlineKeyboardButton(text="💎 НАЙТИ В ВИТРИНЕ", callback_data="showcase_bracelets")],
        [types.InlineKeyboardButton(text="← К СПИСКУ", callback_data="knowledge_list")]])
    try:
        if photo_id:
            await cb.message.answer_photo(photo=photo_id, caption=text[:1024], reply_markup=kb)
            await cb.message.delete()
        else:
            await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# БАЗА ЗНАНИЙ — АДМИН
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_knowledge")
async def admin_knowledge(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM knowledge"); count = c.fetchone()[0]; conn.close()
    await cb.message.edit_text(f"📚 БАЗА ЗНАНИЙ\n\nКамней в базе: {count}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ КАМЕНЬ", callback_data="knowledge_add")],
            [types.InlineKeyboardButton(text="📋 СПИСОК / УДАЛИТЬ", callback_data="knowledge_admin_list")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()

@admin_router.callback_query(F.data == "knowledge_add")
async def knowledge_add_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    await safe_edit(cb, "📚 ДОБАВИТЬ КАМЕНЬ\n\nВведите название (например: Аметист):")
    await state.set_state(KnowledgeAdminStates.stone_name); await cb.answer()

@admin_router.message(KnowledgeAdminStates.stone_name)
async def ka_name(msg: types.Message, state: FSMContext):
    await state.update_data(stone_name=msg.text)
    await msg.answer("Введите эмодзи (например: 💜):"); await state.set_state(KnowledgeAdminStates.stone_emoji)

@admin_router.message(KnowledgeAdminStates.stone_emoji)
async def ka_emoji(msg: types.Message, state: FSMContext):
    await state.update_data(stone_emoji=msg.text)
    await msg.answer("Опишите свойства камня:"); await state.set_state(KnowledgeAdminStates.stone_properties)

@admin_router.message(KnowledgeAdminStates.stone_properties)
async def ka_properties(msg: types.Message, state: FSMContext):
    await state.update_data(stone_properties=msg.text)
    await msg.answer("Стихии (или -):"); await state.set_state(KnowledgeAdminStates.stone_elements)

@admin_router.message(KnowledgeAdminStates.stone_elements)
async def ka_elements(msg: types.Message, state: FSMContext):
    await state.update_data(stone_elements=msg.text)
    await msg.answer("Знаки зодиака (или -):"); await state.set_state(KnowledgeAdminStates.stone_zodiac)

@admin_router.message(KnowledgeAdminStates.stone_zodiac)
async def ka_zodiac(msg: types.Message, state: FSMContext):
    await state.update_data(stone_zodiac=msg.text)
    await msg.answer("Чакра (или -):"); await state.set_state(KnowledgeAdminStates.stone_chakra)

@admin_router.message(KnowledgeAdminStates.stone_chakra)
async def ka_chakra(msg: types.Message, state: FSMContext):
    await state.update_data(stone_chakra=msg.text)
    await msg.answer("Отправьте фото камня или напишите 'пропустить':"); await state.set_state(KnowledgeAdminStates.stone_photo)

@admin_router.message(KnowledgeAdminStates.stone_photo)
async def ka_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else None
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO knowledge (stone_name, emoji, properties, elements, zodiac, chakra, photo_file_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
              (data["stone_name"],data["stone_emoji"],data["stone_properties"],data["stone_elements"],
               data["stone_zodiac"],data["stone_chakra"],photo_id,datetime.now()))
    conn.commit(); conn.close()
    await msg.answer(f"✅ {data['stone_emoji']} {data['stone_name']} добавлен!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить ещё", callback_data="knowledge_add")],
            [types.InlineKeyboardButton(text="← В ПАНЕЛЬ", callback_data="admin_panel")]]))
    await state.clear()

@admin_router.callback_query(F.data == "knowledge_admin_list")
async def knowledge_admin_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name")
    stones = c.fetchall(); conn.close()
    if not stones: await cb.answer("База пустая", show_alert=True); return
    buttons = [[types.InlineKeyboardButton(text=f"🗑 {s[1]} {s[2]}", callback_data=f"knowledge_del_{s[0]}")] for s in stones]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")])
    await safe_edit(cb, "📋 Нажмите чтобы удалить:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("knowledge_del_"))
async def knowledge_delete(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    try:
        sid = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT stone_name, emoji FROM knowledge WHERE id=?", (sid,)); s = c.fetchone()
    c.execute("DELETE FROM knowledge WHERE id=?", (sid,)); conn.commit(); conn.close()
    await cb.answer(f"✅ {s[1]} {s[0]} удалён!" if s else "✅ Удалено!", show_alert=True)
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name"); stones = c.fetchall(); conn.close()
    if not stones:
        await safe_edit(cb, "База пустая.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")]])); return
    buttons = [[types.InlineKeyboardButton(text=f"🗑 {s[1]} {s[2]}", callback_data=f"knowledge_del_{s[0]}")] for s in stones]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")])
    await safe_edit(cb, "📋 Нажмите чтобы удалить:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@admin_router.callback_query(F.data == "admin_quiz_results")
async def admin_quiz_results(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM quiz_results"); total = c.fetchone()[0]
    c.execute("SELECT recommended_stone, COUNT(*) cnt FROM quiz_results GROUP BY recommended_stone ORDER BY cnt DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = f"🔮 РЕЗУЛЬТАТЫ ТЕСТА\n\nВсего прошли: {total}\n\n🏆 Топ камней:\n"
    for stone, cnt in top: text += f"  {stone}: {cnt} чел.\n"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# СТАТУС ЗАКАЗА ДЛЯ КЛИЕНТА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "my_orders")
async def my_orders(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, total_price, status, created_at FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (cb.from_user.id,))
    orders = c.fetchall(); conn.close()
    if not orders:
        await safe_edit(cb, "📦 МОИ ЗАКАЗЫ\n\nЗаказов пока нет.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    STATUS_EMOJI = {'pending':'⏳ Ожидает','confirmed':'✅ Подтверждён','paid':'💰 Оплачен',
                    'in_progress':'🔨 В работе','shipped':'🚚 Отправлен','delivered':'📦 Доставлен','cancelled':'❌ Отменён'}
    text = "📦 МОИ ЗАКАЗЫ\n\n"
    for o in orders:
        text += f"Заказ #{o[0]}\n{STATUS_EMOJI.get(o[2], o[2])}\nСумма: {o[1]:.0f} руб\n\n"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()

@admin_router.callback_query(F.data == "admin_orders")
async def admin_orders(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT o.id, u.first_name, u.username, o.total_price, o.status FROM orders o LEFT JOIN users u ON o.user_id=u.user_id ORDER BY o.created_at DESC LIMIT 20")
    orders = c.fetchall(); conn.close()
    if not orders:
        await safe_edit(cb, "📦 Заказов нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]])); await cb.answer(); return
    buttons = []
    text = "📦 ЗАКАЗЫ\n\n"
    for o in orders:
        oid, fname, uname, price, status = o
        uinfo = f"@{uname}" if uname else (fname or "?")
        text += f"#{oid} {uinfo} — {price:.0f}₽ [{status}]\n"
        buttons.append([types.InlineKeyboardButton(text=f"#{oid} {uinfo} [{status}]", callback_data=f"order_status_{oid}")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    await safe_edit(cb, text[:3000], reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("order_status_"))
async def order_change_status(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    try:
        order_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT o.id, u.first_name, o.total_price, o.status FROM orders o LEFT JOIN users u ON o.user_id=u.user_id WHERE o.id=?", (order_id,))
    o = c.fetchone(); conn.close()
    if not o: await cb.answer("Не найдено", show_alert=True); return
    await safe_edit(cb, 
        f"📦 Заказ #{order_id}\nКлиент: {o[1] or '?'}\nСумма: {o[2]:.0f}₽\nСтатус: {o[3]}\n\nВыберите новый статус:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Подтверждён", callback_data=f"setstatus_confirmed_{order_id}")],
            [types.InlineKeyboardButton(text="💰 Оплачен", callback_data=f"setstatus_paid_{order_id}")],
            [types.InlineKeyboardButton(text="🔨 В работе", callback_data=f"setstatus_inprogress_{order_id}")],
            [types.InlineKeyboardButton(text="🚚 Отправлен", callback_data=f"setstatus_shipped_{order_id}")],
            [types.InlineKeyboardButton(text="📦 Доставлен", callback_data=f"setstatus_delivered_{order_id}")],
            [types.InlineKeyboardButton(text="❌ Отменён", callback_data=f"setstatus_cancelled_{order_id}")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_orders")],
        ]))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("setstatus_"))
async def set_order_status(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    parts = cb.data.split("_")
    order_id = int(parts[-1])
    status = parts[1]  # setstatus_confirmed_123
    STATUS_MAP = {'confirmed':'confirmed','paid':'paid','inprogress':'in_progress','shipped':'shipped','delivered':'delivered','cancelled':'cancelled'}
    real_status = STATUS_MAP.get(status, status)
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (real_status, order_id))
    c.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    r = c.fetchone(); conn.commit(); conn.close()
    STATUS_MSG = {
        'confirmed': '✅ Ваш заказ подтверждён! Мастер приступил к работе.',
        'paid': '💰 Оплата получена, спасибо!',
        'in_progress': '🔨 Ваш заказ в работе! Мастер создаёт его прямо сейчас.',
        'shipped': '🚚 Ваш заказ отправлен! Скоро будет у вас.',
        'delivered': '📦 Заказ доставлен! Наслаждайтесь силой камней 💎',
        'cancelled': '❌ Ваш заказ отменён. Если есть вопросы — напишите мастеру.',
    }
    if r and real_status in STATUS_MSG:
        try: await bot.send_message(r[0], f"📦 Заказ #{order_id}\n\n{STATUS_MSG[real_status]}")
        except: pass
    await cb.answer(f"✅ Статус: {real_status}", show_alert=True)
    await admin_orders(cb)

# ═══════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ПРИВЕТСТВИЯ — АДМИН
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_welcome_text")
async def admin_welcome_text(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    current = await get_setting('welcome_text', '')
    await cb.message.edit_text(
        f"✏️ ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ\n\nТекущий текст:\n{current}\n\nЧто редактируем?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✏️ Текст для НОВЫХ пользователей", callback_data="edit_welcome_new")],
            [types.InlineKeyboardButton(text="✏️ Текст для ВЕРНУВШИХСЯ", callback_data="edit_welcome_return")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ]))
    await cb.answer()

@admin_router.callback_query(F.data == "edit_welcome_new")
async def edit_welcome_new(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    current = await get_setting('welcome_text', '')
    await safe_edit(cb, f"✏️ Текущий текст для НОВЫХ:\n\n{current}\n\nНапишите новый текст:")
    await state.set_state(WelcomeTextStates.waiting_text)
    await cb.answer()

@admin_router.message(WelcomeTextStates.waiting_text)
async def save_welcome_text(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await set_setting('welcome_text', msg.text)
    await msg.answer("✅ Приветственный текст обновлён! Preview:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В ПАНЕЛЬ", callback_data="admin_panel")]]))
    await msg.answer(msg.text)
    await state.clear()

@admin_router.callback_query(F.data == "edit_welcome_return")
async def edit_welcome_return(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    current = await get_setting('return_text', '')
    await safe_edit(cb, f"✏️ Текущий текст для ВЕРНУВШИХСЯ:\n\n{current}\n\nНапишите новый:")
    await state.set_state(WelcomeTextStates.waiting_return_text)
    await cb.answer()

@admin_router.message(WelcomeTextStates.waiting_return_text)
async def save_return_text(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await set_setting('return_text', msg.text)
    await msg.answer("✅ Текст для вернувшихся обновлён!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В ПАНЕЛЬ", callback_data="admin_panel")]]))
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ПОИСК ПО БАЗЕ ЗНАНИЙ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "knowledge_search")
async def knowledge_search_start(cb: types.CallbackQuery, state: FSMContext):
    await safe_edit(cb, "🔍 ПОИСК ПО БАЗЕ ЗНАНИЙ\n\nВведите название камня или свойство\n(например: защита, любовь, аметист):")
    await state.set_state(QuizStates.q1)
    await state.update_data(search_mode='knowledge')
    await cb.answer()

@main_router.message(QuizStates.q1)
async def knowledge_search_results(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get('search_mode') != 'knowledge':
        await state.clear(); return
    query = msg.text.strip().lower()
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge WHERE lower(stone_name) LIKE ? OR lower(properties) LIKE ? OR lower(tasks) LIKE ? ORDER BY stone_name",
              (f'%{query}%', f'%{query}%', f'%{query}%'))
    results = c.fetchall(); conn.close()
    await state.clear()
    if not results:
        await msg.answer(f"🔍 По запросу '{query}' ничего не найдено.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📚 ВСЯ БАЗА", callback_data="knowledge_list")],
                [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]]))
        return
    buttons = [[types.InlineKeyboardButton(text=f"{r[1]} {r[2]}", callback_data=f"stone_info_{r[0]}")] for r in results]
    buttons.append([types.InlineKeyboardButton(text="← К БАЗЕ", callback_data="knowledge_list")])
    await msg.answer(f"🔍 Найдено: {len(results)} камней по запросу '{query}'",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

# ═══════════════════════════════════════════════════════════════════════════
# ФИЛЬТР ВИТРИНЫ ПО КАМНЮ И СВОЙСТВУ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "filter_bracelets")
async def filter_bracelets(cb: types.CallbackQuery):
    buttons = [
        [types.InlineKeyboardButton(text="⚡ ВСЕ БРАСЛЕТЫ", callback_data="showcase_bracelets")],
        [types.InlineKeyboardButton(text="━━━ ПО СВОЙСТВУ ━━━", callback_data="noop")],
        [types.InlineKeyboardButton(text="🛡 Защита", callback_data="bf_защит"),
         types.InlineKeyboardButton(text="❤️ Любовь", callback_data="bf_любов")],
        [types.InlineKeyboardButton(text="💰 Деньги", callback_data="bf_деньг"),
         types.InlineKeyboardButton(text="⚡ Энергия", callback_data="bf_энерги")],
        [types.InlineKeyboardButton(text="😌 Спокойствие", callback_data="bf_спокойств"),
         types.InlineKeyboardButton(text="💜 Духовность", callback_data="bf_духовн")],
        [types.InlineKeyboardButton(text="━━━ ПО КАМНЮ ━━━", callback_data="noop")],
        [types.InlineKeyboardButton(text="💜 Аметист", callback_data="bf_аметист"),
         types.InlineKeyboardButton(text="💗 Розовый кварц", callback_data="bf_розовый")],
        [types.InlineKeyboardButton(text="⚫ Обсидиан", callback_data="bf_обсидиан"),
         types.InlineKeyboardButton(text="🔶 Сердолик", callback_data="bf_сердолик")],
        [types.InlineKeyboardButton(text="💛 Цитрин", callback_data="bf_цитрин"),
         types.InlineKeyboardButton(text="❤️ Гранат", callback_data="bf_гранат")],
        [types.InlineKeyboardButton(text="🔵 Лабрадор", callback_data="bf_лабрадор"),
         types.InlineKeyboardButton(text="🟠 Тигровый глаз", callback_data="bf_тигровый")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]
    await safe_edit(cb, "💎 ФИЛЬТР ВИТРИНЫ\n\nВыберите что вам нужно:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("bf_"))
async def bracelet_filter_results(cb: types.CallbackQuery):
    search_term = cb.data.replace("bf_", "")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, name, desc, price, image_url FROM bracelets WHERE lower(name) LIKE ? OR lower(desc) LIKE ? ORDER BY created_at DESC",
              (f'%{search_term}%', f'%{search_term}%'))
    items = c.fetchall(); conn.close()
    if not items:
        await safe_edit(cb, 
            f"💎 По фильтру '{search_term}' нет товаров.\n\nПопробуйте другой фильтр.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💎 ВСЕ БРАСЛЕТЫ", callback_data="showcase_bracelets")],
                [types.InlineKeyboardButton(text="🔍 ФИЛЬТР", callback_data="filter_bracelets")],
                [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]]))
        await cb.answer(); return
    await cb.message.edit_text(f"💎 Найдено: {len(items)} браслетов",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔍 Другой фильтр", callback_data="filter_bracelets")],
            [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")]]))
    for item in items:
        bid, name, desc, price, image_url = item
        caption = f"💎 {name}\n\n{desc or ''}\n\n💰 {price:.0f} руб"
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🛒 В КОРЗИНУ", callback_data=f"add_to_cart_{bid}")]])
        try:
            if image_url: await cb.message.answer_photo(photo=image_url, caption=caption, reply_markup=kb)
            else: await cb.message.answer(caption, reply_markup=kb)
        except: await cb.message.answer(caption, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ФОНОВЫЕ ЗАДАЧИ: НАПОМИНАНИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def send_quiz_reminders():
    """Напоминание тем кто завершил тест но не прошёл диагностику (через ~24 часа)"""
    while True:
        try:
            await asyncio.sleep(3600)
            conn = get_db(); c = conn.cursor()
            c.execute("""SELECT qs.user_id FROM quiz_started qs
                WHERE qs.completed = 1
                AND qs.started_at < datetime('now', '-23 hours')
                AND qs.user_id NOT IN (SELECT user_id FROM diagnostics)
                AND qs.user_id NOT IN (SELECT user_id FROM diag_reminded)""")
            users = c.fetchall()
            for (uid,) in users:
                try:
                    await bot.send_message(uid,
                        "🔮 Помните, мы подобрали для вас камень?\n\n"
                        "Для точного персонального подбора мастер готов изучить ваш запрос по фото.\n\n"
                        "Это займёт 2 минуты — а результат останется с вами навсегда.",
                        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                            [types.InlineKeyboardButton(text="🩺 ПРОЙТИ ДИАГНОСТИКУ", callback_data="diag_start")]]))
                    c.execute("INSERT OR REPLACE INTO diag_reminded (user_id, reminded_at) VALUES (?,?)", (uid, datetime.now()))
                    conn.commit()
                    await asyncio.sleep(0.3)
                except: pass
            conn.close()
        except Exception as e:
            logger.error(f"reminder: {e}")
            await asyncio.sleep(300)

async def send_diag_followup():
    """Через 2 часа после диагностики — сообщение 'мастер уже изучает'"""
    while True:
        try:
            await asyncio.sleep(1800)
            conn = get_db(); c = conn.cursor()
            c.execute("""SELECT id, user_id FROM diagnostics
                WHERE created_at < datetime('now', '-90 minutes')
                AND created_at > datetime('now', '-150 minutes')
                AND (followup_sent IS NULL OR followup_sent = 0)""")
            rows = c.fetchall()
            for (did, uid) in rows:
                try:
                    await bot.send_message(uid,
                        "🔮 Мастер уже изучает ваши фото...\n\n"
                        "Персональный подбор камней — дело тонкое.\n"
                        "Мастер внимательно анализирует ваш запрос.\n\n"
                        "Результат придёт в течение 24 часов 💎")
                    c.execute("UPDATE diagnostics SET followup_sent=1 WHERE id=?", (did,))
                    conn.commit()
                    await asyncio.sleep(0.3)
                except: pass
            conn.close()
        except Exception as e:
            logger.error(f"followup: {e}")
            await asyncio.sleep(300)



# ═══════════════════════════════════════════════════════════════════════════
# БРАСЛЕТЫ НА ЗАКАЗ — ЦЕПОЧКА ВОПРОСОВ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "order_bracelet_start")
async def order_bracelet_start(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(cb, 
        "💍 БРАСЛЕТ НА ЗАКАЗ\n\n"
        "Мастер создаст браслет специально для вас.\n\n"
        "Вопрос 1 из 5\n\n"
        "🌟 В какой сфере жизни тебе нужна поддержка?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="❤️ Любовь и отношения", callback_data="ob1_love")],
            [types.InlineKeyboardButton(text="💪 Здоровье и жизненная сила", callback_data="ob1_health")],
            [types.InlineKeyboardButton(text="🌟 Самореализация и карьера", callback_data="ob1_career")],
            [types.InlineKeyboardButton(text="🔮 Духовность и интуиция", callback_data="ob1_spirit")],
            [types.InlineKeyboardButton(text="💰 Богатство и изобилие", callback_data="ob1_money")],
            [types.InlineKeyboardButton(text="🛡 Защита и очищение", callback_data="ob1_protect")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("ob1_"))
async def ob_q2(cb: types.CallbackQuery, state: FSMContext):
    labels = {
        "ob1_love": "❤️ Любовь и отношения",
        "ob1_health": "💪 Здоровье и жизненная сила",
        "ob1_career": "🌟 Самореализация и карьера",
        "ob1_spirit": "🔮 Духовность и интуиция",
        "ob1_money": "💰 Богатство и изобилие",
        "ob1_protect": "🛡 Защита и очищение",
    }
    await state.update_data(ob_sphere=labels.get(cb.data, cb.data))
    await safe_edit(cb, 
        "Вопрос 2 из 5\n\n"
        "🎯 Что именно хочешь изменить или усилить?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✨ Привлечь что-то новое", callback_data="ob2_attract")],
            [types.InlineKeyboardButton(text="🧹 Очиститься от старого", callback_data="ob2_clear")],
            [types.InlineKeyboardButton(text="⚡ Усилить то что уже есть", callback_data="ob2_boost")],
            [types.InlineKeyboardButton(text="🔍 Разобраться в себе", callback_data="ob2_clarity")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("ob2_"))
async def ob_q3(cb: types.CallbackQuery, state: FSMContext):
    labels = {
        "ob2_attract": "✨ Привлечь новое",
        "ob2_clear": "🧹 Очиститься от старого",
        "ob2_boost": "⚡ Усилить имеющееся",
        "ob2_clarity": "🔍 Разобраться в себе",
    }
    await state.update_data(ob_intent=labels.get(cb.data, cb.data))
    await safe_edit(cb, 
        "Вопрос 3 из 5\n\n"
        "👤 Для кого браслет?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="👩 Для себя (женщина)", callback_data="ob3_self_f")],
            [types.InlineKeyboardButton(text="👨 Для себя (мужчина)", callback_data="ob3_self_m")],
            [types.InlineKeyboardButton(text="🎁 Подарок женщине", callback_data="ob3_gift_f")],
            [types.InlineKeyboardButton(text="🎁 Подарок мужчине", callback_data="ob3_gift_m")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("ob3_"))
async def ob_q4(cb: types.CallbackQuery, state: FSMContext):
    labels = {
        "ob3_self_f": "👩 Для себя (женщина)",
        "ob3_self_m": "👨 Для себя (мужчина)",
        "ob3_gift_f": "🎁 Подарок женщине",
        "ob3_gift_m": "🎁 Подарок мужчине",
    }
    await state.update_data(ob_for=labels.get(cb.data, cb.data))
    await safe_edit(cb, 
        "Вопрос 4 из 5\n\n"
        "⚡ Насколько мощный браслет тебе нужен?\n\n"
        "Камни сами по себе уже работают — но мастер может дополнительно зарядить браслет "
        "энергией и намерением, усилив его действие многократно.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💎 Силы камней достаточно", callback_data="ob4_stones")],
            [types.InlineKeyboardButton(text="🔥 Хочу чтобы мастер зарядил браслет", callback_data="ob4_charged")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data.startswith("ob4_"))
async def ob_q5(cb: types.CallbackQuery, state: FSMContext):
    labels = {
        "ob4_stones": "💎 Сила камней",
        "ob4_charged": "🔥 Заряженный мастером",
    }
    await state.update_data(ob_power=labels.get(cb.data, cb.data))
    await safe_edit(cb, 
        "Вопрос 5 из 5\n\n"
        "🔮 Хочешь индивидуальный браслет, созданный именно под твою энергетику?\n\n"
        "Мастер проведёт диагностику твоего энергетического состояния — "
        "определит пробои, привязки, утечки и блоки в чакрах, "
        "и создаст браслет который закроет именно твои «дыры».\n\n"
        "Для этого понадобятся два фото — мастер читает энергетику по ним.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Да, хочу индивидуальный", callback_data="ob5_individual")],
            [types.InlineKeyboardButton(text="📿 Нет, браслет по теме без диагностики", callback_data="ob5_simple")],
        ])
    )
    await cb.answer()

@main_router.callback_query(F.data == "ob5_individual")
async def ob_individual(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(ob_type="индивидуальный с диагностикой")
    await safe_edit(cb, 
        "🔮 Отлично! Мастер проведёт полную диагностику.\n\n"
        "📏 Шаг 1 — Размер запястья\n\n"
        "Как измерить:\n"
        "• Обмотай нитку или полоску бумаги вокруг запястья\n"
        "• Отметь где концы сошлись\n"
        "• Измерь длину в сантиметрах\n"
        "• Прибавь 1–1.5 см — это и есть нужный размер браслета\n\n"
        "Введи размер цифрой (например: 17.5):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Не знаю свой размер", callback_data="ob_size_unknown")],
        ])
    )
    await state.set_state(OrderBraceletStates.q3_size)
    await cb.answer()

@main_router.callback_query(F.data == "ob5_simple")
async def ob_simple(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(ob_type="стандартный по теме")
    await safe_edit(cb, 
        "📿 Хороший выбор!\n\n"
        "📏 Размер запястья\n\n"
        "Как измерить:\n"
        "• Обмотай нитку или полоску бумаги вокруг запястья\n"
        "• Отметь где концы сошлись\n"
        "• Измерь длину в сантиметрах\n"
        "• Прибавь 1–1.5 см — это и есть нужный размер браслета\n\n"
        "Введи размер цифрой (например: 17.5):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Не знаю свой размер", callback_data="ob_size_unknown")],
        ])
    )
    await state.set_state(OrderBraceletStates.q3_size)
    await cb.answer()

@main_router.callback_query(F.data == "ob_size_unknown")
async def ob_size_unknown_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(ob_size="не указан — уточнит мастер")
    await ob_go_notes(cb.message, state, is_cb=True)
    await cb.answer()

@main_router.message(OrderBraceletStates.q3_size)
async def ob_save_size(msg: types.Message, state: FSMContext):
    text = msg.text.strip()
    # Пробуем распарсить число
    try:
        size_cm = float(text.replace(',', '.'))
        size_str = f"{size_cm} см"
    except ValueError:
        size_str = text
    await state.update_data(ob_size=size_str)
    await ob_go_notes(msg, state, is_cb=False)

async def ob_go_notes(msg_or_cb, state: FSMContext, is_cb=False):
    text = (
        "💬 Последний шаг!\n\n"
        "Есть пожелания по камням, цветам или что-то важное о себе "
        "что хочешь передать мастеру?\n\n"
        "Напиши или нажми «Пропустить»:"
    )
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Пропустить", callback_data="ob_notes_skip")],
    ])
    if is_cb:
        await msg_or_cb.edit_text(text, reply_markup=kb)
    else:
        await msg_or_cb.answer(text, reply_markup=kb)
    await state.set_state(OrderBraceletStates.q4_notes)

@main_router.callback_query(F.data == "ob_notes_skip")
async def ob_notes_skip(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(ob_notes="—")
    data = await state.get_data()
    ob_type = data.get('ob_type', '')
    if 'диагностик' in ob_type:
        await ob_ask_photos(cb.message, state, edit=True)
    else:
        await ob_finish_simple(cb.message, state, edit=True)
    await cb.answer()

@main_router.message(OrderBraceletStates.q4_notes)
async def ob_save_notes(msg: types.Message, state: FSMContext):
    await state.update_data(ob_notes=msg.text)
    data = await state.get_data()
    ob_type = data.get('ob_type', '')
    if 'диагностик' in ob_type:
        await ob_ask_photos(msg, state, edit=False)
    else:
        await ob_finish_simple(msg, state, edit=False)

async def ob_ask_photos(msg_or_cb, state: FSMContext, edit=False):
    text = (
        "📸 Почти готово!\n\n"
        "Для диагностики энергетики нужны два фото:\n\n"
        "1️⃣ Фото СПЕРЕДИ во весь рост\n"
        "   • Глаза смотрят прямо в камеру\n"
        "   • Обязательно без очков\n\n"
        "2️⃣ Фото СЗАДИ во весь рост\n\n"
        "Загружайте первое фото 👇"
    )
    if edit:
        await msg_or_cb.edit_text(text)
    else:
        await msg_or_cb.answer(text)
    await state.set_state(OrderBraceletStates.photo1)

async def ob_finish_simple(msg_or_cb, state: FSMContext, edit=False):
    """Без фото — просто принимаем заявку"""
    data = await state.get_data()
    text = (
        "✅ ЗАЯВКА ПРИНЯТА!\n\n"
        "Мастер изучит ваш запрос и свяжется в течение 24 часов "
        "для уточнения деталей и расчёта стоимости.\n\n"
        "💍 Ваш браслет будет создан специально для вас!"
    )
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
    ])
    if edit:
        await msg_or_cb.edit_text(text, reply_markup=kb)
    else:
        await msg_or_cb.answer(text, reply_markup=kb)
    await ob_notify_admin(data, msg_or_cb if not edit else None, state)
    await state.clear()

@main_router.message(OrderBraceletStates.photo1)
async def ob_photo1(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Пожалуйста, отправьте фотографию!")
        return
    await state.update_data(ob_photo1=msg.photo[-1].file_id)
    await msg.answer(
        "✅ Фото спереди получено!\n\n"
        "Теперь фото СЗАДИ во весь рост 👇"
    )
    await state.set_state(OrderBraceletStates.photo2)

@main_router.message(OrderBraceletStates.photo2)
async def ob_photo2(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Пожалуйста, отправьте фотографию!")
        return
    await state.update_data(ob_photo2=msg.photo[-1].file_id)
    data = await state.get_data()
    await msg.answer(
        "✅ Оба фото получены!\n\n"
        "Мастер проведёт диагностику и свяжется с вами в течение 24 часов.\n\n"
        "💍 Ваш индивидуальный браслет будет создан специально под вашу энергетику!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
        ])
    )
    # Сохраняем в БД
    conn = get_db(); c = conn.cursor()
    notes = (f"ЗАКАЗ БРАСЛЕТА (индивидуальный)\n"
             f"Сфера: {data.get('ob_sphere','')}\n"
             f"Намерение: {data.get('ob_intent','')}\n"
             f"Для: {data.get('ob_for','')}\n"
             f"Усиление: {data.get('ob_power','')}\n"
             f"Тип: {data.get('ob_type','')}\n"
             f"Размер: {data.get('ob_size','')}\n"
             f"Пожелания: {data.get('ob_notes','')}")
    c.execute("INSERT INTO diagnostics (user_id, photo_count, notes, created_at, photo1_file_id, photo2_file_id) VALUES (?,?,?,?,?,?)",
              (msg.from_user.id, 2, notes, datetime.now(), data.get('ob_photo1'), data.get('ob_photo2')))
    conn.commit(); conn.close()
    await ob_notify_admin(data, msg, state)
    await state.clear()

async def ob_notify_admin(data: dict, msg, state):
    if not ADMIN_ID: return
    try:
        user_id = msg.from_user.id if msg else 0
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT first_name, username FROM users WHERE user_id=?", (user_id,))
        u = c.fetchone(); conn.close()
        name = u[0] if u else str(user_id)
        uname = f"@{u[1]}" if u and u[1] else "нет"
        ob_type = data.get('ob_type', '')
        emoji = "🔮" if "диагностик" in ob_type else "📿"
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={user_id}")],
        ])
        await bot.send_message(ADMIN_ID,
            f"{emoji} НОВЫЙ ЗАКАЗ БРАСЛЕТА\n\n"
            f"👤 {name} ({uname})\n"
            f"🆔 ID: {user_id}\n\n"
            f"🌟 Сфера: {data.get('ob_sphere','')}\n"
            f"🎯 Намерение: {data.get('ob_intent','')}\n"
            f"👤 Для: {data.get('ob_for','')}\n"
            f"⚡ Усиление: {data.get('ob_power','')}\n"
            f"💎 Тип: {ob_type}\n"
            f"📏 Размер: {data.get('ob_size','')}\n"
            f"💬 Пожелания: {data.get('ob_notes','')}\n\n"
            f"{'📸 Фото для диагностики прикреплены ниже' if data.get('ob_photo1') else '📝 Без фото'}",
            reply_markup=kb)
        if data.get('ob_photo1'):
            await bot.send_photo(ADMIN_ID, data['ob_photo1'], caption="📸 Фото спереди")
        if data.get('ob_photo2'):
            await bot.send_photo(ADMIN_ID, data['ob_photo2'], caption="📸 Фото сзади")
    except Exception as e:
        logger.error(f"ob_notify: {e}")




# ═══════════════════════════════════════════════════════════════════════════
# МУЗЫКА — ВОСПРОИЗВЕДЕНИЕ ТРЕКА
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("play_track_"))
async def play_track(cb: types.CallbackQuery):
    try:
        track_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, desc, duration, audio_url FROM music WHERE id=?", (track_id,))
    t = c.fetchone(); conn.close()
    if not t:
        await cb.answer("Трек не найден", show_alert=True); return
    name, desc, duration, audio_url = t
    caption = f"🎵 {name}\n\n{desc or ''}\n\n⏱ {duration//60}:{duration%60:02d}" if duration else f"🎵 {name}"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← К СПИСКУ", callback_data="menu")]])
    try:
        await cb.message.answer_audio(audio=audio_url, caption=caption, reply_markup=kb)
        await cb.message.delete()
    except Exception as e:
        await safe_edit(cb, f"❌ Ошибка воспроизведения: {e}", reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ВИТРИНА — ПОДПАПКИ (до 100 коллекций)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "showcase_bracelets")
async def showcase_bracelets(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, name, emoji, desc FROM showcase_collections ORDER BY sort_order ASC, created_at ASC")
    cols = c.fetchall(); conn.close()
    if not cols:
        await safe_edit(cb, 
            "💎 ВИТРИНА\n\nКоллекции пока не добавлены.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    buttons = []
    for col in cols:
        cid, name, emoji, desc = col
        em = emoji or "💎"
        buttons.append([types.InlineKeyboardButton(text=f"{em} {name}", callback_data=f"sc_col_{cid}")])
    buttons.append([types.InlineKeyboardButton(text="🔍 ФИЛЬТР", callback_data="filter_bracelets")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    await safe_edit(cb, 
        "💎 ВИТРИНА БРАСЛЕТОВ\n\nВыберите коллекцию:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("sc_col_"))
async def showcase_collection(cb: types.CallbackQuery):
    try:
        col_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, emoji, desc FROM showcase_collections WHERE id=?", (col_id,))
    col = c.fetchone()
    c.execute("SELECT id, name, desc, price, image_file_id FROM showcase_items WHERE collection_id=? ORDER BY sort_order ASC, created_at ASC", (col_id,))
    items = c.fetchall(); conn.close()
    if not col:
        await cb.answer("Не найдено", show_alert=True); return
    em = col[1] or "💎"
    if not items:
        await safe_edit(cb, 
            f"{em} {col[0]}\n\n{col[2] or ''}\n\nТоваров пока нет.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← К ВИТРИНЕ", callback_data="showcase_bracelets")]]))
        await cb.answer(); return
    buttons = []
    for item in items:
        iid, iname, idesc, iprice, iimg = item
        price_str = f" — {iprice:.0f}₽" if iprice else ""
        buttons.append([types.InlineKeyboardButton(text=f"{iname}{price_str}", callback_data=f"sc_item_{iid}")])
    buttons.append([types.InlineKeyboardButton(text="← К ВИТРИНЕ", callback_data="showcase_bracelets")])
    await safe_edit(cb, 
        f"{em} {col[0]}\n\n{col[2] or ''}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("sc_item_"))
async def showcase_item(cb: types.CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT si.name, si.desc, si.price, si.image_file_id, sc.id FROM showcase_items si JOIN showcase_collections sc ON si.collection_id=sc.id WHERE si.id=?", (item_id,))
    item = c.fetchone(); conn.close()
    if not item:
        await cb.answer("Не найдено", show_alert=True); return
    name, desc, price, image_id, col_id = item
    price_str = f"\n\n💰 Цена: {price:.0f} руб" if price else ""
    text = f"💎 {name}\n\n{desc or ''}{price_str}"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ ОПЛАТИТЬ STARS", callback_data=f"stars_pay_{item_id}")],
        [types.InlineKeyboardButton(text="🛒 В КОРЗИНУ", callback_data=f"sc_cart_{item_id}"),
         types.InlineKeyboardButton(text="❤️", callback_data=f"wish_add_{item_id}")],
        [types.InlineKeyboardButton(text="💍 ЗАКАЗАТЬ БРАСЛЕТ", callback_data="order_bracelet_start")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data=f"sc_col_{col_id}")],
    ])
    try:
        if image_id:
            await cb.message.answer_photo(photo=image_id, caption=text[:1024], reply_markup=kb)
            await cb.message.delete()
        else:
            await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

@main_router.callback_query(F.data.startswith("sc_cart_"))
async def sc_add_to_cart(cb: types.CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, price FROM showcase_items WHERE id=?", (item_id,))
    item = c.fetchone()
    if not item:
        await cb.answer("Товар не найден", show_alert=True); conn.close(); return
    # Добавляем в корзину через таблицу cart (используем bracelet_id = item_id со смещением)
    c.execute("INSERT INTO cart (user_id, bracelet_id, quantity, added_at) VALUES (?,?,?,?)",
              (cb.from_user.id, item_id + 100000, 1, __import__('datetime').datetime.now()))
    conn.commit(); conn.close()
    await cb.answer(f"✅ {item[0]} добавлен в корзину!", show_alert=True)
    # Уведомляем мастера
    if ADMIN_ID:
        try:
            username = cb.from_user.username
            name_str = f"@{username}" if username else f"id:{cb.from_user.id}"
            price_str = f" — {item[1]:.0f} руб" if item[1] else ""
            await bot.send_message(
                ADMIN_ID,
                f"🛒 НОВЫЙ ТОВАР В КОРЗИНЕ\n\n"
                f"Товар: {item[0]}{price_str}\n"
                f"Покупатель: {name_str}\n"
                f"Telegram ID: {cb.from_user.id}",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(
                        text="✍️ Написать клиенту",
                        url=f"tg://user?id={cb.from_user.id}"
                    )],
                ])
            )
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════
# ВИТРИНА — АДМИН УПРАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

class ShowcaseStates(StatesGroup):
    col_name = State()
    col_emoji = State()
    col_desc = State()
    item_name = State()
    item_desc = State()
    item_price = State()
    item_stars = State()
    item_photo = State()
    edit_item_field = State()

@admin_router.callback_query(F.data == "admin_showcase")
async def admin_showcase(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, name, emoji FROM showcase_collections ORDER BY sort_order ASC, created_at ASC")
    cols = c.fetchall(); conn.close()
    buttons = []
    for col in cols:
        cid, name, emoji = col
        buttons.append([
            types.InlineKeyboardButton(text=f"{emoji or '💎'} {name}", callback_data=f"sc_admin_col_{cid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"sc_del_col_{cid}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="➕ НОВАЯ КОЛЛЕКЦИЯ", callback_data="sc_add_col")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    text = f"💎 УПРАВЛЕНИЕ ВИТРИНОЙ\n{len(cols)} коллекций (макс 100)"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data == "sc_add_col")
async def sc_add_col(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    await safe_edit(cb, "➕ НОВАЯ КОЛЛЕКЦИЯ\n\nВведи название коллекции:")
    await state.set_state(ShowcaseStates.col_name)
    await cb.answer()

@admin_router.message(ShowcaseStates.col_name)
async def sc_save_col_name(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.update_data(col_name=msg.text)
    await msg.answer("Введи эмодзи для коллекции (или напиши 'нет'):")
    await state.set_state(ShowcaseStates.col_emoji)

@admin_router.message(ShowcaseStates.col_emoji)
async def sc_save_col_emoji(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    emoji = msg.text if msg.text != 'нет' else '💎'
    await state.update_data(col_emoji=emoji)
    await msg.answer("Введи описание коллекции (или 'пропустить'):")
    await state.set_state(ShowcaseStates.col_desc)

@admin_router.message(ShowcaseStates.col_desc)
async def sc_save_col_desc(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    desc = msg.text if msg.text.lower() != 'пропустить' else ''
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO showcase_collections (name, emoji, desc, created_at) VALUES (?,?,?,?)",
              (data['col_name'], data.get('col_emoji','💎'), desc, __import__('datetime').datetime.now()))
    conn.commit(); conn.close()
    await msg.answer(f"✅ Коллекция '{data['col_name']}' создана!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💎 К ВИТРИНЕ", callback_data="admin_showcase")]]))
    await state.clear()

@admin_router.callback_query(F.data.startswith("sc_admin_col_"))
async def sc_admin_collection(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    try:
        col_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, emoji FROM showcase_collections WHERE id=?", (col_id,))
    col = c.fetchone()
    c.execute("SELECT id, name, price FROM showcase_items WHERE collection_id=? ORDER BY sort_order ASC, created_at ASC", (col_id,))
    items = c.fetchall(); conn.close()
    if not col: await cb.answer("Не найдено", show_alert=True); return
    buttons = []
    for item in items:
        iid, iname, iprice = item
        price_str = f" {iprice:.0f}₽" if iprice else ""
        buttons.append([
            types.InlineKeyboardButton(text=f"{iname}{price_str}", callback_data=f"sc_admin_item_{iid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"sc_del_item_{iid}_{col_id}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="➕ ДОБАВИТЬ ТОВАР", callback_data=f"sc_add_item_{col_id}")])
    buttons.append([types.InlineKeyboardButton(text="← К ВИТРИНЕ", callback_data="admin_showcase")])
    await safe_edit(cb, 
        f"{col[1] or '💎'} {col[0]}\n{len(items)} товаров",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("sc_add_item_"))
async def sc_add_item(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    try:
        col_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    await state.update_data(sc_col_id=col_id)
    await safe_edit(cb, "➕ НОВЫЙ ТОВАР\n\nВведи название товара:")
    await state.set_state(ShowcaseStates.item_name)
    await cb.answer()

@admin_router.message(ShowcaseStates.item_name)
async def sc_save_item_name(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.update_data(item_name=msg.text)
    await msg.answer("Введи описание товара (или 'пропустить'):")
    await state.set_state(ShowcaseStates.item_desc)

@admin_router.message(ShowcaseStates.item_desc)
async def sc_save_item_desc(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    desc = msg.text if msg.text.lower() != 'пропустить' else ''
    await state.update_data(item_desc=desc)
    await msg.answer("Введи цену (число, или 'пропустить'):")
    await state.set_state(ShowcaseStates.item_price)

@admin_router.message(ShowcaseStates.item_price)
async def sc_save_item_price(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: price = float(msg.text.replace(',', '.'))
    except: price = None
    await state.update_data(item_price=price)
    await msg.answer("Цена в ⭐ Telegram Stars (целое число, например 150)\nИли напиши 'пропустить':")
    await state.set_state(ShowcaseStates.item_stars)

@admin_router.message(ShowcaseStates.item_stars)
async def sc_save_item_stars(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: stars = int(msg.text.strip())
    except: stars = 0
    await state.update_data(item_stars=stars)
    await msg.answer("Отправь фото товара (или напиши 'пропустить'):")
    await state.set_state(ShowcaseStates.item_photo)

@admin_router.message(ShowcaseStates.item_photo)
async def sc_save_item_photo(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    image_id = msg.photo[-1].file_id if msg.photo else None
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO showcase_items (collection_id, name, desc, price, stars_price, image_file_id, created_at) VALUES (?,?,?,?,?,?,?)",
              (data['sc_col_id'], data['item_name'], data.get('item_desc',''),
               data.get('item_price'), data.get('item_stars', 0), image_id, __import__('datetime').datetime.now()))
    conn.commit(); conn.close()
    await msg.answer(f"✅ Товар '{data['item_name']}' добавлен!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← К КОЛЛЕКЦИИ", callback_data=f"sc_admin_col_{data['sc_col_id']}")],
            [types.InlineKeyboardButton(text="➕ ЕЩЁ ТОВАР", callback_data=f"sc_add_item_{data['sc_col_id']}")],
        ]))
    await state.clear()

@admin_router.callback_query(F.data.startswith("sc_admin_item_"))
async def sc_admin_item(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT si.id, si.name, si.desc, si.price, si.image_file_id, si.collection_id FROM showcase_items si WHERE si.id=?", (item_id,))
    item = c.fetchone(); conn.close()
    if not item: await cb.answer("Не найдено", show_alert=True); return
    iid, name, desc, price, img, col_id = item
    text = f"✏️ {name}\n\n{desc or '—'}\n💰 {price:.0f}₽" if price else f"✏️ {name}\n\n{desc or '—'}"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✏️ Название", callback_data=f"sc_edit_name_{iid}"),
         types.InlineKeyboardButton(text="✏️ Описание", callback_data=f"sc_edit_desc_{iid}")],
        [types.InlineKeyboardButton(text="✏️ Цена ₽", callback_data=f"sc_edit_price_{iid}"),
         types.InlineKeyboardButton(text="⭐ Цена Stars", callback_data=f"sc_edit_stars_{iid}")],
        [types.InlineKeyboardButton(text="📸 Фото", callback_data=f"sc_edit_photo_{iid}")],
        [types.InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"sc_del_item_{iid}_{col_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data=f"sc_admin_col_{col_id}")],
    ])
    try:
        if img:
            await cb.message.answer_photo(photo=img, caption=text[:1024], reply_markup=kb)
            await cb.message.delete()
        else:
            await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

@admin_router.callback_query(F.data.startswith("sc_edit_"))
async def sc_edit_item_field(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    parts = cb.data.split("_")
    field = parts[2]  # sc_edit_name_123
    item_id = int(parts[-1])
    await state.update_data(sc_edit_item_id=item_id, sc_edit_field=field)
    prompts = {"name": "Введи новое название:", "desc": "Введи новое описание:", 
               "price": "Введи новую цену:", "photo": "Отправь новое фото:"}
    await cb.message.edit_text(f"✏️ {prompts.get(field, 'Введи значение:')}")
    await state.set_state(ShowcaseStates.edit_item_field)
    await cb.answer()

@admin_router.message(ShowcaseStates.edit_item_field)
async def sc_save_edit(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    item_id = data['sc_edit_item_id']
    field = data['sc_edit_field']
    conn = get_db(); c = conn.cursor()
    if field == 'name':
        c.execute("UPDATE showcase_items SET name=? WHERE id=?", (msg.text, item_id))
    elif field == 'desc':
        c.execute("UPDATE showcase_items SET desc=? WHERE id=?", (msg.text, item_id))
    elif field == 'price':
        try: price = float(msg.text.replace(',','.'))
        except: price = None
        c.execute("UPDATE showcase_items SET price=? WHERE id=?", (price, item_id))
    elif field == 'stars':
        try: stars = int(msg.text.strip())
        except: stars = 0
        c.execute("UPDATE showcase_items SET stars_price=? WHERE id=?", (stars, item_id))
    elif field == 'photo':
        if msg.photo:
            c.execute("UPDATE showcase_items SET image_file_id=? WHERE id=?", (msg.photo[-1].file_id, item_id))
    c.execute("SELECT collection_id FROM showcase_items WHERE id=?", (item_id,))
    r = c.fetchone(); conn.commit(); conn.close()
    await msg.answer("✅ Обновлено!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← К КОЛЛЕКЦИИ", callback_data=f"sc_admin_col_{r[0]}" if r else "admin_showcase")]]))
    await state.clear()

@admin_router.callback_query(F.data.startswith("sc_del_item_"))
async def sc_del_item(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    parts = cb.data.split("_")
    item_id = int(parts[3])
    col_id = int(parts[4]) if len(parts) > 4 else 0
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM showcase_items WHERE id=?", (item_id,))
    conn.commit(); conn.close()
    await cb.answer("✅ Товар удалён", show_alert=True)
    if col_id:
        await sc_admin_collection(cb)

@admin_router.callback_query(F.data.startswith("sc_del_col_"))
async def sc_del_col(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    try:
        col_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM showcase_items WHERE collection_id=?", (col_id,))
    c.execute("DELETE FROM showcase_collections WHERE id=?", (col_id,))
    conn.commit(); conn.close()
    await cb.answer("✅ Коллекция удалена", show_alert=True)
    await admin_showcase(cb)


@admin_router.callback_query(F.data == "admin_workouts")
async def admin_workouts(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM workouts')
    workouts = c.fetchall()
    conn.close()
    
    text = "🏋️ ТРЕНИРОВКИ:\n\n"
    if workouts:
        for w in workouts:
            text += f"• {w[0]}\n"
    else:
        text += "Тренировок нет"
    
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_workout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()


@admin_router.callback_query(F.data == "add_workout")
async def add_workout_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название тренировки:")
    await state.set_state(AdminStates.add_workout)
    await cb.answer()


@admin_router.message(AdminStates.add_workout)
async def add_workout_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO workouts (name, desc, duration, difficulty, created_at) VALUES (?, ?, ?, ?, ?)",
                 (name, "Описание", 30, "Средняя", datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Тренировка '{name}' добавлена!")
        logger.info(f"Тренировка '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - МУЗЫКА
# ═══════════════════════════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM STARS — ОПЛАТА
# ═══════════════════════════════════════════════════════════════════════════

# ── Кнопка «Оплатить» из карточки товара ──
@main_router.callback_query(F.data.startswith("stars_pay_"))
async def stars_pay(cb: types.CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT name, desc, price, stars_price, image_file_id FROM showcase_items WHERE id=?", (item_id,))
    item = c.fetchone(); conn.close()
    if not item:
        await cb.answer("Товар не найден", show_alert=True); return
    name, desc, rub_price, stars_price, img = item
    if not stars_price or stars_price < 1:
        await cb.answer("⭐ Цена в Stars не указана. Обратитесь к мастеру.", show_alert=True); return
    stars = int(stars_price)
    desc_text = (desc or name)[:255]
    # payload — кодируем item_id и user_id для идентификации после оплаты
    payload = f"item_{item_id}_user_{cb.from_user.id}"
    await cb.message.answer_invoice(
        title=name[:32],
        description=desc_text,
        payload=payload,
        currency="XTR",
        provider_token="",          # для Stars всегда пустая строка
        prices=[types.LabeledPrice(label=name[:32], amount=stars)],
        photo_url=None,
    )
    await cb.answer()

# ── ОБЯЗАТЕЛЬНЫЙ обработчик pre_checkout — подтверждаем оплату ──
@main_router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    # Здесь можно проверить наличие товара, актуальность цены и т.д.
    # Если всё ок — отвечаем True, иначе False + error_message
    parts = query.invoice_payload.split("_")
    try:
        item_id = int(parts[1])
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT id, stars_price FROM showcase_items WHERE id=?", (item_id,))
        item = c.fetchone(); conn.close()
        if item and item[1] and int(item[1]) == query.total_amount:
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="Товар недоступен или цена изменилась")
    except Exception as e:
        logger.error(f"pre_checkout error: {e}")
        await query.answer(ok=True)  # не блокируем при ошибке парсинга

# ── Успешная оплата ──
@main_router.message(F.successful_payment)
async def successful_payment(msg: types.Message):
    pay = msg.successful_payment
    payload = pay.invoice_payload
    stars = pay.total_amount
    charge_id = pay.telegram_payment_charge_id
    parts = payload.split("_")
    item_id = int(parts[1]) if len(parts) > 1 else 0
    conn = get_db(); c = conn.cursor()
    # Получаем имя товара
    c.execute("SELECT name FROM showcase_items WHERE id=?", (item_id,))
    item = c.fetchone()
    item_name = item[0] if item else f"Товар #{item_id}"
    # Сохраняем транзакцию
    c.execute("""INSERT INTO stars_orders
                 (user_id, item_id, item_name, stars_amount, charge_id, status, created_at)
                 VALUES (?,?,?,?,?,'paid',?)""",
              (msg.from_user.id, item_id, item_name, stars, charge_id, datetime.now()))
    conn.commit(); conn.close()
    # Подтверждаем пользователю
    username = msg.from_user.username or msg.from_user.first_name
    await msg.answer(
        f"✅ ОПЛАТА ПОЛУЧЕНА\n\n"
        f"⭐ {stars} Stars за «{item_name}»\n\n"
        f"Мастер получил уведомление и свяжется с тобой для уточнения деталей.\n\n"
        f"ID платежа: {charge_id[:16]}…",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📦 МОИ ЗАКАЗЫ", callback_data="my_stars_orders")],
            [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
        ])
    )
    # Уведомляем мастера
    if ADMIN_ID:
        try:
            user_link = f"tg://user?id={msg.from_user.id}"
            await bot.send_message(
                ADMIN_ID,
                f"⭐ НОВАЯ ОПЛАТА STARS\n\n"
                f"Товар: {item_name}\n"
                f"Сумма: {stars} ⭐\n"
                f"Покупатель: @{msg.from_user.username or '—'} ({msg.from_user.id})\n"
                f"Charge ID: {charge_id}",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=user_link)],
                    [types.InlineKeyboardButton(text="↩️ Вернуть Stars", callback_data=f"refund_stars_{charge_id}_{msg.from_user.id}")],
                ])
            )
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

# ── Мои заказы (Stars) ──
@main_router.callback_query(F.data == "my_stars_orders")
async def my_stars_orders(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT item_name, stars_amount, status, created_at FROM stars_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (cb.from_user.id,))
    orders = c.fetchall(); conn.close()
    if not orders:
        await cb.message.edit_text("📦 У тебя пока нет покупок.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    text = "📦 ТВОИ ПОКУПКИ\n\n"
    status_map = {"paid": "✅ Оплачено", "refunded": "↩️ Возврат", "pending": "⏳ Ожидает"}
    for name, stars, status, created_at in orders:
        dt = str(created_at)[:10]
        text += f"• {name} — {stars}⭐ — {status_map.get(status, status)} ({dt})\n"
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()

# ── Возврат Stars (только для мастера) ──
@admin_router.callback_query(F.data.startswith("refund_stars_"))
async def refund_stars(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    # refund_stars_CHARGEID_USERID  (но charge_id сам может содержать _)
    # Формат: refund_stars_{charge_id}_{user_id} — user_id последний
    user_id = int(parts[-1])
    charge_id = "_".join(parts[2:-1])
    try:
        await bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=charge_id)
        conn = get_db(); c = conn.cursor()
        c.execute("UPDATE stars_orders SET status='refunded' WHERE charge_id=?", (charge_id,))
        conn.commit(); conn.close()
        await cb.answer("✅ Stars возвращены!", show_alert=True)
        # Обновляем кнопки — убираем кнопку возврата
        await cb.message.edit_reply_markup(reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="↩️ Stars возвращены", callback_data="noop")],
        ]))
        # Уведомляем покупателя
        try:
            await bot.send_message(user_id,
                "↩️ Мастер вернул Stars за ваш заказ. Средства зачислены на ваш баланс.")
        except: pass
    except Exception as e:
        await cb.answer(f"❌ Ошибка возврата: {str(e)[:100]}", show_alert=True)

# ── Заглушка для "нажатых" кнопок без действия ──
@main_router.callback_query(F.data == "noop")
async def noop_cb(cb: types.CallbackQuery):
    await cb.answer()



# ═══════════════════════════════════════════════════════════════════════════
# ПРОМОКОДЫ
# ═══════════════════════════════════════════════════════════════════════════

class PromoStates(StatesGroup):
    enter_code = State()
    admin_code = State()
    admin_discount = State()
    admin_uses = State()

@main_router.callback_query(F.data == "enter_promo")
async def enter_promo(cb: types.CallbackQuery, state: FSMContext):
    await safe_edit(cb, "🎟️ Введите промокод:")
    await state.set_state(PromoStates.enter_code)

@main_router.message(PromoStates.enter_code)
async def check_promo(msg: types.Message, state: FSMContext):
    code = msg.text.strip().upper()
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, discount_pct, discount_rub, max_uses, used_count, active FROM promocodes WHERE code=?", (code,))
    promo = c.fetchone()
    if not promo or not promo[5]:
        conn.close(); await state.clear()
        await msg.answer("❌ Промокод не найден или недействителен.")
        return
    pid, dpct, drub, max_uses, used, active = promo
    if max_uses > 0 and used >= max_uses:
        conn.close(); await state.clear()
        await msg.answer("❌ Промокод уже использован максимальное количество раз.")
        return
    # Проверяем использовал ли уже этот юзер
    c.execute("SELECT 1 FROM promo_uses WHERE user_id=? AND code=?", (msg.from_user.id, code))
    if c.fetchone():
        conn.close(); await state.clear()
        await msg.answer("❌ Вы уже использовали этот промокод.")
        return
    conn.close()
    # Сохраняем в state
    await state.update_data(promo_code=code, promo_pct=dpct, promo_rub=drub)
    disc_str = f"{dpct}%" if dpct else f"{drub} руб"
    await msg.answer(
        f"✅ Промокод принят! Скидка: {disc_str}\n\nПромокод будет применён при оформлении заказа.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💎 Перейти в витрину", callback_data="showcase_bracelets")],
            [types.InlineKeyboardButton(text="← В меню", callback_data="menu")],
        ])
    )
    await state.set_state(None)

# Создание промокода (admin)
class PromoAdminStates(StatesGroup):
    code = State()
    discount = State()
    uses = State()

@admin_router.callback_query(F.data == "admin_promos")
async def admin_promos(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT code, discount_pct, discount_rub, used_count, max_uses, active FROM promocodes ORDER BY id DESC LIMIT 10")
    promos = c.fetchall(); conn.close()
    text = "🎟️ ПРОМОКОДЫ\n\n"
    if promos:
        for code, dpct, drub, used, max_u, active in promos:
            disc = f"{dpct}%" if dpct else f"{drub}₽"
            status = "✅" if active else "❌"
            uses_str = f"{used}/{max_u}" if max_u else f"{used}/∞"
            text += f"{status} {code} — {disc} — {uses_str}\n"
    else:
        text += "Промокодов нет"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo_new")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "admin_promo_new")
async def admin_promo_new(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    await safe_edit(cb, "Введите код промокода (например: SUMMER20):")
    await state.set_state(PromoAdminStates.code)
    await cb.answer()

@admin_router.message(PromoAdminStates.code)
async def admin_promo_code(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    code = msg.text.strip().upper()
    await state.update_data(promo_code=code)
    await msg.answer("Скидка: введите число\n• % — например: 15 (15%)\n• Рубли — например: 500р")
    await state.set_state(PromoAdminStates.discount)

@admin_router.message(PromoAdminStates.discount)
async def admin_promo_discount(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    txt = msg.text.strip().lower()
    if 'р' in txt or 'руб' in txt:
        try: drub = int(re.sub(r'[^0-9]', '', txt)); dpct = 0
        except: await msg.answer("Введите число"); return
    else:
        try: dpct = int(re.sub(r'[^0-9]', '', txt)); drub = 0
        except: await msg.answer("Введите число"); return
    await state.update_data(promo_pct=dpct, promo_rub=drub)
    await msg.answer("Максимум использований (0 = безлимит):")
    await state.set_state(PromoAdminStates.uses)

@admin_router.message(PromoAdminStates.uses)
async def admin_promo_uses(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    try: max_uses = int(msg.text.strip())
    except: max_uses = 0
    data = await state.get_data()
    code = data['promo_code']
    dpct = data.get('promo_pct', 0)
    drub = data.get('promo_rub', 0)
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO promocodes (code, discount_pct, discount_rub, max_uses, created_at) VALUES (?,?,?,?,?)",
                  (code, dpct, drub, max_uses, datetime.now()))
        conn.commit(); conn.close()
        disc_str = f"{dpct}%" if dpct else f"{drub} руб"
        await msg.answer(f"✅ Промокод {code} создан!\nСкидка: {disc_str}\nИспользований: {'∞' if not max_uses else max_uses}")
    except Exception as e:
        conn.close()
        await msg.answer(f"❌ Ошибка: {e}")
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ИЗБРАННОЕ (WISHLIST)
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data.startswith("wish_add_"))
async def wish_add(cb: types.CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO wishlist (user_id, item_id, added_at) VALUES (?,?,?)",
                  (cb.from_user.id, item_id, datetime.now()))
        conn.commit(); conn.close()
        await cb.answer("❤️ Добавлено в избранное!", show_alert=False)
    except:
        conn.close()
        await cb.answer("Уже в избранном", show_alert=False)

@main_router.callback_query(F.data.startswith("wish_del_"))
async def wish_del(cb: types.CallbackQuery):
    try:
        item_id = int(cb.data.split("_")[-1])
    except (ValueError, IndexError):
        await cb.answer("Ошибка", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM wishlist WHERE user_id=? AND item_id=?", (cb.from_user.id, item_id))
    conn.commit(); conn.close()
    await cb.answer("Удалено из избранного")
    await my_wishlist(cb)

@main_router.callback_query(F.data == "my_wishlist")
async def my_wishlist(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT wi.item_id, si.name, si.price, si.stars_price
                 FROM wishlist wi JOIN showcase_items si ON wi.item_id=si.id
                 WHERE wi.user_id=? ORDER BY wi.added_at DESC""", (cb.from_user.id,))
    items = c.fetchall(); conn.close()
    if not items:
        await safe_edit(cb, "❤️ Избранное пусто",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💎 Перейти в витрину", callback_data="showcase_bracelets")],
                [types.InlineKeyboardButton(text="← В меню", callback_data="menu")],
            ]))
        await cb.answer(); return
    text = "❤️ ИЗБРАННОЕ\n\n"
    buttons = []
    for item_id, name, price, stars in items:
        price_str = f" — {price:.0f}₽" if price else ""
        stars_str = f" / {stars}⭐" if stars else ""
        text += f"• {name}{price_str}{stars_str}\n"
        buttons.append([
            types.InlineKeyboardButton(text=f"👁 {name[:20]}", callback_data=f"sc_item_{item_id}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"wish_del_{item_id}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="← В меню", callback_data="menu")])
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# FAQ
# ═══════════════════════════════════════════════════════════════════════════

class FaqAdminStates(StatesGroup):
    question = State()
    answer = State()

@main_router.callback_query(F.data == "faq")
async def faq_list(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, question FROM faq WHERE active=1 ORDER BY sort_order, id")
    items = c.fetchall(); conn.close()
    if not items:
        await safe_edit(cb, "❓ FAQ пока пуст. Мастер скоро добавит ответы на частые вопросы.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← В меню", callback_data="menu")]]))
        await cb.answer(); return
    buttons = [[types.InlineKeyboardButton(text=f"❓ {q[:40]}", callback_data=f"faq_item_{fid}")]
               for fid, q in items]
    buttons.append([types.InlineKeyboardButton(text="← В меню", callback_data="menu")])
    await safe_edit(cb, "❓ ЧАСТЫЕ ВОПРОСЫ\n\nВыберите вопрос:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("faq_item_"))
async def faq_item(cb: types.CallbackQuery):
    try: fid = int(cb.data.split("_")[-1])
    except: await cb.answer(); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT question, answer FROM faq WHERE id=?", (fid,))
    item = c.fetchone(); conn.close()
    if not item: await cb.answer("Не найдено"); return
    await safe_edit(cb, f"❓ {item[0]}\n\n💬 {item[1]}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← К вопросам", callback_data="faq")],
            [types.InlineKeyboardButton(text="← В меню", callback_data="menu")],
        ]))
    await cb.answer()

@admin_router.callback_query(F.data == "admin_faq")
async def admin_faq(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, question, active FROM faq ORDER BY sort_order, id")
    items = c.fetchall(); conn.close()
    text = "❓ УПРАВЛЕНИЕ FAQ\n\n"
    buttons = []
    for fid, q, active in items:
        status = "✅" if active else "❌"
        text += f"{status} {q[:50]}\n"
        buttons.append([
            types.InlineKeyboardButton(text=f"{status} {q[:25]}", callback_data=f"faq_toggle_{fid}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"faq_del_{fid}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="faq_add")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    await safe_edit(cb, text or "FAQ пуст", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data == "faq_add")
async def faq_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    await safe_edit(cb, "Введите вопрос:")
    await state.set_state(FaqAdminStates.question)
    await cb.answer()

@admin_router.message(FaqAdminStates.question)
async def faq_save_q(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.update_data(faq_q=msg.text.strip())
    await msg.answer("Введите ответ:")
    await state.set_state(FaqAdminStates.answer)

@admin_router.message(FaqAdminStates.answer)
async def faq_save_a(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO faq (question, answer, created_at) VALUES (?,?,?)",
              (data['faq_q'], msg.text.strip(), datetime.now()))
    conn.commit(); conn.close()
    await state.clear()
    await msg.answer("✅ Вопрос добавлен!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← К FAQ", callback_data="admin_faq")]]))

@admin_router.callback_query(F.data.startswith("faq_del_"))
async def faq_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try: fid = int(cb.data.split("_")[-1])
    except: await cb.answer(); return
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM faq WHERE id=?", (fid,))
    conn.commit(); conn.close()
    await cb.answer("Удалено")
    await admin_faq(cb)

@admin_router.callback_query(F.data.startswith("faq_toggle_"))
async def faq_toggle(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try: fid = int(cb.data.split("_")[-1])
    except: await cb.answer(); return
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE faq SET active = 1 - active WHERE id=?", (fid,))
    conn.commit(); conn.close()
    await cb.answer("Обновлено")
    await admin_faq(cb)

# ═══════════════════════════════════════════════════════════════════════════
# ЗАПИСЬ НА КОНСУЛЬТАЦИЮ
# ═══════════════════════════════════════════════════════════════════════════

class ConsultStates(StatesGroup):
    topic = State()

@main_router.callback_query(F.data == "book_consult")
async def book_consult(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT date, time_slot FROM schedule_slots
                 WHERE available=1 AND date >= DATE('now')
                 ORDER BY date, time_slot LIMIT 12""")
    slots = c.fetchall(); conn.close()
    if not slots:
        await safe_edit(cb, "📅 К сожалению, свободных слотов пока нет.\nНапишите мастеру напрямую.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📞 Написать мастеру", callback_data="contact_master")],
                [types.InlineKeyboardButton(text="← В меню", callback_data="menu")],
            ]))
        await cb.answer(); return
    text = "📅 ЗАПИСЬ НА КОНСУЛЬТАЦИЮ\n\nВыберите удобное время:"
    buttons = [[types.InlineKeyboardButton(
        text=f"📅 {date} в {slot}", callback_data=f"slot_{date}_{slot}")]
        for date, slot in slots]
    buttons.append([types.InlineKeyboardButton(text="← В меню", callback_data="menu")])
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("slot_"))
async def choose_slot(cb: types.CallbackQuery, state: FSMContext):
    parts = cb.data.split("_", 2)
    date, slot = parts[1], parts[2]
    await state.update_data(consult_date=date, consult_slot=slot)
    await safe_edit(cb, f"📅 {date} в {slot}\n\nОпишите коротко тему консультации:")
    await state.set_state(ConsultStates.topic)
    await cb.answer()

@main_router.message(ConsultStates.topic)
async def save_consult(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    date = data['consult_date']
    slot = data['consult_slot']
    conn = get_db(); c = conn.cursor()
    # Резервируем слот
    c.execute("UPDATE schedule_slots SET available=0 WHERE date=? AND time_slot=?", (date, slot))
    c.execute("INSERT INTO consultations (user_id, date, time_slot, topic, created_at) VALUES (?,?,?,?,?)",
              (msg.from_user.id, date, slot, msg.text.strip()[:500], datetime.now()))
    conn.commit()
    # Данные пользователя
    c.execute("SELECT first_name, username FROM users WHERE user_id=?", (msg.from_user.id,))
    u = c.fetchone(); conn.close()
    uname = f"@{u[1]}" if u and u[1] else (u[0] if u else str(msg.from_user.id))
    await state.clear()
    await msg.answer(
        f"✅ Запись подтверждена!\n\n📅 {date} в {slot}\n\nМастер свяжется с вами для подтверждения.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← В меню", callback_data="menu")]]))
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID,
                f"📅 НОВАЯ ЗАПИСЬ НА КОНСУЛЬТАЦИЮ\n\nКлиент: {uname} (id:{msg.from_user.id})\n"
                f"Дата: {date} в {slot}\nТема: {msg.text.strip()[:200]}",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={msg.from_user.id}")],
                    [types.InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"consult_ok_{msg.from_user.id}_{date}_{slot}")],
                    [types.InlineKeyboardButton(text="❌ Отменить", callback_data=f"consult_no_{msg.from_user.id}_{date}_{slot}")],
                ]))
        except: pass

@admin_router.callback_query(F.data.startswith("consult_ok_"))
async def consult_confirm(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    user_id, date, slot = int(parts[2]), parts[3], parts[4]
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE consultations SET status='confirmed' WHERE user_id=? AND date=? AND time_slot=?",
              (user_id, date, slot))
    conn.commit(); conn.close()
    await cb.answer("✅ Подтверждено")
    try:
        await bot.send_message(user_id, f"✅ Мастер подтвердил вашу запись!\n📅 {date} в {slot}\n\nДо встречи!")
    except: pass
    await cb.message.edit_reply_markup(reply_markup=None)

@admin_router.callback_query(F.data.startswith("consult_no_"))
async def consult_cancel(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    parts = cb.data.split("_")
    user_id, date, slot = int(parts[2]), parts[3], parts[4]
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE consultations SET status='cancelled' WHERE user_id=? AND date=? AND time_slot=?",
              (user_id, date, slot))
    c.execute("UPDATE schedule_slots SET available=1 WHERE date=? AND time_slot=?", (date, slot))
    conn.commit(); conn.close()
    await cb.answer("Отменено, слот освобождён")
    try:
        await bot.send_message(user_id, f"❌ К сожалению, мастер не сможет принять вас {date} в {slot}.\nПожалуйста, выберите другое время.")
    except: pass
    await cb.message.edit_reply_markup(reply_markup=None)

# Управление расписанием (admin)
class ScheduleStates(StatesGroup):
    date = State()
    slots = State()

@admin_router.callback_query(F.data == "admin_schedule")
async def admin_schedule(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT date, time_slot, available FROM schedule_slots
                 WHERE date >= DATE('now') ORDER BY date, time_slot LIMIT 20""")
    slots = c.fetchall()
    c.execute("SELECT id, user_id, date, time_slot, topic, status FROM consultations WHERE status='pending' ORDER BY date LIMIT 10")
    consults = c.fetchall(); conn.close()
    text = "⏰ РАСПИСАНИЕ\n\n"
    if slots:
        text += "Слоты:\n"
        for date, slot, avail in slots:
            text += f"{'🟢' if avail else '🔴'} {date} {slot}\n"
    else:
        text += "Слотов нет\n"
    if consults:
        text += "\nЗаписи на консультацию:\n"
        for _, uid, date, slot, topic, status in consults:
            text += f"📅 {date} {slot} — {topic[:30]}\n"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить слоты", callback_data="schedule_add")],
        [types.InlineKeyboardButton(text="🗑 Очистить прошедшие", callback_data="schedule_clean")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "schedule_add")
async def schedule_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    await safe_edit(cb, "Введите дату в формате ДД.ММ.ГГГГ\n(например: 15.03.2025):")
    await state.set_state(ScheduleStates.date)
    await cb.answer()

@admin_router.message(ScheduleStates.date)
async def schedule_date(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    import re as _re
    if not _re.match(r'\d{2}\.\d{2}\.\d{4}', msg.text.strip()):
        await msg.answer("Формат: ДД.ММ.ГГГГ"); return
    d = msg.text.strip()
    parts = d.split('.')
    db_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
    await state.update_data(sched_date=db_date, sched_date_display=d)
    await msg.answer("Введите слоты через запятую\n(например: 10:00, 12:00, 14:00, 16:00):")
    await state.set_state(ScheduleStates.slots)

@admin_router.message(ScheduleStates.slots)
async def schedule_slots_save(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    db_date = data['sched_date']
    slots = [s.strip() for s in msg.text.split(',') if s.strip()]
    conn = get_db(); c = conn.cursor()
    added = 0
    for slot in slots:
        try:
            c.execute("INSERT OR IGNORE INTO schedule_slots (date, time_slot, available) VALUES (?,?,1)",
                      (db_date, slot))
            added += 1
        except: pass
    conn.commit(); conn.close()
    await state.clear()
    await msg.answer(f"✅ Добавлено {added} слотов на {data['sched_date_display']}", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← К расписанию", callback_data="admin_schedule")]]))

@admin_router.callback_query(F.data == "schedule_clean")
async def schedule_clean(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM schedule_slots WHERE date < DATE('now')")
    deleted = c.rowcount
    conn.commit(); conn.close()
    await cb.answer(f"Удалено {deleted} прошедших слотов", show_alert=True)
    await admin_schedule(cb)

# ═══════════════════════════════════════════════════════════════════════════
# CRM — ЗАМЕТКИ ПО КЛИЕНТАМ
# ═══════════════════════════════════════════════════════════════════════════

class CrmStates(StatesGroup):
    note = State()

@admin_router.callback_query(F.data == "admin_crm")
async def admin_crm(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT u.user_id, u.first_name, u.username,
                 COUNT(DISTINCT o.id) as orders,
                 COUNT(DISTINCT n.id) as notes
                 FROM users u
                 LEFT JOIN orders o ON u.user_id=o.user_id
                 LEFT JOIN crm_notes n ON u.user_id=n.user_id
                 GROUP BY u.user_id ORDER BY orders DESC, u.created_at DESC LIMIT 20""")
    users = c.fetchall(); conn.close()
    if not users:
        await safe_edit(cb, "👥 Клиентов нет",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
        await cb.answer(); return
    text = "👥 CRM — КЛИЕНТЫ\n\n"
    buttons = []
    for uid, fname, uname, orders_cnt, notes_cnt in users:
        name = uname and f"@{uname}" or fname or str(uid)
        note_icon = "📋" if notes_cnt else ""
        text_short = f"{name} — {orders_cnt} зак. {note_icon}"
        buttons.append([types.InlineKeyboardButton(text=text_short[:40], callback_data=f"crm_client_{uid}")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("crm_client_"))
async def crm_client(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try: uid = int(cb.data.split("_")[-1])
    except: await cb.answer(); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT first_name, username, created_at FROM users WHERE user_id=?", (uid,))
    u = c.fetchone()
    c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,))
    orders_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM diagnostics WHERE user_id=?", (uid,))
    diag_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM stars_orders WHERE user_id=? AND status='paid'", (uid,))
    stars_cnt = c.fetchone()[0]
    c.execute("SELECT note, created_at FROM crm_notes WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,))
    notes = c.fetchall(); conn.close()
    if not u: await cb.answer("Не найдено"); return
    fname, uname, reg = u
    name = uname and f"@{uname}" or fname or str(uid)
    text = (f"👤 {name}\nID: {uid}\nРег: {str(reg)[:10]}\n\n"
            f"📦 Заказов: {orders_cnt}\n🩺 Диагностик: {diag_cnt}\n⭐ Stars покупок: {stars_cnt}\n")
    if notes:
        text += "\n📋 Заметки:\n"
        for note, nat in notes:
            text += f"• {str(nat)[:10]}: {note[:80]}\n"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 Добавить заметку", callback_data=f"crm_note_{uid}")],
        [types.InlineKeyboardButton(text="✍️ Написать клиенту", url=f"tg://user?id={uid}")],
        [types.InlineKeyboardButton(text="← К списку", callback_data="admin_crm")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("crm_note_"))
async def crm_note_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    try: uid = int(cb.data.split("_")[-1])
    except: await cb.answer(); return
    await state.update_data(crm_uid=uid)
    await safe_edit(cb, "Введите заметку по клиенту:")
    await state.set_state(CrmStates.note)
    await cb.answer()

@admin_router.message(CrmStates.note)
async def crm_note_save(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    uid = data.get('crm_uid')
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO crm_notes (user_id, note, created_at, admin_id) VALUES (?,?,?,?)",
              (uid, msg.text.strip()[:1000], datetime.now(), msg.from_user.id))
    conn.commit(); conn.close()
    await state.clear()
    await msg.answer("✅ Заметка сохранена", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← К клиенту", callback_data=f"crm_client_{uid}")]]))

# ═══════════════════════════════════════════════════════════════════════════
# РАСШИРЕННАЯ СТАТИСТИКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_stats_v2")
async def admin_stats_v2(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    # Пользователи
    c.execute("SELECT COUNT(*) FROM users"); total_u = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at)=DATE('now')"); new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at)>=DATE('now','-7 days')"); new_week = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at)>=DATE('now','-30 days')"); new_month = c.fetchone()[0]
    # Заказы
    c.execute("SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders"); ord_row = c.fetchone()
    total_orders, total_rev = ord_row
    c.execute("SELECT COUNT(*), COALESCE(SUM(total_price),0) FROM orders WHERE DATE(created_at)>=DATE('now','-30 days')")
    month_ord = c.fetchone()
    # Stars
    c.execute("SELECT COUNT(*), COALESCE(SUM(stars_amount),0) FROM stars_orders WHERE status='paid'")
    stars_row = c.fetchone(); stars_cnt, stars_total = stars_row
    # Тест
    c.execute("SELECT COUNT(*) FROM quiz_results"); quiz_cnt = c.fetchone()[0]
    c.execute("SELECT recommended_stone, COUNT(*) as cnt FROM quiz_results GROUP BY recommended_stone ORDER BY cnt DESC LIMIT 3")
    top_stones = c.fetchall()
    # Диагностика
    c.execute("SELECT COUNT(*) FROM diagnostics"); diag_cnt = c.fetchone()[0]
    # Консультации
    c.execute("SELECT COUNT(*) FROM consultations WHERE status='confirmed'"); consult_cnt = c.fetchone()[0]
    # Промокоды
    c.execute("SELECT COUNT(*) FROM promo_uses"); promo_uses = c.fetchone()[0]
    # Корзина
    c.execute("SELECT COUNT(DISTINCT user_id) FROM cart"); cart_users = c.fetchone()[0]
    # FAQ популярность — нет счётчика, но знаем сколько вопросов
    c.execute("SELECT COUNT(*) FROM faq WHERE active=1"); faq_cnt = c.fetchone()[0]
    # Рост по дням (последние 7)
    c.execute("""SELECT DATE(created_at), COUNT(*) FROM users
                 WHERE DATE(created_at) >= DATE('now','-7 days')
                 GROUP BY DATE(created_at) ORDER BY DATE(created_at)""")
    daily = c.fetchall(); conn.close()

    text = (f"📊 СТАТИСТИКА v2\n\n"
            f"👥 ПОЛЬЗОВАТЕЛИ\n"
            f"Всего: {total_u}  |  Сегодня: +{new_today}  |  7д: +{new_week}  |  30д: +{new_month}\n\n"
            f"📦 ЗАКАЗЫ\n"
            f"Всего: {total_orders}  |  Выручка: {total_rev:.0f}₽\n"
            f"За 30 дней: {month_ord[0]} зак. / {month_ord[1]:.0f}₽\n\n"
            f"⭐ STARS ОПЛАТЫ\n"
            f"Покупок: {stars_cnt}  |  Итого: {stars_total}⭐\n\n"
            f"🔮 ТЕСТ КАМНЯ\n"
            f"Пройдено: {quiz_cnt}\n")
    if top_stones:
        text += "Топ камней: " + ", ".join(f"{s} ({c})" for s, c in top_stones) + "\n"
    text += (f"\n🩺 Диагностик: {diag_cnt}\n"
             f"📅 Консультаций: {consult_cnt}\n"
             f"🎟️ Промокодов использовано: {promo_uses}\n"
             f"🛒 Активных корзин: {cart_users}\n"
             f"❓ FAQ вопросов: {faq_cnt}\n")
    if daily:
        text += "\n📈 Рост по дням:\n"
        for date, cnt in daily:
            bar = "█" * min(cnt, 10)
            text += f"{str(date)[5:]} {bar} {cnt}\n"
    await safe_edit(cb, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# НАПОМИНАНИЕ О БРОШЕННОЙ КОРЗИНЕ
# ═══════════════════════════════════════════════════════════════════════════

async def send_cart_reminders():
    """Фоновая задача — раз в час проверяет брошенные корзины."""
    while True:
        await asyncio.sleep(3600)
        try:
            conn = get_db(); c = conn.cursor()
            # Пользователи с корзиной которым не отправляли напоминание
            c.execute("""SELECT DISTINCT cart.user_id FROM cart
                         LEFT JOIN cart_reminders cr ON cart.user_id=cr.user_id
                         WHERE cr.user_id IS NULL
                         OR (cr.reminded=0 AND 
                             CAST((JULIANDAY('now') - JULIANDAY(cart.added_at))*24 AS INT) >= 2)""")
            users = [r[0] for r in c.fetchall()]
            for uid in users:
                try:
                    c.execute("SELECT COUNT(*) FROM cart WHERE user_id=?", (uid,))
                    cnt = c.fetchone()[0]
                    if cnt == 0: continue
                    await bot.send_message(uid,
                        f"🛒 Вы оставили {cnt} товар(а) в корзине!\n\n"
                        f"Хотите завершить покупку? 😊",
                        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                            [types.InlineKeyboardButton(text="🛒 Перейти в корзину", callback_data="view_cart")],
                            [types.InlineKeyboardButton(text="💎 В витрину", callback_data="showcase_bracelets")],
                        ]))
                    c.execute("INSERT OR REPLACE INTO cart_reminders (user_id, last_reminder, reminded) VALUES (?,?,1)",
                              (uid, datetime.now()))
                    conn.commit()
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════
# ПОДПИСКА НА НОВЫЕ ТОВАРЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "subscribe_new")
async def subscribe_new(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM new_item_subscribers WHERE user_id=?", (cb.from_user.id,))
    already = c.fetchone()
    if already:
        c.execute("DELETE FROM new_item_subscribers WHERE user_id=?", (cb.from_user.id,))
        conn.commit(); conn.close()
        await cb.answer("🔕 Вы отписались от уведомлений о новых товарах", show_alert=True)
    else:
        c.execute("INSERT OR IGNORE INTO new_item_subscribers (user_id, subscribed_at) VALUES (?,?)",
                  (cb.from_user.id, datetime.now()))
        conn.commit(); conn.close()
        await cb.answer("🔔 Подписка оформлена! Вы первыми узнаете о новых браслетах", show_alert=True)

@admin_router.callback_query(F.data == "admin_notify_new")
async def admin_notify_new(cb: types.CallbackQuery):
    """Уведомить подписчиков о новом товаре последней добавленном."""
    if not is_admin(cb.from_user.id): await cb.answer("❌"); return
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT si.id, si.name, si.desc, si.price, sc.name as col_name
                 FROM showcase_items si JOIN showcase_collections sc ON si.collection_id=sc.id
                 ORDER BY si.created_at DESC LIMIT 1""")
    item = c.fetchone()
    if not item: await cb.answer("Нет товаров", show_alert=True); conn.close(); return
    c.execute("SELECT user_id FROM new_item_subscribers")
    subs = [r[0] for r in c.fetchall()]; conn.close()
    iid, iname, idesc, iprice, colname = item
    price_str = f"\n💰 Цена: {iprice:.0f}₽" if iprice else ""
    text = (f"🆕 НОВЫЙ БРАСЛЕТ В КОЛЛЕКЦИИ «{colname}»!\n\n"
            f"💎 {iname}\n{idesc or ''}{price_str}\n\n"
            f"Смотреть и купить 👇")
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💎 Смотреть", callback_data=f"sc_item_{iid}")]])
    sent = 0
    for uid in subs:
        try:
            await bot.send_message(uid, text, reply_markup=kb)
            sent += 1
            await asyncio.sleep(0.05)
        except: pass
    await cb.answer(f"Отправлено {sent} из {len(subs)} подписчикам", show_alert=True)


@main_router.message(StateFilter(None))
async def handle_any(msg: types.Message):
    await msg.answer("❓ Команды:\n/start - меню\n/admin - админ-панель\n/diagnostics - диагностика")

# ═══════════════════════════════════════════════════════════════════════════
# ВЕБХУК
# ═══════════════════════════════════════════════════════════════════════════

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
    print("\n" + "="*60 + "\n")
    
    # Запуск polling
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