import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def insert_sample_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    # -----------------------------
    # Insert grammar point
    # -----------------------------
    cursor.execute("""
    INSERT INTO grammar_points (
        jlpt_level,
        grammar,
        reading,
        romaji,
        meaning,
        formation,
        example_sentence,
        example_translation,
        source
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "N2",
        "あえて",
        "敢えて",
        "aete",
        "dare to; deliberately; purposely",
        "あえて + Verb",
        "彼はあえて難しい道を選んだ。",
        "He deliberately chose the difficult path.",
        "JLPT Sensei"
    ))

    grammar_id = cursor.lastrowid

    # -----------------------------
    # Insert question
    # -----------------------------
    cursor.execute("""
    INSERT INTO questions (
        grammar_id,
        question_type,
        question_text,
        explanation,
        difficulty
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        grammar_id,
        "fill_blank",
        "彼は（　）難しい道を選んだ。",
        "あえて means to deliberately do something, often even though it is difficult or risky.",
        "easy"
    ))

    question_id = cursor.lastrowid

    # -----------------------------
    # Insert 4 choices
    # -----------------------------
    choices = [
        (question_id, 1, "あえて", 1),
        (question_id, 2, "かえって", 0),
        (question_id, 3, "むしろ", 0),
        (question_id, 4, "せっかく", 0),
    ]

    cursor.executemany("""
    INSERT INTO choices (
        question_id,
        choice_number,
        choice_text,
        is_correct
    )
    VALUES (?, ?, ?, ?)
    """, choices)

    # -----------------------------
    # Insert review status
    # -----------------------------
    cursor.execute("""
    INSERT INTO review_status (
        grammar_id,
        correct_count,
        wrong_count,
        mastery_level,
        last_reviewed_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        grammar_id,
        0,
        0,
        "new",
        None
    ))

    conn.commit()
    conn.close()

    print("Sample data inserted successfully!")


if __name__ == "__main__":
    insert_sample_data()