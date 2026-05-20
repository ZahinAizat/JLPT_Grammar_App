import sqlite3
import getpass
from werkzeug.security import generate_password_hash

DB_PATH = "data/jlpt_app.db"


def ensure_user_account_columns():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(users)")
    columns = [row["name"] for row in cur.fetchall()]

    if "password_hash" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    if "created_at" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

    conn.commit()
    conn.close()


def main():
    ensure_user_account_columns()

    username = input("Old username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass.getpass("New password: ")
    confirm_password = getpass.getpass("Confirm password: ")

    if password != confirm_password:
        print("Passwords do not match.")
        return

    if len(password) < 6:
        print("Password must be at least 6 characters.")
        return

    password_hash = generate_password_hash(password)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, username, password_hash
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    user = cur.fetchone()

    if user is None:
        conn.close()
        print("User not found.")
        return

    cur.execute(
        """
        UPDATE users
        SET password_hash = ?
        WHERE username = ?
        """,
        (password_hash, username)
    )

    conn.commit()
    conn.close()

    print(f"Password set successfully for user: {username}")


if __name__ == "__main__":
    main()