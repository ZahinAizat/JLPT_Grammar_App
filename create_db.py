import sqlite3
from pathlib import Path


# Get project folder path
BASE_DIR = Path(__file__).resolve().parent

# Database path: JLPT_Grammar_App/data/jlpt_app.db
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def create_database():
    # Make sure data folder exists
    DB_PATH.parent.mkdir(exist_ok=True)

    # Connect to SQLite database
    # If jlpt_app.db does not exist, Python will create it
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable foreign key support
    cursor.execute("PRAGMA foreign_keys = ON;")

    # TABLE 1: grammar_points
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grammar_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jlpt_level TEXT,
        grammar TEXT NOT NULL,
        reading TEXT,
        romaji TEXT,
        meaning TEXT,
        formation TEXT,
        example_sentence TEXT,
        example_translation TEXT,
        source TEXT
    );
    """)

    # TABLE 2: questions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grammar_id INTEGER NOT NULL,
        question_type TEXT NOT NULL,
        question_text TEXT NOT NULL,
        explanation TEXT,
        difficulty TEXT,
        FOREIGN KEY (grammar_id) REFERENCES grammar_points(id)
    );
    """)

    # TABLE 3: choices
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS choices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        choice_number INTEGER NOT NULL,
        choice_text TEXT NOT NULL,
        is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
        FOREIGN KEY (question_id) REFERENCES questions(id)
    );
    """)

    # TABLE 4: user_answers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        selected_choice_id INTEGER NOT NULL,
        is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
        answered_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (question_id) REFERENCES questions(id),
        FOREIGN KEY (selected_choice_id) REFERENCES choices(id)
    );
    """)

    # TABLE 5: review_status
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_status (
        grammar_id INTEGER PRIMARY KEY,
        correct_count INTEGER DEFAULT 0,
        wrong_count INTEGER DEFAULT 0,
        mastery_level TEXT DEFAULT 'new',
        last_reviewed_at TEXT,
        FOREIGN KEY (grammar_id) REFERENCES grammar_points(id)
    );
    """)

    # Save changes
    conn.commit()

    # Close connection
    conn.close()

    print("Database created successfully!")
    print(f"Location: {DB_PATH}")


if __name__ == "__main__":
    create_database()