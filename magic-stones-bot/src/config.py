import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / '.env'
load_dotenv(ENV_FILE)

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else 0
    
    DB_PATH = BASE_DIR / os.getenv('DB', 'data/bot.db')
    
    STORAGE_PATH = BASE_DIR / 'storage'
    DIAGNOSTICS_PATH = STORAGE_PATH / 'diagnostics'
    STORIES_PATH = STORAGE_PATH / 'stories'
    PHOTOS_PATH = STORAGE_PATH / 'photos'
    
    CONTENT_PATH = BASE_DIR / 'content'
    KNOWLEDGE_BASE_PATH = CONTENT_PATH / 'knowledge_base'
    POSTS_PATH = CONTENT_PATH / 'posts'
    CLUB_CONTENT_PATH = CONTENT_PATH / 'club'
    
    AMOCRM_SUBDOMAIN = os.getenv('AMOCRM_SUBDOMAIN', '')
    AMOCRM_ACCESS_TOKEN = os.getenv('AMOCRM_ACCESS_TOKEN', '')
    
    CHANNEL_ID = os.getenv('CHANNEL_ID', '')
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN не установлен")
        cls.STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        cls.DIAGNOSTICS_PATH.mkdir(parents=True, exist_ok=True)
        cls.STORIES_PATH.mkdir(parents=True, exist_ok=True)
        cls.PHOTOS_PATH.mkdir(parents=True, exist_ok=True)
        cls.CONTENT_PATH.mkdir(parents=True, exist_ok=True)
        cls.KNOWLEDGE_BASE_PATH.mkdir(parents=True, exist_ok=True)
        cls.POSTS_PATH.mkdir(parents=True, exist_ok=True)
        cls.CLUB_CONTENT_PATH.mkdir(parents=True, exist_ok=True)
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return True

Config.validate()