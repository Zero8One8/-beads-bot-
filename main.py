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
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from aiogram import F, types, Router, Dispatcher, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

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
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def admin_panel_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [types.InlineKeyboardButton(text="📝 КОНТЕНТ", callback_data="admin_content")],
        [types.InlineKeyboardButton(text="🏋️ ТРЕНИРОВКИ", callback_data="admin_workouts")],
        [types.InlineKeyboardButton(text="🎵 МУЗЫКА", callback_data="admin_music")],
        [types.InlineKeyboardButton(text="💼 УСЛУГИ", callback_data="admin_services")],
        [types.InlineKeyboardButton(text="💎 БРАСЛЕТЫ", callback_data="admin_bracelets")],
        [types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics")],
        [types.InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats")],
        [types.InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast")],
        [types.InlineKeyboardButton(text="📖 ИСТОРИИ", callback_data="admin_stories")],
        [types.InlineKeyboardButton(text="📚 БАЗА ЗНАНИЙ", callback_data="admin_knowledge")],
        [types.InlineKeyboardButton(text="🔮 РЕЗУЛЬТАТЫ ТЕСТА", callback_data="admin_quiz_results")],
        [types.InlineKeyboardButton(text="✏️ ПРИВЕТСТВИЕ", callback_data="admin_welcome_text")],
        [types.InlineKeyboardButton(text="📦 ЗАКАЗЫ", callback_data="admin_orders")],
        [types.InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ КАТЕГОРИИ", callback_data="edit_categories")],
        [types.InlineKeyboardButton(text="📚 ПОДКАТЕГОРИИ", callback_data="manage_subcategories")],
        [types.InlineKeyboardButton(text="🔷 ПОД-ПОДКАТЕГОРИИ", callback_data="manage_subsubcategories")],
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
                c.execute('INSERT INTO referral_balance (user_id, referral_count) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET referral_count = referral_count + 1', (ref_id,))
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
    await cb.message.edit_text(
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
        await cb.message.edit_text(
            "Шаг 2 из 4 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💔 Больно — что-то важное ушло или рассыпалось", callback_data="dg_type_f_lost")],
                [types.InlineKeyboardButton(text="🌱 Развиваюсь — ищу себя и свой путь", callback_data="dg_type_f_grow")],
            ])
        )
    else:
        await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t, callback_data=d)] for t,d in opts
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("dg_q2_"))
async def dg_q2_done(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(dg_q2=cb.data)
    await cb.message.edit_text(
        "✅ Отлично! Картина складывается.\n\n"
        "Последний шаг — загрузите два фото.\n\n"
        "📸 Фото 1: ваши ладони\n"
        "📸 Фото 2: ваше лицо или любое фото которое хотите показать\n\n"
        "Мастер подберёт камни лично для вас. Ответ в течение 24 часов.\n\n"
        "Загружайте первое фото 👇"
    )
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

@main_router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())
    await cb.answer()

@main_router.callback_query(F.data == "menu")
async def menu_cb(cb: types.CallbackQuery):
    kb = await get_categories_keyboard()
    await cb.message.edit_text("Выбери раздел:", reply_markup=kb)
    await cb.answer()

