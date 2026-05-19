import csv
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"
GRAMMAR_CSV_PATH = BASE_DIR / "data" / "grammar_points.csv"
QUESTIONS_CSV_PATH = BASE_DIR / "data" / "questions.csv"


def get_connection():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def clean(value):
    if value is None:
        return ""

    return value.strip()


def check_required_tables(cursor):
    required_tables = [
        "grammar_points",
        "questions",
        "choices",
        "user_answers",
        "review_status",
    ]

    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    """)

    existing_tables = [row["name"] for row in cursor.fetchall()]

    missing_tables = []

    for table in required_tables:
        if table not in existing_tables:
            missing_tables.append(table)

    if missing_tables:
        raise RuntimeError(
            "Missing database tables: " + ", ".join(missing_tables)
        )


def import_grammar_points(cursor):
    if not GRAMMAR_CSV_PATH.exists():
        print("grammar_points.csv not found.")
        return 0, 0

    inserted_count = 0
    skipped_count = 0

    with open(GRAMMAR_CSV_PATH, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            grammar = clean(row.get("grammar"))

            if grammar == "":
                skipped_count += 1
                continue

            cursor.execute("""
            SELECT id
            FROM grammar_points
            WHERE grammar = ?
            """, (grammar,))

            existing = cursor.fetchone()

            if existing:
                skipped_count += 1
                continue

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
                clean(row.get("jlpt_level")),
                grammar,
                clean(row.get("reading")),
                clean(row.get("romaji")),
                clean(row.get("meaning")),
                clean(row.get("formation")),
                clean(row.get("example_sentence")),
                clean(row.get("example_translation")),
                clean(row.get("source")),
            ))

            inserted_count += 1

    return inserted_count, skipped_count


def get_grammar_id(cursor, grammar):
    cursor.execute("""
    SELECT id
    FROM grammar_points
    WHERE grammar = ?
    """, (grammar,))

    result = cursor.fetchone()

    if result is None:
        return None

    return result["id"]


def import_questions(cursor):
    if not QUESTIONS_CSV_PATH.exists():
        print("questions.csv not found.")
        return 0, 0, 0

    inserted_count = 0
    skipped_count = 0
    error_count = 0

    with open(QUESTIONS_CSV_PATH, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            grammar = clean(row.get("grammar"))
            question_text = clean(row.get("question_text"))

            if grammar == "" or question_text == "":
                print("Skipped row because grammar or question_text is empty.")
                error_count += 1
                continue

            grammar_id = get_grammar_id(cursor, grammar)

            if grammar_id is None:
                print(f"Skipped question because grammar was not found: {grammar}")
                error_count += 1
                continue

            cursor.execute("""
            SELECT id
            FROM questions
            WHERE grammar_id = ? AND question_text = ?
            """, (grammar_id, question_text))

            existing_question = cursor.fetchone()

            if existing_question:
                skipped_count += 1
                continue

            correct_choice_text = clean(row.get("correct_choice"))

            if not correct_choice_text.isdigit():
                print(f"Invalid correct_choice for question: {question_text}")
                error_count += 1
                continue

            correct_choice = int(correct_choice_text)

            if correct_choice < 1 or correct_choice > 4:
                print(f"correct_choice must be 1 to 4: {question_text}")
                error_count += 1
                continue

            choices = [
                clean(row.get("choice1")),
                clean(row.get("choice2")),
                clean(row.get("choice3")),
                clean(row.get("choice4")),
            ]

            if any(choice == "" for choice in choices):
                print(f"Question has empty choices: {question_text}")
                error_count += 1
                continue

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
                clean(row.get("question_type")) or "fill_blank",
                question_text,
                clean(row.get("explanation")),
                clean(row.get("difficulty")) or "easy",
            ))

            question_id = cursor.lastrowid

            for index, choice_text in enumerate(choices, start=1):
                is_correct = 1 if index == correct_choice else 0

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

            inserted_count += 1

    return inserted_count, skipped_count, error_count


def import_csv_data():
    conn = get_connection()
    cursor = conn.cursor()

    check_required_tables(cursor)

    grammar_inserted, grammar_skipped = import_grammar_points(cursor)
    question_inserted, question_skipped, question_errors = import_questions(cursor)

    conn.commit()
    conn.close()

    print("=" * 50)
    print("CSV Import Finished")
    print("=" * 50)
    print(f"Grammar inserted: {grammar_inserted}")
    print(f"Grammar skipped: {grammar_skipped}")
    print(f"Questions inserted: {question_inserted}")
    print(f"Questions skipped: {question_skipped}")
    print(f"Question errors: {question_errors}")


if __name__ == "__main__":
    import_csv_data()