"""Database connection management"""

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from typing import Optional
import logging
from ..config import Config

logger = logging.getLogger(__name__)

# Connection pool
_pool: Optional[SimpleConnectionPool] = None


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """Initialize the connection pool"""
    global _pool
    if _pool is None:
        try:
            _pool = SimpleConnectionPool(
                minconn,
                maxconn,
                **Config.get_db_params()
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise


def get_connection():
    """Get a connection from the pool"""
    global _pool
    if _pool is None:
        init_pool()

    try:
        conn = _pool.getconn()
        return conn
    except Exception as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise


def return_connection(conn) -> None:
    """Return a connection to the pool"""
    global _pool
    if _pool is not None and conn is not None:
        _pool.putconn(conn)


def close_all_connections() -> None:
    """Close all connections in the pool"""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("All database connections closed")


def close_connection(conn) -> None:
    """Close a specific connection (returns to pool)"""
    return_connection(conn)


def test_connection() -> bool:
    """Test database connectivity"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        return_connection(conn)
        logger.info("Database connection test successful")
        return result[0] == 1
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
