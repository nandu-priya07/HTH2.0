"""
Centralized Supabase PostgreSQL Connection Pool and Client Management.
Provides thread-safe connection pooling, row dictionary cursors, and transaction safety.
"""

import os
import logging
import urllib.parse
from contextlib import contextmanager
from typing import Generator
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Ensure .env is loaded
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def get_postgres_uri() -> str:
    """
    Constructs or retrieves the valid PostgreSQL connection string for Supabase.
    Encodes password special characters cleanly.
    """
    raw_conn = os.getenv("Connection_string") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    user = os.getenv("user")
    password = os.getenv("password")
    host = os.getenv("host")
    port = os.getenv("port", "5432")
    database = os.getenv("database", "postgres")

    if user and password and host:
        quoted_pwd = urllib.parse.quote_plus(password)
        return f"postgresql://{user}:{quoted_pwd}@{host}:{port}/{database}"

    if raw_conn and "[YOUR-PASSWORD]" not in raw_conn and "[PASSWORD]" not in raw_conn:
        return raw_conn

    raise ValueError("Invalid or missing Supabase PostgreSQL connection parameters in .env")


_pool: ThreadedConnectionPool | None = None


def get_connection_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        uri = get_postgres_uri()
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=uri
        )
        logger.info("Initialized Supabase PostgreSQL Connection Pool.")
    return _pool


@contextmanager
def get_supabase_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager providing a pooled Supabase PostgreSQL connection with DictCursor.
    Handles commit on success, rollback on exception, and return to pool.
    """
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Supabase transaction error: {e}")
        raise
    finally:
        pool.putconn(conn)


import threading

_db_initialized = False
_db_init_lock = threading.Lock()


def initialize_supabase_database() -> None:
    """
    Ensures all required Supabase tables, indexes, and schemas exist once at process startup.
    """
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        schema_path = BACKEND_DIR / "supabase_schema.sql"
        if not schema_path.exists():
            logger.warning(f"Schema file not found at {schema_path}")
            _db_initialized = True
            return

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                sql_script = f.read()

            with get_supabase_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_script)
                    # Ensure datasets storage bucket exists in storage.buckets
                    cur.execute("""
                        INSERT INTO storage.buckets (id, name, public) 
                        VALUES ('datasets', 'datasets', false) 
                        ON CONFLICT (id) DO NOTHING;
                    """)
            _db_initialized = True
            logger.info("Supabase PostgreSQL database successfully verified & initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase database: {e}")
            raise
