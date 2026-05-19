from database import get_review_progress


def show_progress():
    progress_list = get_review_progress()

    if not progress_list:
        print("No review progress found yet.")
        return

    print("=" * 50)
    print("JLPT Grammar Review Progress")
    print("=" * 50)

    for item in progress_list:
        print()
        print(f'ID: {item["id"]}')
        print(f'Grammar: {item["grammar"]}')
        print(f'Meaning: {item["meaning"]}')
        print(f'Correct: {item["correct_count"]}')
        print(f'Wrong: {item["wrong_count"]}')
        print(f'Mastery: {item["mastery_level"]}')
        print(f'Last reviewed: {item["last_reviewed_at"]}')


if __name__ == "__main__":
    show_progress()


def get_random_question():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        questions.id AS question_id,
        grammar_points.id AS grammar_id,
        grammar_points.grammar,
        grammar_points.meaning,
        questions.question_text,
        questions.explanation,
        questions.difficulty
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    ORDER BY RANDOM()
    LIMIT 1
    """)

    question = cursor.fetchone()

    if question is None:
        conn.close()
        return None

    cursor.execute("""
    SELECT
        id AS choice_id,
        choice_number,
        choice_text,
        is_correct
    FROM choices
    WHERE question_id = ?
    ORDER BY choice_number
    """, (question["question_id"],))

    choices = cursor.fetchall()

    conn.close()

    return {
        "question_id": question["question_id"],
        "grammar_id": question["grammar_id"],
        "grammar": question["grammar"],
        "meaning": question["meaning"],
        "question_text": question["question_text"],
        "explanation": question["explanation"],
        "difficulty": question["difficulty"],
        "choices": [dict(choice) for choice in choices]
    }    