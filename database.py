import random
import sqlite3
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "data" / "jlpt_app.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def initialize_database_updates():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(choices)")
    choice_columns = [row["name"] for row in cursor.fetchall()]

    if "grammar_id" not in choice_columns:
        cursor.execute("""
        ALTER TABLE choices
        ADD COLUMN grammar_id INTEGER
        """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_choices_grammar_id
    ON choices(grammar_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_choices_question_id
    ON choices(question_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_review_status_user_grammar
    ON review_status(user_id, grammar_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_answers_user_question
    ON user_answers(user_id, question_id)
    """)

    conn.commit()
    conn.close()


# -----------------------------
# User functions
# -----------------------------

def get_or_create_user(username):
    username = username.strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO users (username)
    VALUES (?)
    """, (username,))

    cursor.execute("""
    SELECT id, username
    FROM users
    WHERE username = ?
    """, (username,))

    user = cursor.fetchone()

    conn.commit()
    conn.close()

    return dict(user)


def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, username, created_at
    FROM users
    ORDER BY username
    """)

    users = cursor.fetchall()
    conn.close()

    return [dict(user) for user in users]


# -----------------------------
# Question helper functions
# -----------------------------

def calculate_question_weight(correct_count, wrong_count):
    total = correct_count + wrong_count

    if total == 0:
        return 10

    accuracy = correct_count / total * 100

    if accuracy < 60:
        return 10

    if accuracy < 80:
        return 6

    if accuracy < 90:
        return 3

    if accuracy >= 90 and total >= 5:
        return 1

    return 3


def find_choice_detail_by_text(cursor, choice_text, preferred_level):
    cursor.execute("""
    SELECT
        id AS choice_grammar_id,
        jlpt_level AS choice_detail_jlpt_level,
        grammar AS choice_detail_grammar,
        reading AS choice_detail_reading,
        romaji AS choice_detail_romaji,
        meaning AS choice_detail_meaning,
        formation AS choice_detail_formation,
        example_sentence AS choice_detail_example_sentence,
        example_translation AS choice_detail_example_translation,
        source AS choice_detail_source
    FROM grammar_points
    WHERE grammar = ?
       OR reading = ?
       OR romaji = ?
    ORDER BY
        CASE
            WHEN jlpt_level = ? THEN 0
            ELSE 1
        END,
        id
    LIMIT 1
    """, (
        choice_text,
        choice_text,
        choice_text,
        preferred_level
    ))

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def make_question_dict(cursor, question):
    cursor.execute("""
    SELECT
        choices.id AS choice_id,
        choices.choice_number,
        choices.choice_text,
        choices.is_correct,
        choices.grammar_id AS choice_grammar_id,
        grammar_points.jlpt_level AS choice_detail_jlpt_level,
        grammar_points.grammar AS choice_detail_grammar,
        grammar_points.reading AS choice_detail_reading,
        grammar_points.romaji AS choice_detail_romaji,
        grammar_points.meaning AS choice_detail_meaning,
        grammar_points.formation AS choice_detail_formation,
        grammar_points.example_sentence AS choice_detail_example_sentence,
        grammar_points.example_translation AS choice_detail_example_translation,
        grammar_points.source AS choice_detail_source
    FROM choices
    LEFT JOIN grammar_points
        ON choices.grammar_id = grammar_points.id
    WHERE choices.question_id = ?
    ORDER BY choices.choice_number
    """, (question["question_id"],))

    raw_choices = cursor.fetchall()
    choices = []

    for choice in raw_choices:
        choice_dict = dict(choice)

        if choice_dict["choice_detail_grammar"] is None:
            detail = find_choice_detail_by_text(
                cursor,
                choice_dict["choice_text"],
                question["jlpt_level"]
            )

            if detail is not None:
                for key, value in detail.items():
                    choice_dict[key] = value

        choices.append(choice_dict)

    correct_count = question["correct_count"]
    wrong_count = question["wrong_count"]
    total_asked = correct_count + wrong_count

    if total_asked == 0:
        accuracy = None
    else:
        accuracy = correct_count / total_asked * 100

    return {
        "question_id": question["question_id"],
        "grammar_id": question["grammar_id"],
        "jlpt_level": question["jlpt_level"],
        "grammar": question["grammar"],
        "meaning": question["meaning"],
        "question_text": question["question_text"],
        "explanation": question["explanation"],
        "difficulty": question["difficulty"],
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_asked": total_asked,
        "accuracy": accuracy,
        "mastery_level": question["mastery_level"],
        "choices": choices
    }


def get_weighted_question_excluding(user_id, exclude_question_ids, jlpt_level=None, difficulty_filter=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT
        questions.id AS question_id,
        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.meaning,
        questions.question_text,
        questions.explanation,
        questions.difficulty,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    """

    params = [user_id]
    conditions = []

    if jlpt_level is not None:
        conditions.append("grammar_points.jlpt_level = ?")
        params.append(jlpt_level)

    if difficulty_filter is not None:
        conditions.append("questions.difficulty = ?")
        params.append(difficulty_filter)

    if exclude_question_ids:
        placeholders = ",".join(["?"] * len(exclude_question_ids))
        sql += f" AND questions.id NOT IN ({placeholders})"
        params.extend(exclude_question_ids)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    print("SQL:", sql) #debugging 
    print("PARAMS:", params) #debugging tool
    
    cursor.execute(sql, params)
    questions = cursor.fetchall()

    if not questions:
        conn.close()
        return None

    weights = []

    for question in questions:
        weight = calculate_question_weight(
            question["correct_count"],
            question["wrong_count"]
        )
        weights.append(weight)

    selected_question = random.choices(
        questions,
        weights=weights,
        k=1
    )[0]

    question_dict = make_question_dict(cursor, selected_question)

    conn.close()
    return question_dict


def get_weak_question_excluding(user_id, exclude_question_ids, jlpt_level=None, difficulty_filter=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT
        questions.id AS question_id,
        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.meaning,
        questions.question_text,
        questions.explanation,
        questions.difficulty,
        review_status.correct_count AS correct_count,
        review_status.wrong_count AS wrong_count,
        review_status.mastery_level AS mastery_level
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    WHERE review_status.mastery_level = 'weak'
    """

    params = [user_id]

    if jlpt_level is not None:
        sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    if difficulty_filter is not None:
        sql += " AND questions.difficulty = ?"
        params.append(difficulty_filter)

    if exclude_question_ids:
        placeholders = ",".join("?" for _ in exclude_question_ids)
        sql += f" AND questions.id NOT IN ({placeholders})"
        params.extend(exclude_question_ids)

    sql += """
    ORDER BY review_status.wrong_count DESC, RANDOM()
    LIMIT 1
    """

    cursor.execute(sql, params)
    question = cursor.fetchone()

    if question is None:
        conn.close()
        return None

    question_dict = make_question_dict(cursor, question)

    conn.close()
    return question_dict


def get_new_question_excluding(user_id, exclude_question_ids, jlpt_level=None, difficulty_filter=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT
        questions.id AS question_id,
        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.meaning,
        questions.question_text,
        questions.explanation,
        questions.difficulty,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    WHERE questions.id NOT IN (
        SELECT question_id
        FROM user_answers
        WHERE user_id = ?
    )
    """

    params = [user_id, user_id]

    if jlpt_level is not None:
        sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    if difficulty_filter is not None:
        sql += " AND questions.difficulty = ?"
        params.append(difficulty_filter)

    if exclude_question_ids:
        placeholders = ",".join("?" for _ in exclude_question_ids)
        sql += f" AND questions.id NOT IN ({placeholders})"
        params.extend(exclude_question_ids)

    sql += """
    ORDER BY RANDOM()
    LIMIT 1
    """

    cursor.execute(sql, params)
    question = cursor.fetchone()

    if question is None:
        conn.close()
        return None

    question_dict = make_question_dict(cursor, question)

    conn.close()
    return question_dict


# -----------------------------
# Answer / progress functions
# -----------------------------

def save_user_answer(user_id, question_id, selected_choice_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT is_correct
    FROM choices
    WHERE id = ?
    """, (selected_choice_id,))

    choice_result = cursor.fetchone()

    if choice_result is None:
        conn.close()
        return False

    is_correct = choice_result["is_correct"] == 1

    cursor.execute("""
    INSERT INTO user_answers (
        user_id,
        question_id,
        selected_choice_id,
        is_correct
    )
    VALUES (?, ?, ?, ?)
    """, (
        user_id,
        question_id,
        selected_choice_id,
        1 if is_correct else 0
    ))

    cursor.execute("""
    SELECT grammar_id
    FROM questions
    WHERE id = ?
    """, (question_id,))

    question_result = cursor.fetchone()

    if question_result is None:
        conn.commit()
        conn.close()
        return is_correct

    grammar_id = question_result["grammar_id"]

    cursor.execute("""
    INSERT OR IGNORE INTO review_status (
        user_id,
        grammar_id,
        correct_count,
        wrong_count,
        mastery_level,
        last_reviewed_at
    )
    VALUES (?, ?, 0, 0, 'new', CURRENT_TIMESTAMP)
    """, (user_id, grammar_id))

    if is_correct:
        cursor.execute("""
        UPDATE review_status
        SET
            correct_count = correct_count + 1,
            last_reviewed_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND grammar_id = ?
        """, (user_id, grammar_id))
    else:
        cursor.execute("""
        UPDATE review_status
        SET
            wrong_count = wrong_count + 1,
            last_reviewed_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND grammar_id = ?
        """, (user_id, grammar_id))

    cursor.execute("""
    SELECT correct_count, wrong_count
    FROM review_status
    WHERE user_id = ? AND grammar_id = ?
    """, (user_id, grammar_id))

    status = cursor.fetchone()

    correct_count = status["correct_count"]
    wrong_count = status["wrong_count"]
    total = correct_count + wrong_count

    if total == 0:
        mastery_level = "new"
    else:
        accuracy = correct_count / total * 100

        if wrong_count >= 3 and accuracy < 80:
            mastery_level = "weak"
        elif correct_count >= 5 and accuracy >= 90:
            mastery_level = "mastered"
        elif correct_count >= 1:
            mastery_level = "learning"
        else:
            mastery_level = "new"

    cursor.execute("""
    UPDATE review_status
    SET mastery_level = ?
    WHERE user_id = ? AND grammar_id = ?
    """, (mastery_level, user_id, grammar_id))

    conn.commit()
    conn.close()

    return is_correct


def get_review_progress(user_id, jlpt_level=None, mastery_filter=None, excluded_mastery_levels=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT
        grammar_points.id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.meaning,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        review_status.last_reviewed_at
    FROM grammar_points
    LEFT JOIN review_status
        ON review_status.grammar_id = grammar_points.id
        AND review_status.user_id = ?
    """

    params = [user_id]
    conditions = []

    if jlpt_level is not None:
        conditions.append("grammar_points.jlpt_level = ?")
        params.append(jlpt_level)

    if mastery_filter is not None:
        if isinstance(mastery_filter, (list, tuple, set)):
            mastery_filter = list(mastery_filter)

            if len(mastery_filter) == 0:
                conditions.append("1 = 0")
            else:
                placeholders = ",".join("?" for _ in mastery_filter)
                conditions.append(
                    f"COALESCE(review_status.mastery_level, 'new') IN ({placeholders})"
                )
                params.extend(mastery_filter)
        else:
            conditions.append("COALESCE(review_status.mastery_level, 'new') = ?")
            params.append(mastery_filter)

    elif excluded_mastery_levels:
        excluded_mastery_levels = list(excluded_mastery_levels)
        placeholders = ",".join("?" for _ in excluded_mastery_levels)
        conditions.append(
            f"COALESCE(review_status.mastery_level, 'new') NOT IN ({placeholders})"
        )
        params.extend(excluded_mastery_levels)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += """
    ORDER BY
        grammar_points.jlpt_level,
        CASE COALESCE(review_status.mastery_level, 'new')
            WHEN 'weak' THEN 1
            WHEN 'new' THEN 2
            WHEN 'learning' THEN 3
            WHEN 'mastered' THEN 4
            ELSE 5
        END,
        grammar_points.id
    """

    cursor.execute(sql, params)

    rows = cursor.fetchall()
    conn.close()

    progress = []

    for row in rows:
        item = dict(row)
        total = item["correct_count"] + item["wrong_count"]

        if total == 0:
            item["accuracy"] = None
        else:
            item["accuracy"] = item["correct_count"] / total * 100

        item["total_asked"] = total
        progress.append(item)

    return progress


def search_grammar_points(user_id, keyword):
    conn = get_connection()
    cursor = conn.cursor()

    keyword = f"%{keyword}%"

    cursor.execute("""
    SELECT
        grammar_points.id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.reading,
        grammar_points.romaji,
        grammar_points.meaning,
        grammar_points.formation,
        grammar_points.example_sentence,
        grammar_points.example_translation,
        grammar_points.source,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        review_status.last_reviewed_at
    FROM grammar_points
    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    WHERE
        grammar_points.grammar LIKE ?
        OR grammar_points.reading LIKE ?
        OR grammar_points.romaji LIKE ?
        OR grammar_points.meaning LIKE ?
        OR grammar_points.formation LIKE ?
        OR grammar_points.example_sentence LIKE ?
    ORDER BY
        grammar_points.jlpt_level,
        grammar_points.grammar
    LIMIT 30
    """, (
        user_id,
        keyword,
        keyword,
        keyword,
        keyword,
        keyword,
        keyword,
    ))

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        item = dict(row)

        total = item["correct_count"] + item["wrong_count"]

        if total == 0:
            item["accuracy"] = None
        else:
            item["accuracy"] = item["correct_count"] / total * 100

        item["total_asked"] = total
        results.append(item)

    return results


def reset_user_progress(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM user_answers
    WHERE user_id = ?
    """, (user_id,))

    cursor.execute("""
    DELETE FROM review_status
    WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()


def get_user_dashboard(user_id, jlpt_level=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT COUNT(*) AS total_grammar
    FROM grammar_points
    """

    params = []

    if jlpt_level is not None:
        sql += " WHERE jlpt_level = ?"
        params.append(jlpt_level)

    cursor.execute(sql, params)
    total_grammar = cursor.fetchone()["total_grammar"]

    sql = """
    SELECT COUNT(*) AS total_questions
    FROM questions
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    """

    params = []

    if jlpt_level is not None:
        sql += " WHERE grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    cursor.execute(sql, params)
    total_questions = cursor.fetchone()["total_questions"]

    sql = """
    SELECT
        COUNT(*) AS total_answered,
        COALESCE(SUM(user_answers.is_correct), 0) AS correct_count
    FROM user_answers
    JOIN questions
        ON user_answers.question_id = questions.id
    JOIN grammar_points
        ON questions.grammar_id = grammar_points.id
    WHERE user_answers.user_id = ?
    """

    params = [user_id]

    if jlpt_level is not None:
        sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    cursor.execute(sql, params)

    answer_row = cursor.fetchone()

    total_answered = answer_row["total_answered"]
    correct_count = answer_row["correct_count"]
    wrong_count = total_answered - correct_count

    if total_answered == 0:
        accuracy = None
    else:
        accuracy = correct_count / total_answered * 100

    sql = """
    SELECT
        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        COUNT(*) AS count
    FROM grammar_points
    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    """

    params = [user_id]

    if jlpt_level is not None:
        sql += " WHERE grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    sql += """
    GROUP BY COALESCE(review_status.mastery_level, 'new')
    """

    cursor.execute(sql, params)

    mastery_rows = cursor.fetchall()

    mastery_counts = {
        "new": 0,
        "learning": 0,
        "weak": 0,
        "mastered": 0
    }

    for row in mastery_rows:
        mastery_level = row["mastery_level"]
        count = row["count"]

        if mastery_level in mastery_counts:
            mastery_counts[mastery_level] = count

    conn.close()

    return {
        "jlpt_level": jlpt_level,
        "total_grammar": total_grammar,
        "total_questions": total_questions,
        "total_answered": total_answered,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "accuracy": accuracy,
        "new_count": mastery_counts["new"],
        "learning_count": mastery_counts["learning"],
        "weak_count": mastery_counts["weak"],
        "mastered_count": mastery_counts["mastered"]
    }