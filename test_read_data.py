import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def read_question():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        questions.id,
        grammar_points.grammar,
        grammar_points.meaning,
        questions.question_text,
        questions.explanation
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    LIMIT 1
    """)

    question = cursor.fetchone()

    if question is None:
        print("No question found.")
        conn.close()
        return

    question_id = question[0]

    print("=== QUESTION ===")
    print(f"Question ID: {question[0]}")
    print(f"Grammar: {question[1]}")
    print(f"Meaning: {question[2]}")
    print(f"Question: {question[3]}")
    print(f"Explanation: {question[4]}")
    print()

    cursor.execute("""
    SELECT choice_number, choice_text, is_correct
    FROM choices
    WHERE question_id = ?
    ORDER BY choice_number
    """, (question_id,))

    choices = cursor.fetchall()

    print("=== CHOICES ===")
    for choice in choices:
        number = choice[0]
        text = choice[1]
        is_correct = choice[2]

        if is_correct == 1:
            correct_mark = "correct"
        else:
            correct_mark = "wrong"

        print(f"{number}. {text} ({correct_mark})")

    conn.close()


if __name__ == "__main__":
    read_question()