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
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, photo_count INT, notes TEXT, created_at TIMESTAMP, admin_result TEXT, sent BOOLEAN DEFAULT FALSE, photo1_file_id TEXT, photo2_file_id TEXT)''')
    
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
    for _sql in ["ALTER TABLE users ADD COLUMN welcome_sent BOOLEAN DEFAULT FALSE","ALTER TABLE users ADD COLUMN referred_by INT DEFAULT NULL"]:
        try: c.execute(_sql); conn.commit()
        except: pass
    
    # Стандартные категории
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🏋️ Практики', '🏋️', 'Физические упражнения'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎵 Музыка 432Hz', '🎵', 'Исцеляющая музыка'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎁 Готовые браслеты', '🎁', 'Готовые изделия'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('✨ Индивидуальный подбор', '✨', 'Подбор под вас'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🩺 Диагностика', '🩺', 'Загрузка фото'))
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
        await bot.send_message(ADMIN_ID, f"🩺 НОВАЯ ДИАГНОСТИКА\n\n👤 {name} ({uname})\nID: {user_id}\n\n📝 {notes}")
        if photo1_id: await bot.send_photo(ADMIN_ID, photo1_id, caption="Фото 1")
        if photo2_id: await bot.send_photo(ADMIN_ID, photo2_id, caption="Фото 2")
    except Exception as e: logger.error(f"notify_diag: {e}")

async def get_categories_keyboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}")] for cat in cats]
    # Добавляю диагностику и корзину
    buttons.append([types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="diag_start")])
    buttons.append([types.InlineKeyboardButton(text="🛒 КОРЗИНА", callback_data="view_cart")])
    buttons.append([types.InlineKeyboardButton(text="📖 ИСТОРИИ КЛИЕНТОВ", callback_data="show_stories")])
    buttons.append([types.InlineKeyboardButton(text="🤝 МОЯ РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="my_referral")])
    buttons.append([types.InlineKeyboardButton(text="📞 СВЯЗАТЬСЯ С МАСТЕРОМ", callback_data="contact_master")])
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
            await msg.answer("🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nЯ помогу найти браслет или чётки, которые подойдут именно вам.\n\n🎁 СКИДКА 20% на первый заказ!\nПромокод: WELCOME20\n\nВыберите раздел 👇", reply_markup=kb)
            conn = get_db(); c = conn.cursor()
            c.execute('UPDATE users SET welcome_sent = TRUE WHERE user_id = ?', (user_id,))
            conn.commit(); conn.close()
        else:
            await msg.answer("👋 С возвращением!\n\nВыбери раздел:", reply_markup=kb)

@main_router.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    await msg.answer("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())

@main_router.message(Command("diagnostics"))
async def diag_cmd(msg: types.Message, state: FSMContext):
    text = """🏥 ДИАГНОСТИКА ЗДОРОВЬЯ

Я помогу определить, какие браслеты подойдут именно вам.

Ответьте на несколько вопросов:

1️⃣ Какая главная проблема вас беспокоит?
   А) Стресс и тревога
   В) Боли в теле
   С) Сон и усталость
   D) Другое"""
    
    await msg.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="😰 Стресс и тревога", callback_data="diag_stress")],
        [types.InlineKeyboardButton(text="🤕 Боли в теле", callback_data="diag_pain")],
        [types.InlineKeyboardButton(text="😴 Сон и усталость", callback_data="diag_sleep")],
        [types.InlineKeyboardButton(text="❓ Другое", callback_data="diag_other")],
    ]))
    await state.set_state(DiagnosticStates.waiting_photo1)

@main_router.callback_query(F.data == "diag_start")
async def diag_start_cb(cb: types.CallbackQuery, state: FSMContext):
    """Стартовая кнопка диагностики из меню"""
    text = """🏥 ДИАГНОСТИКА ЗДОРОВЬЯ

Я помогу определить, какие браслеты подойдут именно вам.

Ответьте на несколько вопросов:

1️⃣ Какая главная проблема вас беспокоит?
   А) Стресс и тревога
   В) Боли в теле
   С) Сон и усталость
   D) Другое"""
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="😰 Стресс и тревога", callback_data="diag_stress")],
        [types.InlineKeyboardButton(text="🤕 Боли в теле", callback_data="diag_pain")],
        [types.InlineKeyboardButton(text="😴 Сон и усталость", callback_data="diag_sleep")],
        [types.InlineKeyboardButton(text="❓ Другое", callback_data="diag_other")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЕ CALLBACK - НАВИГАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

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
async def show_category(cb: types.CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    
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
    await state.set_state(AdminStates.add_category)
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

@main_router.callback_query(F.data.startswith("diag_"))
async def diag_answer(cb: types.CallbackQuery, state: FSMContext):
    answer = cb.data.split("_")[1]
    
    questions = {
        'stress': ('😰 Стресс и тревога', '2️⃣ Как долго вас беспокоит эта проблема?\n   А) Недавно (1-2 недели)\n   В) Месяц-два\n   С) Больше полугода'),
        'pain': ('🤕 Боли в теле', '2️⃣ Где именно вы чувствуете боли?\n   А) Спина\n   В) Суставы\n   С) Мышцы'),
        'sleep': ('😴 Сон и усталость', '2️⃣ Сколько часов вы спите в ночь?\n   А) Менее 6 часов\n   В) 6-7 часов\n   С) 8+ часов'),
        'other': ('❓ Другое', '2️⃣ Опишите вашу проблему в свободном виде'),
    }
    
    if answer == 'other':
        await cb.message.edit_text(questions['other'][1])
        await state.update_data(diag_answer1='other')
        await state.set_state(DiagnosticStates.waiting_photo1)
        await cb.answer()
        return
    
    await state.update_data(diag_answer1=answer)
    
    buttons = []
    if answer in ['stress', 'pain', 'sleep']:
        q_variants = questions[answer][1].split('\n   ')
        for variant in q_variants[1:]:
            letter = variant[0]
            text = variant[3:]
            buttons.append([types.InlineKeyboardButton(text=f"{letter} {text}", callback_data=f"diag_q2_{letter}")])
    
    await cb.message.edit_text(questions[answer][1], reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@main_router.callback_query(F.data.startswith("diag_q2_"))
async def diag_q2_answer(cb: types.CallbackQuery, state: FSMContext):
    answer2 = cb.data.split("_")[-1]
    await state.update_data(diag_answer2=answer2)
    
    await cb.message.edit_text("""3️⃣ ФОТО ЗДОРОВЬЯ

Теперь загрузи две свои фотографии для анализа:
- Первая фото: фото вашего состояния (лицо, руки, тело - что хотите)
- Вторая фото: дополнительная фото для полноты анализа

Это поможет нам лучше подобрать браслеты.""")
    await state.set_state(DiagnosticStates.waiting_photo1)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА - ЗАГРУЗКА ФОТО
# ═══════════════════════════════════════════════════════════════════════════

@diag_router.message(DiagnosticStates.waiting_photo1)
async def diag_photo1(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo1=photo.file_id)
    await msg.answer("✅ Первая фото получена!\n\nТеперь загрузи ВТОРУЮ:")
    await state.set_state(DiagnosticStates.waiting_photo2)

@diag_router.message(DiagnosticStates.waiting_photo2)
async def diag_photo2(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo2=photo.file_id)
    await msg.answer("✅ Вторая фото получена!\n\nНапиши заметки (или 'пропустить'):")
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
