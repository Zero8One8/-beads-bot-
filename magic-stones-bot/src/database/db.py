import sqlite3
import threading
import logging
from contextlib import contextmanager
from typing import Generator
from src.config import Config

logger = logging.getLogger(__name__)

class Database:
    _local = threading.local()
    
    def __init__(self, db_path: str = str(Config.DB_PATH)):
        self.db_path = db_path
    
    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or not self._local.connection:
            self._local.connection = self._create_connection()
        return self._local.connection
    
    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -64000")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA temp_store = MEMORY")
        logger.debug(f"Создано соединение с БД для потока {threading.get_ident()}")
        return conn
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка БД: {e}")
            raise
    
    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        with self.connection() as conn:
            yield conn.cursor()
    
    def close_all(self):
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            delattr(self._local, 'connection')
            logger.info("Соединения с БД закрыты")

db = Database()