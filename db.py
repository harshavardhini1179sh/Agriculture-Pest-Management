"""Database connection helper for Flask (PostgreSQL only)."""
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DATABASE_URL


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def execute_query(query, params=None, fetch=True):
    """Execute a SELECT and return list of dicts."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params)
        if fetch:
            return cur.fetchall()
        conn.commit()
    finally:
        conn.close()


def execute_insert(query, params=None):
    """Execute INSERT with RETURNING id; returns the new id."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else None
    finally:
        conn.close()


def execute_update_delete(query, params=None):
    """Execute UPDATE or DELETE."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
    finally:
        conn.close()
