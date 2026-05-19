import sqlite3
import shutil
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def table_exists(cursor, table_name):
    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table' AND name = ?
    """, (table_name,))

    return cursor.fetchone() is not None


def count_rows(cursor, table_name):
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def clear_study_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BASE_DIR / "data" / f"jlpt_app_backup_before_clear_{timestamp}.db"

    shutil.copy2(DB_PATH, backup_path)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    tables_to_clear = [
        "user_answers",
        "review_status",
        "choices",
        "questions",
        "grammar_points",
    ]

    print("=" * 50)
    print("Before clearing")
    print("=" * 50)

    for table in tables_to_clear:
        print(f"{table}: {count_rows(cursor, table)} rows")

    confirm = input("\nType CLEAR to delete grammar/questions/progress data: ")

    if confirm != "CLEAR":
        print("Cancelled. Nothing was deleted.")
        conn.close()
        return

    # Delete child/dependent tables first
    cursor.execute("DELETE FROM user_answers")
    cursor.execute("DELETE FROM review_status")
    cursor.execute("DELETE FROM choices")
    cursor.execute("DELETE FROM questions")
    cursor.execute("DELETE FROM grammar_points")

    # Reset AUTOINCREMENT counters if sqlite_sequence exists
    if table_exists(cursor, "sqlite_sequence"):
        cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name IN (
            'grammar_points',
            'questions',
            'choices',
            'user_answers',
            'review_status'
        )
        """)

    conn.commit()

    print()
    print("=" * 50)
    print("After clearing")
    print("=" * 50)

    for table in tables_to_clear:
        print(f"{table}: {count_rows(cursor, table)} rows")

    conn.close()

    print()
    print(f"Backup created at: {backup_path}")
    print("Study database cleared successfully.")
    print("Users table was NOT deleted.")


if __name__ == "__main__":
    clear_study_database()