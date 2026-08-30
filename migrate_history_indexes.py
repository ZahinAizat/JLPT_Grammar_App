import sqlite3
from database import DB_PATH


def migrate():
    conn = sqlite3.connect(DB_PATH)

    try:
        cur = conn.cursor()

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_history_user_answered_at
        ON web_answer_history(user_id, answered_at DESC)
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_history_user_grammar
        ON web_answer_history(user_id, correct_grammar_id)
        """)

        conn.commit()

        print("History indexes migration completed successfully.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()