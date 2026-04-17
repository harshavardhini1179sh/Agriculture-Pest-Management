#!/usr/bin/env python3
"""Create pest_management database and run schema.sql (PostgreSQL)."""
import os
import sys

import psycopg2

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Connect to default 'postgres' db to create our database
CREATE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
DB_URL = "postgresql://postgres:postgres@localhost:5432/pest_management"


def main():
    print("Creating database pest_management...")
    conn = psycopg2.connect(CREATE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    # Close other clients (e.g. Flask, pgAdmin) or DROP DATABASE fails with ObjectInUse.
    cur.execute(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = 'pest_management' AND pid <> pg_backend_pid()
        """
    )
    cur.execute("DROP DATABASE IF EXISTS pest_management")
    cur.execute("CREATE DATABASE pest_management")
    cur.close()
    conn.close()

    print("Applying schema.sql...")
    with open(os.path.join(SCRIPT_DIR, "schema.sql")) as f:
        sql = f.read()
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            try:
                cur.execute(stmt)
            except Exception as e:
                print("Warning:", e)
    cur.close()
    conn.close()
    print("Done. Database ready.")


if __name__ == "__main__":
    main()