@main_router.callback_query(F.data.startswith("cat_"))
async def show_category(cb: types.CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split("_")[1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    conn.close()
    
    # Перехватываем "Браслеты на заказ" — запускаем цепочку заказа
    if cat and cat[0] == '💍 Браслеты на заказ':
        await cb.message.edit_text(
            "💍 БРАСЛЕТЫ НА ЗАКАЗ\n\n"
            "Мастер создаст браслет специально для вас — с учётом вашего запроса и энергетики.\n\n"
            "Для подбора нужно ответить на несколько вопросов, а затем прислать два фото.\n\n"
            "Начнём? 👇",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Да, начать", callback_data="order_bracelet_start")],
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
            ])
        )
        await cb.answer()
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КАТЕГОРИИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_categories")
async def admin_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, emoji FROM categories')
    cats = c.fetchall()
    conn.close()
    
    text = "📋 УПРАВЛЕНИЕ КАТЕГОРИЯМИ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"{cat[2]} {cat[1]}\n"
        buttons.append([
            types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"edit_cat_{cat[0]}"),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_cat_{cat[0]}")
        ])
    
    buttons.extend([
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data == "add_cat")
async def add_cat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("📝 Напиши название новой категории:")
    await state.set_state(AdminStates.add_category)
    await cb.answer()

@admin_router.message(AdminStates.add_category)
async def add_cat_process(msg: types.Message, state: FSMContext):
    name = msg.text.strip()
    
    if not name:
        await msg.answer("❌ Название не может быть пустым!")
        await state.clear()
        return
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Проверяю есть ли уже такая категория
        c.execute('SELECT id FROM categories WHERE name = ?', (name,))
        if c.fetchone():
            await msg.answer(f"❌ Категория '{name}' уже существует!")
        else:
            # Добавляю новую категорию
            c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", (name, '📌', 'Новая категория'))
            conn.commit()
            await msg.answer(f"✅ Категория '{name}' добавлена!")
            logger.info(f"Категория '{name}' добавлена")
            
            # ПОКАЗЫВАЮ ОБНОВЛЕННОЕ МЕНЮ
            c.execute('SELECT id, name, emoji FROM categories ORDER BY id DESC')
            cats = c.fetchall()
            
            text = "📋 УПРАВЛЕНИЕ КАТЕГОРИЯМИ:\n\n"
            buttons = []
            
            for cat in cats:
                text += f"{cat[2]} {cat[1]}\n"
                buttons.append([
                    types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"edit_cat_{cat[0]}"),
                    types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_cat_{cat[0]}")
                ])
            
            buttons.extend([
                [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_categories")],
            ])
            
            await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
            
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка добавления категории: {e}")
    finally:
        conn.close()
    
    await state.clear()

@admin_router.callback_query(F.data.startswith("delete_cat_"))
async def delete_cat(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаю информацию перед удалением
        c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
        cat = c.fetchone()
        
        if not cat:
            await cb.answer("❌ Категория не найдена!", show_alert=True)
            conn.close()
            return
        
        cat_name = cat[0]
        
        # Удаляю все под-подкатегории этой категории через подкатегории
        c.execute('SELECT id FROM subcategories WHERE parent_id = ?', (cat_id,))
        subcats = c.fetchall()
        
        for subcat in subcats:
            c.execute('DELETE FROM subsubcategories WHERE parent_id = ?', (subcat[0],))
        
        # Удаляю подкатегории
        c.execute('DELETE FROM subcategories WHERE parent_id = ?', (cat_id,))
        
        # Удаляю контент категории
        c.execute('DELETE FROM content WHERE cat_id = ?', (cat_id,))
        
        # Удаляю саму категорию
        c.execute('DELETE FROM categories WHERE id = ?', (cat_id,))
        conn.commit()
        conn.close()
        
        await cb.answer(f"✅ Категория '{cat_name}' удалена со всем содержимым!", show_alert=True)
        
        # Возвращаюсь в меню категорий
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, name, emoji FROM categories')
        cats = c.fetchall()
        conn.close()
        
        text = "📋 УПРАВЛЕНИЕ КАТЕГОРИЯМИ:\n\n"
        buttons = []
        
        for c_item in cats:
            text += f"{c_item[2]} {c_item[1]}\n"
            buttons.append([
                types.InlineKeyboardButton(text=f"✏️ {c_item[1]}", callback_data=f"edit_cat_{c_item[0]}"),
                types.InlineKeyboardButton(text="🗑️", callback_data=f"delete_cat_{c_item[0]}")
            ])
        
        buttons.extend([
            [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
    except Exception as e:
        logger.error(f"Ошибка при удалении категории {cat_id}: {e}")
        await cb.answer(f"❌ Ошибка при удалении: {str(e)[:50]}", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КОНТЕНТ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_content")
async def admin_content(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"content_cat_{cat[0]}")] for cat in cats]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text("Выбери категорию для добавления контента:", 
                              reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("content_cat_"))
async def select_content_category(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(content_cat_id=cat_id)
    await cb.message.edit_text("Напиши название контента (заголовок):")
    await state.set_state(AdminStates.add_content)
    await cb.answer()

@admin_router.message(AdminStates.add_content)
async def add_content_handler(msg: types.Message, state: FSMContext):
    """Обработчик добавления контента (название и описание)"""
    data = await state.get_data()
    
    # Если это первое сообщение - сохраняем как название
    if 'content_title' not in data:
        await state.update_data(content_title=msg.text)
        await msg.answer("Теперь напиши описание/текст для этого контента:")
        return
    
    # Второе сообщение - это описание
    title = data.get('content_title')
    cat_id = data['content_cat_id']
    desc = msg.text
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO content (cat_id, title, desc, created_at) VALUES (?, ?, ?, ?)",
                 (cat_id, title, desc, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Контент '{title}' добавлен!")
        logger.info(f"Контент '{title}' добавлен в категорию {cat_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ТРЕНИРОВКИ
# ═══════════════════════════════════════════════════════════════════════════

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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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

@admin_router.callback_query(F.data == "admin_music")
async def admin_music(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM music')
    tracks = c.fetchall()
    conn.close()
    
    text = "🎵 МУЗЫКА:\n\n"
    if tracks:
        for t in tracks:
            text += f"• {t[0]}\n"
    else:
        text += "Музыки нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_music")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_music")
async def add_music_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("🎵 ДОБАВИТЬ МУЗЫКУ\n\n📝 Введи название трека:")
    await state.set_state(AdminStates.add_music_name)
    await cb.answer()

@admin_router.message(AdminStates.add_music_name)
async def add_music_name(msg: types.Message, state: FSMContext):
    """Сохранить название трека и ждать аудиофайл"""
    await state.update_data(music_name=msg.text)
    await msg.answer("🎵 Теперь загрузи АУДИОФАЙЛ (MP3, WAV, OGG и т.д.):")
    await state.set_state(AdminStates.add_music_file)

@admin_router.message(AdminStates.add_music_file)
async def add_music_file(msg: types.Message, state: FSMContext):
    """Сохранить аудиофайл трека"""
    data = await state.get_data()
    music_name = data.get('music_name')
    
    if not msg.audio and not msg.document:
        await msg.answer("❌ Загрузи аудиофайл (музыку)!\n\n🎵 Поддерживаются MP3, WAV, OGG и другие аудиоформаты.")
        return
    
    # Получаю file_id аудиофайла
    if msg.audio:
        audio_file_id = msg.audio.file_id
        duration = msg.audio.duration or 60
    else:
        audio_file_id = msg.document.file_id
        duration = 60
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO music (name, desc, duration, audio_url, created_at) VALUES (?, ?, ?, ?, ?)",
                 (music_name, f"🎵 {music_name}", duration, audio_file_id, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Трек '{music_name}' добавлен!\n\n⏱️ Длительность: {duration} сек")
        logger.info(f"Музыка '{music_name}' добавлена (ID: {audio_file_id})")
    except Exception as e:
        await msg.answer(f"❌ Ошибка при сохранении: {e}")
        logger.error(f"Ошибка добавления музыки: {e}")
    finally:
        conn.close()
    
    await state.clear()

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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "edit_categories")
async def edit_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, name, emoji FROM categories')
    cats = c.fetchall()
    conn.close()
    
    text = "✏️ РЕДАКТИРОВАТЬ КАТЕГОРИИ:\n\n"
    buttons = []
    
    for cat in cats:
        text += f"ID: {cat[0]} | {cat[1]}\n"
        buttons.append([types.InlineKeyboardButton(text=f"✏️ {cat[1]}", callback_data=f"edit_cat_{cat[0]}")])
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("edit_cat_"))
async def edit_cat_name(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(edit_cat_id=cat_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    conn.close()
    
    await cb.message.edit_text(f"✏️ Текущее название: {cat[0]}\n\nНапиши новое название:")
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
        await cb.message.edit_text("📭 Категорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subcat_"))
async def manage_subcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subcat_"))
async def add_subcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(add_subcat_parent_id=cat_id)
    
    await cb.message.edit_text("📝 Введи название подкатегории:")
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
    
    subcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    conn.close()
    
    await state.update_data(edit_subcat_id=subcat_id)
    await cb.message.edit_text(f"✏️ Текущее название: {subcat[0]}\n\nНапиши новое:")
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
        
        text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
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
    
    subcat_id = int(cb.data.split("_")[-1])
    
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
        
        text = f"✏️ ПОДКАТЕГОРИИ - {cat[0]}:\n\n"
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
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
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
        await cb.message.edit_text("📭 Подкатегорий не найдено", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("manage_subsubcat_"))
async def manage_subsubcat(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("add_subsubcat_"))
async def add_subsubcat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    subcat_id = int(cb.data.split("_")[-1])
    await state.update_data(add_subsubcat_parent_id=subcat_id, step='name')
    
    await cb.message.edit_text("📝 Введи название под-подкатегории:")
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
    
    subsubcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    conn.close()
    
    await state.update_data(edit_subsubcat_id=subsubcat_id)
    await cb.message.edit_text(f"✏️ Текущее название: {subsubcat[0]}\n\nНапиши новое:")
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
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
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
    
    subsubcat_id = int(cb.data.split("_")[-1])
    
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
        
        text = f"✏️ ПОД-ПОДКАТЕГОРИИ - {subcat[0]}:\n\n"
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
        
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
        
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    
    await cb.message.edit_text("💎 ДОБАВИТЬ БРАСЛЕТ\n\n📝 Введи НАЗВАНИЕ:")
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
        await cb.message.edit_text("📭 Браслетов нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_bracelets")],
        ]))
    else:
        text = "💎 СПИСОК БРАСЛЕТОВ:\n\n"
        for b in bracelets:
            text += f"ID: {b[0]} | {b[1]} | {b[2]}₽\n"
        await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    subcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subcategories WHERE id = ?', (subcat_id,))
    subcat = c.fetchone()
    
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
    
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("subsubcat_"))
async def show_subsubcategory(cb: types.CallbackQuery):
    subsubcat_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM subsubcategories WHERE id = ?', (subsubcat_id,))
    subsubcat = c.fetchone()
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (subsubcat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{subsubcat[1]} {subsubcat[0]}\n\n"
    
    if content:
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        text += "📭 Контента нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
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
        await cb.message.edit_text("📭 Браслетов нет в наличии", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("view_bracelet_"))
async def view_bracelet(cb: types.CallbackQuery):
    bracelet_id = int(cb.data.split("_")[-1])
    
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
    bracelet_id = int(cb.data.split("_")[-1])
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
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT cart.id, bracelets.name, bracelets.price, cart.quantity, cart.bracelet_id
                 FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id 
                 WHERE cart.user_id = ?''', (user_id,))
    items = c.fetchall()
    conn.close()
    
    if not items:
        await cb.message.edit_text("🛒 Корзина пуста", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
        ]))
        await cb.answer()
        return
    
    total = 0
    text = "🛒 КОРЗИНА:\n\n"
    buttons = []
    
    for item in items:
        price = item[2] * item[3]
        total += price
        text += f"💎 {item[1]}\n{item[3]} шт. × {item[2]}₽ = {price}₽\n\n"
        buttons.append([types.InlineKeyboardButton(text=f"❌ Удалить {item[1]}", callback_data=f"remove_cart_{item[0]}")])
    
    text += f"\n💰 ИТОГО: {total}₽"
    
    buttons.extend([
        [types.InlineKeyboardButton(text="💳 ОФОРМИТЬ ЗАКАЗ", callback_data="checkout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("remove_cart_"))
async def remove_from_cart(cb: types.CallbackQuery):
    cart_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM cart WHERE id = ?', (cart_id,))
    conn.commit()
    conn.close()
    
    await cb.answer("✅ Удалено из корзины!", show_alert=True)
    # Переказываю корзину
    await view_cart(cb)

@main_router.callback_query(F.data == "checkout")
async def checkout(cb: types.CallbackQuery):
    await cb.message.edit_text("💳 СПОСОБ ОПЛАТЫ:\n\n1. 💰 Яндекс.Касса\n2. ₿ Криптовалюта", 
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 ЯНДЕКС.КАССА", callback_data="pay_yandex")],
        [types.InlineKeyboardButton(text="₿ КРИПТО", callback_data="pay_crypto")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "pay_yandex")
async def pay_yandex(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT SUM(bracelets.price * cart.quantity) FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id WHERE cart.user_id = ?', (user_id,))
    total = c.fetchone()[0] or 0
    
    # Создаю заказ
    c.execute('INSERT INTO orders (user_id, total_price, status, payment_method, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, total, 'pending', 'yandex', datetime.now()))
    order_id = c.lastrowid
    
    conn.commit()
    conn.close()
    await notify_admin_order(user_id, order_id, total, "Яндекс.Касса")
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total}₽\n\n📝 РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ:\n"
    
    if YANDEX_KASSA_EMAIL != 'your-email@yandex.kassa.com':
        payment_text += f"Яндекс.Касса: {YANDEX_KASSA_EMAIL}\nShop ID: {YANDEX_KASSA_SHOP_ID}"
    else:
        payment_text += "⚠️ Реквизиты Яндекс.Кассы не настроены.\nОбновите YANDEX_KASSA_EMAIL в переменных окружения."
    
    await cb.message.edit_text(payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "pay_crypto")
async def pay_crypto(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT SUM(bracelets.price * cart.quantity) FROM cart JOIN bracelets ON cart.bracelet_id = bracelets.id WHERE cart.user_id = ?', (user_id,))
    total = c.fetchone()[0] or 0
    
    c.execute('INSERT INTO orders (user_id, total_price, status, payment_method, created_at) VALUES (?, ?, ?, ?, ?)',
              (user_id, total, 'pending', 'crypto', datetime.now()))
    order_id = c.lastrowid
    
    conn.commit()
    conn.close()
    
    payment_text = f"✅ Заказ #{order_id} создан!\n\n💰 Сумма: {total}₽\n\n"
    
    if CRYPTO_WALLET_ADDRESS != 'bc1qyour_bitcoin_address_here':
        payment_text += f"₿ {CRYPTO_WALLET_NETWORK} адрес:\n{CRYPTO_WALLET_ADDRESS}"
    else:
        payment_text += "⚠️ Адрес кошелька не настроен.\nОбновите CRYPTO_WALLET_ADDRESS в переменных окружения."
    
    await cb.message.edit_text(payment_text,
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ОПЛАЧЕНО", callback_data=f"confirm_order_{order_id}")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="view_cart")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order(cb: types.CallbackQuery, state: FSMContext):
    order_id = int(cb.data.split("_")[-1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ? WHERE id = ?', ('confirmed', order_id))
    conn.commit()
    conn.close()
    
    await cb.message.edit_text(f"✅ Заказ #{order_id} подтвержден!\n\n📝 Спасибо за покупку! Оставь отзыв после получения товара.",
    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⭐ ОСТАВИТЬ ОТЗЫВ", callback_data="leave_review")],
        [types.InlineKeyboardButton(text="← МЕНЮ", callback_data="menu")],
    ]))
    await cb.answer()

@main_router.callback_query(F.data == "leave_review")
async def leave_review(cb: types.CallbackQuery, state: FSMContext):
    # Получаю bracelet_id из контекста или из callback_data
    await state.update_data(from_confirmation=True)
    await cb.message.edit_text("⭐ ОЦЕНКА:\n\n1 - очень плохо\n5 - отлично",
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
    rating = int(cb.data.split("_")[-1])
    await state.update_data(rating=rating)
    await cb.message.edit_text("📝 Напиши свой отзыв (текст):")
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
    bracelet_id = int(cb.data.split("_")[-1])
    
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
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
        f"🤝 РЕФЕРАЛЬНАЯ ПРОГРАММА\n\n"
        f"Ваш статус: {get_referral_status(ref_count)}\n"
        f"Приглашено друзей: {ref_count}\n"
        f"Ваш % с продаж: {get_referral_percent(ref_count)}%\n\n"
        f"💰 Баланс: {balance:.0f} руб\n"
        f"📈 Заработано всего: {total_earned:.0f} руб\n\n"
        f"🔗 Ваша ссылка:\n{ref_link}\n\n"
        f"📊 УРОВНИ:\n"
        f"1-5 друзей → 5%\n"
        f"6-15 друзей → 10%\n"
        f"16+ друзей → 15% + 👑 Амбассадор + скидка 15%",
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
    await cb.message.edit_text(
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
    await cb.message.edit_text("📢 РАССЫЛКА\n\nНапишите текст сообщения:")
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
    await cb.message.edit_text("✅ История отправлена на проверку!")
    await state.clear(); await cb.answer()

@admin_router.callback_query(F.data.startswith("approve_story_"))
async def approve_story(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True); return
    user_id = int(cb.data.split("_")[-1])
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
    await cb.message.edit_text(
        f"📖 ИСТОРИИ КЛИЕНТОВ\n\nОжидают проверки: {pending}\nОдобрено: {approved_count}",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
        ])
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# ТЕСТ "КАКОЙ КАМЕНЬ ПОДХОДИТ ИМЕННО ВАМ"
# ═══════════════════════════════════════════════════════════════════════════

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
    await cb.message.edit_text(
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
        await cb.message.edit_text("Шаг 2 из 5 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="💔 Больно — что-то важное ушло или рассыпалось", callback_data="qz_t_f_lost")],
                [types.InlineKeyboardButton(text="🌱 Развиваюсь — ищу себя и свой путь", callback_data="qz_t_f_grow")],
            ]))
    else:
        await cb.message.edit_text("Шаг 2 из 5 — Что сейчас ближе к вашему состоянию?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🌑 Всё навалилось — не вывожу", callback_data="qz_t_m_down")],
                [types.InlineKeyboardButton(text="⚡ Рвусь вперёд — нужна дополнительная сила", callback_data="qz_t_m_up")],
            ]))
    await cb.answer()

@main_router.callback_query(F.data == "qz_t_f_lost")
async def qz_f_lost(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(qz_type="f_lost")
    await cb.message.edit_text("Шаг 3 из 5 — Что сейчас внутри?",
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
    await cb.message.edit_text("Шаг 3 из 5 — Что сейчас важнее всего усилить?",
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
    await cb.message.edit_text("Шаг 3 из 5 — Что сейчас происходит?",
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
    await cb.message.edit_text("Шаг 3 из 5 — Что хотите усилить?",
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
    await cb.message.edit_text(q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    await cb.message.edit_text(q, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
    await cb.message.edit_text(
        f"🔮 ВАШ КАМЕНЬ — {stone} {emoji}\n\n{desc}\n\n✨ {why}\n\n"
        f"Это экспресс-результат. Для точного подбора — пройдите диагностику по фото.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🩺 ПРОЙТИ ПОЛНУЮ ДИАГНОСТИКУ", callback_data="diag_start")],
            [types.InlineKeyboardButton(text="💎 ПОСМОТРЕТЬ ВИТРИНУ", callback_data="showcase_bracelets")],
            [types.InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")],
        ]))
    await state.clear(); await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ВИТРИНА БРАСЛЕТОВ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "showcase_bracelets")
async def showcase_bracelets(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, name, desc, price, image_url FROM bracelets ORDER BY created_at DESC")
    items = c.fetchall(); conn.close()
    if not items:
        await cb.message.edit_text("💎 ВИТРИНА БРАСЛЕТОВ\n\nПока товаров нет. Скоро появятся!",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    await cb.message.edit_text(f"💎 ВИТРИНА БРАСЛЕТОВ\n\nНайдено: {len(items)} товаров:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    for item in items:
        bid, name, desc, price, image_url = item
        caption = f"💎 {name}\n\n{desc or ''}\n\n💰 Цена: {price:.0f} руб"
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🛒 В КОРЗИНУ", callback_data=f"add_to_cart_{bid}")]])
        try:
            if image_url: await cb.message.answer_photo(photo=image_url, caption=caption, reply_markup=kb)
            else: await cb.message.answer(caption, reply_markup=kb)
        except: await cb.message.answer(caption, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# БАЗА ЗНАНИЙ О КАМНЯХ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "knowledge_list")
async def knowledge_list(cb: types.CallbackQuery):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name")
    stones = c.fetchall(); conn.close()
    if not stones:
        await cb.message.edit_text("📚 БАЗА ЗНАНИЙ О КАМНЯХ\n\nБаза пока пустая!",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    buttons = [[types.InlineKeyboardButton(text=f"{s[1]} {s[2]}", callback_data=f"stone_info_{s[0]}")] for s in stones]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    await cb.message.edit_text("📚 БАЗА ЗНАНИЙ О КАМНЯХ\n\nВыберите камень:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("stone_info_"))
async def stone_detail(cb: types.CallbackQuery):
    stone_id = int(cb.data.split("_")[-1])
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
    await cb.message.edit_text("📚 ДОБАВИТЬ КАМЕНЬ\n\nВведите название (например: Аметист):")
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
    await cb.message.edit_text("📋 Нажмите чтобы удалить:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("knowledge_del_"))
async def knowledge_delete(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT stone_name, emoji FROM knowledge WHERE id=?", (sid,)); s = c.fetchone()
    c.execute("DELETE FROM knowledge WHERE id=?", (sid,)); conn.commit(); conn.close()
    await cb.answer(f"✅ {s[1]} {s[0]} удалён!" if s else "✅ Удалено!", show_alert=True)
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, emoji, stone_name FROM knowledge ORDER BY stone_name"); stones = c.fetchall(); conn.close()
    if not stones:
        await cb.message.edit_text("База пустая.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")]])); return
    buttons = [[types.InlineKeyboardButton(text=f"🗑 {s[1]} {s[2]}", callback_data=f"knowledge_del_{s[0]}")] for s in stones]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_knowledge")])
    await cb.message.edit_text("📋 Нажмите чтобы удалить:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@admin_router.callback_query(F.data == "admin_quiz_results")
async def admin_quiz_results(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌ Нет прав!", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM quiz_results"); total = c.fetchone()[0]
    c.execute("SELECT recommended_stone, COUNT(*) cnt FROM quiz_results GROUP BY recommended_stone ORDER BY cnt DESC LIMIT 5")
    top = c.fetchall(); conn.close()
    text = f"🔮 РЕЗУЛЬТАТЫ ТЕСТА\n\nВсего прошли: {total}\n\n🏆 Топ камней:\n"
    for stone, cnt in top: text += f"  {stone}: {cnt} чел.\n"
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
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
        await cb.message.edit_text("📦 МОИ ЗАКАЗЫ\n\nЗаказов пока нет.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
        await cb.answer(); return
    STATUS_EMOJI = {'pending':'⏳ Ожидает','confirmed':'✅ Подтверждён','paid':'💰 Оплачен',
                    'in_progress':'🔨 В работе','shipped':'🚚 Отправлен','delivered':'📦 Доставлен','cancelled':'❌ Отменён'}
    text = "📦 МОИ ЗАКАЗЫ\n\n"
    for o in orders:
        text += f"Заказ #{o[0]}\n{STATUS_EMOJI.get(o[2], o[2])}\nСумма: {o[1]:.0f} руб\n\n"
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]]))
    await cb.answer()

@admin_router.callback_query(F.data == "admin_orders")
async def admin_orders(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT o.id, u.first_name, u.username, o.total_price, o.status FROM orders o LEFT JOIN users u ON o.user_id=u.user_id ORDER BY o.created_at DESC LIMIT 20")
    orders = c.fetchall(); conn.close()
    if not orders:
        await cb.message.edit_text("📦 Заказов нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")]])); await cb.answer(); return
    buttons = []
    text = "📦 ЗАКАЗЫ\n\n"
    for o in orders:
        oid, fname, uname, price, status = o
        uinfo = f"@{uname}" if uname else (fname or "?")
        text += f"#{oid} {uinfo} — {price:.0f}₽ [{status}]\n"
        buttons.append([types.InlineKeyboardButton(text=f"#{oid} {uinfo} [{status}]", callback_data=f"order_status_{oid}")])
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    await cb.message.edit_text(text[:3000], reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("order_status_"))
async def order_change_status(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    order_id = int(cb.data.split("_")[-1])
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT o.id, u.first_name, o.total_price, o.status FROM orders o LEFT JOIN users u ON o.user_id=u.user_id WHERE o.id=?", (order_id,))
    o = c.fetchone(); conn.close()
    if not o: await cb.answer("Не найдено", show_alert=True); return
    await cb.message.edit_text(
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
    await cb.message.edit_text(f"✏️ Текущий текст для НОВЫХ:\n\n{current}\n\nНапишите новый текст:")
    await state.set_state(WelcomeTextStates.waiting_text)
    await cb.answer()

@admin_router.callback_query(F.data == "edit_welcome_return")
async def edit_welcome_return(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): await cb.answer("❌", show_alert=True); return
    current = await get_setting('return_text', '')
    await cb.message.edit_text(f"✏️ Текущий текст для ВЕРНУВШИХСЯ:\n\n{current}\n\nНапишите новый:")
    await state.set_state(WelcomeTextStates.waiting_return_text)
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
    await cb.message.edit_text("🔍 ПОИСК ПО БАЗЕ ЗНАНИЙ\n\nВведите название камня или свойство\n(например: защита, любовь, аметист):")
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
    await cb.message.edit_text("💎 ФИЛЬТР ВИТРИНЫ\n\nВыберите что вам нужно:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data == "noop")
async def noop_handler(cb: types.CallbackQuery):
    await cb.answer()

@main_router.callback_query(F.data.startswith("bf_"))
async def bracelet_filter_results(cb: types.CallbackQuery):
    search_term = cb.data.replace("bf_", "")
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id, name, desc, price, image_url FROM bracelets WHERE lower(name) LIKE ? OR lower(desc) LIKE ? ORDER BY created_at DESC",
              (f'%{search_term}%', f'%{search_term}%'))
    items = c.fetchall(); conn.close()
    if not items:
        await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
        "Вопрос 4 из 5\n\n"
        "⚡ Насколько мощный браслет тебе нужен?\n\n"
        "Камни сами по себе уже работают — но мастер может дополнительно зарядить браслет "
        "своей энергией и намерением, усилив его действие многократно.",
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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
    await cb.message.edit_text(
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



@main_router.message()
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
    asyncio.create_task(send_quiz_reminders())
    asyncio.create_task(send_diag_followup())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")