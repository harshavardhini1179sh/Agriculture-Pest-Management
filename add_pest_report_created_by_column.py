#!/usr/bin/env python3
"""One-time migration: add created_by column to pest_report if missing (e.g. DB created before this column was in schema)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import psycopg2

def main():
    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE pest_report ADD COLUMN IF NOT EXISTS created_by VARCHAR(255)")
        print("Done. pest_report.created_by is present.")
    except Exception as e:
        print("Error:", e)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
