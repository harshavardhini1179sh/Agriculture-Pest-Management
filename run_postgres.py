#!/usr/bin/env python3
"""
One script to run the app with PostgreSQL: create DB, schema, load data, start Flask.
Requires PostgreSQL running on localhost:5432 (user postgres, password postgres).
Install: https://postgresapp.com (Mac) or Docker: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15-alpine
"""
import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pest_management")

def step(msg):
    print("\n=== " + msg + " ===")

def main():
    step("Checking PostgreSQL connection")
    try:
        import psycopg2
        c = psycopg2.connect(os.environ["DATABASE_URL"].replace("pest_management", "postgres"))
        c.close()
    except Exception as e:
        print("Cannot connect to PostgreSQL:", e)
        print("\nTo use PostgreSQL:")
        print("  1. Install: https://postgresapp.com (Mac) or Docker")
        print("  2. Start PostgreSQL (e.g. open Postgres.app, or: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15-alpine)")
        print("  3. Run again: python3 run_postgres.py")
        sys.exit(1)
    print("Connected.")

    step("Creating database and tables")
    subprocess.run([sys.executable, "init_db.py"], check=True)

    step("Loading USDA QuickStats-based dataset")
    subprocess.run([sys.executable, "load_quickstats_dataset.py"], check=True)

    step("Starting Flask at http://127.0.0.1:5001")
    subprocess.run([sys.executable, "app.py"])

if __name__ == "__main__":
    main()
