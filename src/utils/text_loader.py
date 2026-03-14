"""
Модуль для загрузки и парсинга текстовых файлов с контентом.
"""
import os
import logging
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime

from src.config import Config

logger = logging.getLogger(__name__)

class ContentLoader:
    """
    Загрузчик контента с кэшированием и отслеживанием изменений.
    """
    
    _cache: Dict[str, tuple] = {}
    
    MARKERS = {
        'TITLE': 'TITLE',
        'SHORT_DESC': 'SHORT_DESC',
        'FULL_DESC': 'FULL_DESC',
        'PROPERTIES': 'PROPERTIES',
        'ELEMENTS': 'ELEMENTS',
        'ZODIAC': 'ZODIAC',
        'CHAKRA': 'CHAKRA',
        'PRICE_PER_BEAD': 'PRICE_PER_BEAD',
        'FORMS': 'FORMS',
        'COLOR': 'COLOR',
        'STONE_ID': 'STONE_ID',
        'TASKS': 'TASKS',
        'NOTES': 'NOTES',
    }
    
    @classmethod
    def _get_file_hash(cls, file_path: Path) -> str:
        """Получить хеш от времени модификации файла."""
        if not file_path.exists():
            return ""
        mtime = os.path.getmtime(file_path)
        return hashlib.md5(str(mtime).encode()).hexdigest()
    
    @classmethod
    def _parse_file(cls, file_path: Path) -> Dict[str, str]:
        """
        Парсит текстовый файл с маркерами [MARKER].
        """
        if not file_path.exists():
            logger.warning(f"Файл не найден: {file_path}")
            return {}
        
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return {}
        
        result = {}
        current_marker = None
        current_lines = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            if line.startswith('[') and line.endswith(']'):
                if current_marker:
                    result[current_marker] = '\n'.join(current_lines).strip()
                    current_lines = []
                
                marker = line[1:-1].strip()
                if marker in cls.MARKERS.values() or marker in cls.MARKERS:
                    current_marker = marker
                else:
                    logger.warning(f"Неизвестный маркер {marker} в файле {file_path}")
                    current_marker = None
            elif current_marker:
                current_lines.append(line)
        
        if current_marker and current_lines:
            result[current_marker] = '\n'.join(current_lines).strip()
        
        return result
    
    @classmethod
    def load_stone(cls, stone_id: str) -> Optional[Dict[str, Any]]:
        """
        Загружает описание камня по его ID.
        """
        file_path = Config.KNOWLEDGE_BASE_PATH / f"{stone_id}.txt"
        if not file_path.exists():
            for f in Config.KNOWLEDGE_BASE_PATH.glob("*.txt"):
                if stone_id.lower() in f.stem.lower():
                    file_path = f
                    break
            else:
                logger.warning(f"Камень с ID {stone_id} не найден")
                return None
        
        current_hash = cls._get_file_hash(file_path)
        cache_key = str(file_path)
        
        if cache_key in cls._cache:
            cached_hash, cached_content = cls._cache[cache_key]
            if cached_hash == current_hash:
                return cached_content
        
        content = cls._parse_file(file_path)
        content['_file'] = file_path.name
        content['_loaded_at'] = datetime.now().isoformat()
        
        cls._cache[cache_key] = (current_hash, content)
        
        logger.info(f"Загружен камень: {file_path.stem}")
        return content
    
    @classmethod
    def load_all_stones(cls) -> Dict[str, Dict[str, Any]]:
        """Загружает все доступные камни."""
        stones = {}
        for file_path in Config.KNOWLEDGE_BASE_PATH.glob("*.txt"):
            stone_id = file_path.stem
            content = cls.load_stone(stone_id)
            if content:
                stones[stone_id] = content
        return stones
    
    @classmethod
    def load_post(cls, post_id: str) -> Optional[str]:
        """Загружает готовый пост."""
        file_path = Config.POSTS_PATH / f"{post_id}.txt"
        if not file_path.exists():
            return None
        
        try:
            return file_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Ошибка загрузки поста {post_id}: {e}")
            return None
    
    @classmethod
    def list_posts(cls) -> List[str]:
        """Возвращает список ID доступных постов."""
        posts = []
        for file_path in Config.POSTS_PATH.glob("*.txt"):
            posts.append(file_path.stem)
        return sorted(posts)
    
    @classmethod
    def list_club_content(cls) -> List[Dict[str, str]]:
        """Список доступных материалов клуба."""
        items = []
        for file_path in Config.CLUB_CONTENT_PATH.glob("*.txt"):
            items.append({
                'id': file_path.stem,
                'title': file_path.stem.replace('_', ' ').title(),
                'file': file_path.name
            })
        return sorted(items, key=lambda x: x['title'])
    
    @classmethod
    def get_club_content(cls, item_id: str) -> Optional[str]:
        """Получить содержимое материала клуба."""
        file_path = Config.CLUB_CONTENT_PATH / f"{item_id}.txt"
        if not file_path.exists():
            return None
        return file_path.read_text(encoding='utf-8')
    
    @classmethod
    def load_club_info(cls) -> str:
        """Загружает описание клуба."""
        file_path = Config.CONTENT_PATH / 'club_info.txt'
        if not file_path.exists():
            return "Описание клуба временно отсутствует."
        try:
            return file_path.read_text(encoding='utf-8')
        except:
            return "Описание клуба временно отсутствует."
    
    @classmethod
    def clear_cache(cls):
        """Очищает кэш."""
        cls._cache.clear()
        logger.info("Кэш контента очищен")
