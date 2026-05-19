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


def check_csv_headers(reader, required_columns, csv_name):
    actual_columns = reader.fieldnames

    if actual_columns is None:
        raise RuntimeError(f"{csv_name} has no header row.")

    missing_columns = []

    for column in required_columns:
        if column not in actual_columns:
            missing_columns.append(column)

    if missing_columns:
        raise RuntimeError(
            f"{csv_name} is missing required columns: "
            + ", ".join(missing_columns)
        )    


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

        check_csv_headers(
            reader,
            [
                "jlpt_level",
                "grammar",
                "reading",
                "romaji",
                "meaning",
                "formation",
                "example_sentence",
                "example_translation",
                "source",
            ],
            "grammar_points.csv"
        )

        for row_number, row in enumerate(reader, start=2):
            jlpt_level = clean(row.get("jlpt_level"))
            grammar = clean(row.get("grammar"))
            meaning = clean(row.get("meaning"))

            if jlpt_level == "":
                print(f"Grammar CSV row {row_number}: skipped because jlpt_level is empty.")
                skipped_count += 1
                continue

            if jlpt_level not in ["N1", "N2"]:
                print(f"Grammar CSV row {row_number}: skipped because jlpt_level is invalid: {jlpt_level}")
                skipped_count += 1
                continue

            if grammar == "":
                print(f"Grammar CSV row {row_number}: skipped because grammar is empty.")
                skipped_count += 1
                continue

            if meaning == "":
                print(f"Grammar CSV row {row_number}: skipped because meaning is empty.")
                skipped_count += 1
                continue

            cursor.execute("""
            SELECT id
            FROM grammar_points
            WHERE grammar = ?
            """, (grammar,))

            existing = cursor.fetchone()

            if existing:
                print(f"Grammar CSV row {row_number}: skipped duplicate grammar: {grammar}")
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
                jlpt_level,
                grammar,
                clean(row.get("reading")),
                clean(row.get("romaji")),
                meaning,
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

        check_csv_headers(
            reader,
            [
                "grammar",
                "question_type",
                "question_text",
                "choice1",
                "choice2",
                "choice3",
                "choice4",
                "correct_choice",
                "explanation",
                "difficulty",
            ],
            "questions.csv"
        )

        for row_number, row in enumerate(reader, start=2):
            grammar = clean(row.get("grammar"))
            question_text = clean(row.get("question_text"))

            if grammar == "" or question_text == "":
                print(f"Questions CSV row {row_number}: skipped because grammar or question_text is empty.")
                error_count += 1
                continue

            grammar_id = get_grammar_id(cursor, grammar)

            if grammar_id is None:
                print(f"Questions CSV row {row_number}: skipped because grammar was not found: {grammar}")
                error_count += 1
                continue

            cursor.execute("""
            SELECT id
            FROM questions
            WHERE grammar_id = ? AND question_text = ?
            """, (grammar_id, question_text))

            existing_question = cursor.fetchone()

            if existing_question:
                print(f"Questions CSV row {row_number}: skipped duplicate question: {question_text}")
                skipped_count += 1
                continue

            correct_choice_text = clean(row.get("correct_choice"))

            if not correct_choice_text.isdigit():
                print(f"Questions CSV row {row_number}: invalid correct_choice for question: {question_text}")
                error_count += 1
                continue

            correct_choice = int(correct_choice_text)

            if correct_choice < 1 or correct_choice > 4:
                print(f"Questions CSV row {row_number}: correct_choice must be 1 to 4: {question_text}")
                error_count += 1
                continue

            choices = [
                clean(row.get("choice1")),
                clean(row.get("choice2")),
                clean(row.get("choice3")),
                clean(row.get("choice4")),
            ]

            if any(choice == "" for choice in choices):
                print(f"Questions CSV row {row_number}: question has empty choices: {question_text}")
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


def report_grammar_without_questions(cursor):
    cursor.execute("""
    SELECT
        grammar_points.id,
        grammar_points.jlpt_level,
        grammar_points.grammar
    FROM grammar_points
    LEFT JOIN questions
        ON grammar_points.id = questions.grammar_id
    WHERE questions.id IS NULL
    ORDER BY grammar_points.jlpt_level, grammar_points.id
    """)

    rows = cursor.fetchall()

    if not rows:
        return 0

    print()
    print("Warning: grammar points with no questions:")

    for row in rows:
        print(
            f'- ID {row["id"]} '
            f'[{row["jlpt_level"]}] '
            f'{row["grammar"]}'
        )

    return len(rows)    


def import_csv_data():
    conn = get_connection()
    cursor = conn.cursor()

    check_required_tables(cursor)

    grammar_inserted, grammar_skipped = import_grammar_points(cursor)
    question_inserted, question_skipped, question_errors = import_questions(cursor)
    grammar_without_questions = report_grammar_without_questions(cursor)

    conn.commit()
    conn.close()

    print(f"Grammar inserted: {grammar_inserted}")
    print(f"Grammar skipped: {grammar_skipped}")
    print(f"Questions inserted: {question_inserted}")
    print(f"Questions skipped: {question_skipped}")
    print(f"Question errors: {question_errors}")
    print(f"Grammar without questions: {grammar_without_questions}")


if __name__ == "__main__":
    import_csv_data()