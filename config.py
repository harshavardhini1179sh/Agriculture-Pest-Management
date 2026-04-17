# PostgreSQL database configuration.
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/pest_management"
)

# Admin can edit/delete regions and crops; admin can edit/delete any pest report.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@gmail.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
