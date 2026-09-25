"""
Database initialization and connection management for Chat & Conversation persistence.
Uses SQLite for local development with strict schema normalization and foreign key constraints.
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Generator, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Base data directory configuration
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "app.db"


def get_database_path() -> Path:
    """
    Resolves the SQLite database file path from environment or default.
    Ensures the parent directory exists.
    """
    env_path = os.getenv("CHAT_DATABASE_PATH") or os.getenv("CHAT_DATABASE_URL")
    if env_path:
        # Handle sqlite:/// prefix if present
        clean_path = env_path.replace("sqlite:///", "")
        db_path = Path(clean_path)
        if not db_path.is_absolute():
            db_path = BACKEND_DIR / db_path
    else:
        db_path = DEFAULT_DB_PATH

    os.makedirs(db_path.parent, exist_ok=True)
    return db_path


@contextmanager
def get_db_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager providing a SQLite database connection with row_factory,
    foreign key enforcement, and transactional integrity.
    """
    path = db_path or get_database_path()
    os.makedirs(path.parent, exist_ok=True)

    conn = sqlite3.connect(
        str(path),
        timeout=30.0,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    # Enforce SQLite foreign keys & performance pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass

    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction rolled back: {e}")
        raise
    finally:
        conn.close()


def initialize_database(db_path: Optional[Path] = None) -> None:
    """
    Initializes database schema and indexes if they do not already exist.
    """
    with get_db_connection(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                dataset_id TEXT,
                owner_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                result_json TEXT,
                visualization_json TEXT,
                intent_json TEXT,
                query_spec_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id, created_at ASC);

            CREATE INDEX IF NOT EXISTS idx_conversations_updated_at 
                ON conversations(updated_at DESC);

            CREATE TABLE IF NOT EXISTS auth_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
            CREATE TABLE IF NOT EXISTS chat_files (
                file_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (conversation_id, file_id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "owner_id" not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN owner_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated ON conversations(owner_id, updated_at DESC)")
        message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        if "intent_json" not in message_columns:
            conn.execute("ALTER TABLE messages ADD COLUMN intent_json TEXT")
        if "query_spec_json" not in message_columns:
            conn.execute("ALTER TABLE messages ADD COLUMN query_spec_json TEXT")
        logger.info(f"Chat database initialized at {db_path or get_database_path()}")
