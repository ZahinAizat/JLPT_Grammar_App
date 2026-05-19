import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


sample_data = [
    {
        "jlpt_level": "N2",
        "grammar": "あくまでも",
        "reading": "あくまでも",
        "romaji": "akumade mo",
        "meaning": "to the end; persistently; absolutely; still",
        "formation": "あくまでも + phrase",
        "example_sentence": "これはあくまでも私の意見です。",
        "example_translation": "This is only my opinion.",
        "source": "JLPT Sensei",
        "question_type": "fill_blank",
        "question_text": "これは（　）私の意見です。",
        "explanation": "あくまでも means something is only/still within a certain limit or position.",
        "difficulty": "easy",
        "choices": [
            ("あくまでも", 1),
            ("案の定", 0),
            ("あらかじめ", 0),
            ("あっての", 0),
        ],
    },
    {
        "jlpt_level": "N2",
        "grammar": "案の定",
        "reading": "案の定",
        "romaji": "an no jou",
        "meaning": "just as expected; sure enough",
        "formation": "案の定 + sentence",
        "example_sentence": "案の定、彼はまた遅刻した。",
        "example_translation": "Sure enough, he was late again.",
        "source": "JLPT Sensei",
        "question_type": "fill_blank",
        "question_text": "（　）、彼はまた遅刻した。",
        "explanation": "案の定 means something happened just as expected.",
        "difficulty": "easy",
        "choices": [
            ("案の定", 1),
            ("あえて", 0),
            ("あらかじめ", 0),
            ("あっての", 0),
        ],
    },
    {
        "jlpt_level": "N2",
        "grammar": "あらかじめ",
        "reading": "あらかじめ",
        "romaji": "arakajime",
        "meaning": "beforehand; in advance",
        "formation": "あらかじめ + verb",
        "example_sentence": "会議の資料をあらかじめ読んでください。",
        "example_translation": "Please read the meeting materials beforehand.",
        "source": "JLPT Sensei",
        "question_type": "fill_blank",
        "question_text": "会議の資料を（　）読んでください。",
        "explanation": "あらかじめ means doing something beforehand or in advance.",
        "difficulty": "easy",
        "choices": [
            ("あらかじめ", 1),
            ("案の定", 0),
            ("あえて", 0),
            ("あくまでも", 0),
        ],
    },
    {
        "jlpt_level": "N2",
        "grammar": "あっての",
        "reading": "あっての",
        "romaji": "atte no",
        "meaning": "which exists because of; thanks to",
        "formation": "Noun + あっての + Noun",
        "example_sentence": "お客様あっての仕事です。",
        "example_translation": "This work exists because of the customers.",
        "source": "JLPT Sensei",
        "question_type": "fill_blank",
        "question_text": "お客様（　）仕事です。",
        "explanation": "あっての means something can exist only because of something else.",
        "difficulty": "normal",
        "choices": [
            ("あっての", 1),
            ("あえて", 0),
            ("案の定", 0),
            ("あらかじめ", 0),
        ],
    },
]


def insert_grammar_point(cursor, item):
    cursor.execute("""
    SELECT id
    FROM grammar_points
    WHERE grammar = ? AND romaji = ?
    """, (item["grammar"], item["romaji"]))

    existing = cursor.fetchone()

    if existing:
        return existing[0]

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
        item["jlpt_level"],
        item["grammar"],
        item["reading"],
        item["romaji"],
        item["meaning"],
        item["formation"],
        item["example_sentence"],
        item["example_translation"],
        item["source"],
    ))

    return cursor.lastrowid


def insert_question(cursor, grammar_id, item):
    cursor.execute("""
    SELECT id
    FROM questions
    WHERE grammar_id = ? AND question_text = ?
    """, (grammar_id, item["question_text"]))

    existing = cursor.fetchone()

    if existing:
        return None

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
        item["question_type"],
        item["question_text"],
        item["explanation"],
        item["difficulty"],
    ))

    return cursor.lastrowid


def insert_choices(cursor, question_id, choices):
    for index, choice in enumerate(choices, start=1):
        choice_text = choice[0]
        is_correct = choice[1]

        cursor.execute("""
        INSERT INTO choices (
            question_id,
            choice_number,
            choice_text,
            is_correct
        )
        VALUES (?, ?, ?, ?)
        """, (
            question_id,
            index,
            choice_text,
            is_correct,
        ))


def insert_review_status(cursor, grammar_id):
    cursor.execute("""
    INSERT OR IGNORE INTO review_status (
        grammar_id,
        correct_count,
        wrong_count,
        mastery_level,
        last_reviewed_at
    )
    VALUES (?, 0, 0, 'new', NULL)
    """, (grammar_id,))


def insert_more_sample_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    inserted_count = 0
    skipped_count = 0

    for item in sample_data:
        grammar_id = insert_grammar_point(cursor, item)
        question_id = insert_question(cursor, grammar_id, item)

        insert_review_status(cursor, grammar_id)

        if question_id is None:
            skipped_count += 1
        else:
            insert_choices(cursor, question_id, item["choices"])
            inserted_count += 1

    conn.commit()
    conn.close()

    print("More sample data inserted successfully!")
    print(f"Inserted questions: {inserted_count}")
    print(f"Skipped existing questions: {skipped_count}")


if __name__ == "__main__":
    insert_more_sample_data()