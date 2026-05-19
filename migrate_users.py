import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(column[1] == column_name for column in columns)


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = OFF;")

    # Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create default user for old progress
    cursor.execute("""
    INSERT OR IGNORE INTO users (username)
    VALUES ('default')
    """)

    cursor.execute("""
    SELECT id FROM users WHERE username = 'default'
    """)
    default_user_id = cursor.fetchone()[0]

    # Add user_id to user_answers if missing
    if not column_exists(cursor, "user_answers", "user_id"):
        cursor.execute("""
        ALTER TABLE user_answers
        ADD COLUMN user_id INTEGER
        """)

        cursor.execute("""
        UPDATE user_answers
        SET user_id = ?
        WHERE user_id IS NULL
        """, (default_user_id,))

    # Rebuild review_status as user-specific
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_status_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        grammar_id INTEGER NOT NULL,
        correct_count INTEGER DEFAULT 0,
        wrong_count INTEGER DEFAULT 0,
        mastery_level TEXT DEFAULT 'new',
        last_reviewed_at TEXT,
        UNIQUE(user_id, grammar_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (grammar_id) REFERENCES grammar_points(id)
    );
    """)

    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table' AND name = 'review_status'
    """)

    if cursor.fetchone():
        cursor.execute("""
        INSERT OR IGNORE INTO review_status_new (
            user_id,
            grammar_id,
            correct_count,
            wrong_count,
            mastery_level,
            last_reviewed_at
        )
        SELECT
            ?,
            grammar_id,
            correct_count,
            wrong_count,
            mastery_level,
            last_reviewed_at
        FROM review_status
        """, (default_user_id,))

        cursor.execute("DROP TABLE review_status")
        cursor.execute("ALTER TABLE review_status_new RENAME TO review_status")

    conn.commit()
    conn.close()

    print("User migration completed successfully!")


if __name__ == "__main__":
    migrate()