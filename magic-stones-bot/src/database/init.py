from src.database.db import db

def init_db():
    """Создаёт все таблицы, если их нет."""
    with db.connection() as conn:
        c = conn.cursor()
        
        # Пользователи и админы
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMP,
            birthday DATE,
            referred_by INTEGER
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )''')
        
        # Категории и товары
        c.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            emoji TEXT,
            description TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bracelets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL,
            image_url TEXT,
            category_id INTEGER,
            created_at TIMESTAMP,
            deleted INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            emoji TEXT,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS showcase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER,
            name TEXT,
            description TEXT,
            price REAL,
            stars_price INTEGER DEFAULT 0,
            image_file_id TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            FOREIGN KEY(collection_id) REFERENCES showcase_collections(id)
        )''')
        
        # Корзина и заказы
        c.execute('''CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bracelet_id INTEGER,
            quantity INTEGER,
            added_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            order_id INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total_price REAL,
            status TEXT,
            payment_method TEXT,
            created_at TIMESTAMP,
            promo_code TEXT,
            discount_rub REAL DEFAULT 0,
            bonus_used REAL DEFAULT 0,
            cashback_amount REAL DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            item_type TEXT,
            item_id INTEGER,
            item_name TEXT,
            quantity INTEGER,
            price REAL,
            created_at TIMESTAMP
        )''')
        
        # Диагностика
        c.execute('''CREATE TABLE IF NOT EXISTS diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            photo_count INTEGER,
            notes TEXT,
            created_at TIMESTAMP,
            admin_result TEXT,
            sent BOOLEAN DEFAULT FALSE,
            photo1_file_id TEXT,
            photo2_file_id TEXT,
            followup_sent INTEGER DEFAULT 0
        )''')
        
        # Кастомные заказы
        c.execute('''CREATE TABLE IF NOT EXISTS custom_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            purpose TEXT,
            stones TEXT,
            size TEXT,
            notes TEXT,
            photo1 TEXT,
            photo2 TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP
        )''')
        
        # Музыка и тренировки
        c.execute('''CREATE TABLE IF NOT EXISTS music (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            duration INTEGER,
            audio_url TEXT,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            duration INTEGER,
            difficulty TEXT,
            created_at TIMESTAMP
        )''')
        
        # Услуги и расписание
        c.execute('''CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL,
            duration INTEGER,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS schedule_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_date TEXT,
            time_slot TEXT,
            available INTEGER DEFAULT 1,
            booked_by INTEGER,
            booked_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_id INTEGER,
            slot_id INTEGER,
            comment TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP
        )''')
        
        # Подарочные сертификаты
        c.execute('''CREATE TABLE IF NOT EXISTS gift_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            amount REAL,
            buyer_id INTEGER,
            recipient_name TEXT,
            message TEXT,
            status TEXT DEFAULT 'active',
            used_by INTEGER,
            used_at TIMESTAMP,
            created_at TIMESTAMP,
            expires_at TIMESTAMP
        )''')
        
        # Избранное
        c.execute('''CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id INTEGER,
            added_at TIMESTAMP,
            UNIQUE(user_id, item_id)
        )''')
        
        # FAQ
        c.execute('''CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )''')
        
        # Напоминания о корзине
        c.execute('''CREATE TABLE IF NOT EXISTS cart_reminders (
            user_id INTEGER PRIMARY KEY,
            last_reminder TIMESTAMP,
            reminded INTEGER DEFAULT 0
        )''')
        
        # База знаний
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            notes TEXT
        )''')
        
        # Квизы
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            weights TEXT,
            sort_order INTEGER,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            answers TEXT,
            recommended_stone TEXT,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS totem_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            weights TEXT,
            sort_order INTEGER,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS totem_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            answers TEXT,
            top1 TEXT,
            top2 TEXT,
            top3 TEXT,
            created_at TIMESTAMP
        )''')
        
        # Истории
        c.execute('''CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            story_text TEXT,
            photo_file_id TEXT,
            approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            auto_generated BOOLEAN DEFAULT FALSE
        )''')
        
        # Рефералы и бонусы
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS referral_balance (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            total_earned REAL DEFAULT 0,
            referral_count INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bonus_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            operation TEXT,
            order_id INTEGER,
            created_at TIMESTAMP
        )''')
        
        # Промокоды
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            discount_pct INTEGER DEFAULT 0,
            discount_rub INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            expires_at TIMESTAMP,
            description TEXT,
            created_at TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS promo_uses (
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP,
            PRIMARY KEY (user_id, code)
        )''')
        
        # Клуб
        c.execute('''CREATE TABLE IF NOT EXISTS club_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            status TEXT DEFAULT 'trial',
            trial_start TIMESTAMP,
            trial_end TIMESTAMP,
            subscription_start TIMESTAMP,
            subscription_end TIMESTAMP,
            payment_id TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )''')
        
        # Планировщик постов
        c.execute('''CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT,
            channel_id TEXT,
            scheduled_time TIMESTAMP,
            status TEXT DEFAULT 'pending',
            error TEXT,
            published_at TIMESTAMP,
            created_at TIMESTAMP
        )''')
        
        # Статистика воронки
        c.execute('''CREATE TABLE IF NOT EXISTS funnel_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT,
            details TEXT,
            created_at TIMESTAMP
        )''')
        
        # Настройки
        c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        # Рассылки
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_text TEXT,
            sent_count INTEGER,
            failed_count INTEGER,
            blocked_count INTEGER,
            total_count INTEGER,
            created_at TIMESTAMP
        )''')
        
        # Push-уведомления
        c.execute('''CREATE TABLE IF NOT EXISTS push_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            message TEXT,
            sent_at TIMESTAMP,
            clicked BOOLEAN DEFAULT FALSE
        )''')
        
        # Звёздные заказы
        c.execute('''CREATE TABLE IF NOT EXISTS stars_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_id INTEGER,
            item_name TEXT,
            stars_amount INTEGER,
            charge_id TEXT UNIQUE,
            status TEXT DEFAULT 'paid',
            created_at TIMESTAMP
        )''')
        
        # Индексы
        c.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_diag_user ON diagnostics(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_funnel_user ON funnel_stats(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_funnel_date ON funnel_stats(created_at)")
        
        conn.commit()