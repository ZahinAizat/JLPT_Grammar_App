import os
import random
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    get_all_users,
    get_or_create_user,
    get_user_dashboard,
    get_weighted_question_excluding
)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

COOLDOWN_SIZE = 2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "jlpt_app.db")

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"Database file not found: {DB_PATH}")

def row_to_dict(row):
    if row is None:
        return None

    if isinstance(row, dict):
        return row

    try:
        return dict(row)
    except Exception:
        return {key: row[key] for key in row.keys()}


def get_distractor_choices(correct_grammar_id, limit=3):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id AS grammar_id,
            grammar,
            reading,
            meaning,
            formation,
            example_sentence,
            example_translation
        FROM grammar_points
        WHERE id != ?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (correct_grammar_id, limit)
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_grammar_details(grammar_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id AS grammar_id,
            grammar,
            reading,
            meaning,
            formation,
            example_sentence,
            example_translation
        FROM grammar_points
        WHERE id = ?
        """,
        (grammar_id,)
    )

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def build_web_question(question):
    question = row_to_dict(question)

    if question is None:
        return None

    correct_grammar_id = question["grammar_id"]

    correct_choice = get_grammar_details(correct_grammar_id)

    if correct_choice is None:
        correct_choice = {
            "grammar_id": correct_grammar_id,
            "grammar": question["grammar"],
            "reading": "",
            "meaning": question["meaning"],
            "formation": "",
            "example_sentence": "",
            "example_translation": ""
        }

    distractor_choices = get_distractor_choices(correct_grammar_id, limit=3)

    choices = distractor_choices + [correct_choice]
    random.shuffle(choices)

    question_text = question.get("question_text")

    if not question_text:
        question_text = f"What is the meaning of this grammar point: {question['grammar']}?"

    correct_count = question.get("correct_count", 0)
    wrong_count = question.get("wrong_count", 0)
    asked_count = correct_count + wrong_count

    if asked_count > 0:
        accuracy = round((correct_count / asked_count) * 100)
    else:
        accuracy = 0

    jlpt_level_value = (
        question.get("jlpt_level")
        or question.get("level")
        or ""
    )

    web_question = {
        "question_id": question.get("question_id"),
        "grammar_id": correct_grammar_id,

        "grammar": correct_choice.get("grammar", question["grammar"]),
        "reading": correct_choice.get("reading", ""),
        "meaning": correct_choice.get("meaning", question["meaning"]),
        "formation": correct_choice.get("formation", ""),
        "example_sentence": correct_choice.get("example_sentence", ""),
        "example_translation": correct_choice.get("example_translation", ""),

        "jlpt_level": jlpt_level_value,
        "question_text": question_text,
        "explanation": question.get("explanation", ""),
        "difficulty": question.get("difficulty", ""),
        "mastery_level": question.get("mastery_level", "new"),

        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "asked_count": asked_count,
        "accuracy": accuracy,

        "choices": choices
    }

    return web_question


def get_filtered_question_from_database(
    user_id,
    exclude_question_ids,
    jlpt_level=None,
    difficulty_filter=None,
    mastery_levels=None,
    mastery_filter_mode="include"
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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
    WHERE 1 = 1
    """

    params = [user_id]

    if jlpt_level is not None:
        sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    if difficulty_filter is not None:
        sql += " AND questions.difficulty = ?"
        params.append(difficulty_filter)

    if mastery_levels:
        placeholders = ",".join("?" for _ in mastery_levels)

        if mastery_filter_mode == "exclude":
            sql += f"""
            AND COALESCE(review_status.mastery_level, 'new') NOT IN ({placeholders})
            """
        else:
            sql += f"""
            AND COALESCE(review_status.mastery_level, 'new') IN ({placeholders})
            """

        params.extend(mastery_levels)

    if exclude_question_ids:
        placeholders = ",".join("?" for _ in exclude_question_ids)
        sql += f" AND questions.id NOT IN ({placeholders})"
        params.extend(exclude_question_ids)

    sql += """
    ORDER BY
        CASE COALESCE(review_status.mastery_level, 'new')
            WHEN 'weak' THEN 1
            WHEN 'learning' THEN 2
            WHEN 'new' THEN 3
            WHEN 'mastered' THEN 4
            ELSE 5
        END,
        COALESCE(review_status.wrong_count, 0) DESC,
        RANDOM()
    LIMIT 1
    """

    cur.execute(sql, params)
    row = cur.fetchone()

    conn.close()

    if row is None:
        return None

    return dict(row)


def get_weighted_question_for_web(user_id, jlpt_level=None, difficulty_filter=None):
    recent_question_ids = session.get("recent_question_ids", [])
    mastery_levels = session.get("quiz_mastery_levels", [])
    mastery_filter_mode = session.get("quiz_mastery_filter_mode", "include")

    question = get_filtered_question_from_database(
        user_id=user_id,
        exclude_question_ids=recent_question_ids,
        jlpt_level=jlpt_level,
        difficulty_filter=difficulty_filter,
        mastery_levels=mastery_levels,
        mastery_filter_mode=mastery_filter_mode
    )

    question = row_to_dict(question)

    if question is None and recent_question_ids:
        session["recent_question_ids"] = []

        question = get_filtered_question_from_database(
            user_id=user_id,
            exclude_question_ids=[],
            jlpt_level=jlpt_level,
            difficulty_filter=difficulty_filter,
            mastery_levels=mastery_levels,
            mastery_filter_mode=mastery_filter_mode
        )

        question = row_to_dict(question)

    return build_web_question(question)


def calculate_mastery_level(correct_count, wrong_count):
    total = correct_count + wrong_count

    if total == 0:
        return "new"

    accuracy = correct_count / total * 100

    if wrong_count >= 3 and accuracy < 80:
        return "weak"
    elif correct_count >= 5 and accuracy >= 90:
        return "mastered"
    elif correct_count >= 1:
        return "learning"
    else:
        return "new"


def ensure_web_answer_history_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS web_answer_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER,
            correct_grammar_id INTEGER NOT NULL,
            selected_grammar_id INTEGER,
            is_correct INTEGER NOT NULL,
            answered_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def save_web_user_answer(user_id, question_id, correct_grammar_id, selected_grammar_id, is_correct):
    ensure_web_answer_history_table()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Save answer history
    cur.execute(
        """
        INSERT INTO web_answer_history (
            user_id,
            question_id,
            correct_grammar_id,
            selected_grammar_id,
            is_correct,
            answered_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            user_id,
            question_id,
            correct_grammar_id,
            selected_grammar_id,
            1 if is_correct else 0
        )
    )

    # Make sure review_status row exists
    cur.execute(
        """
        INSERT OR IGNORE INTO review_status (
            user_id,
            grammar_id,
            correct_count,
            wrong_count,
            mastery_level,
            last_reviewed_at
        )
        VALUES (?, ?, 0, 0, 'new', CURRENT_TIMESTAMP)
        """,
        (user_id, correct_grammar_id)
    )

    if is_correct:
        cur.execute(
            """
            UPDATE review_status
            SET
                correct_count = correct_count + 1,
                last_reviewed_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND grammar_id = ?
            """,
            (user_id, correct_grammar_id)
        )
    else:
        cur.execute(
            """
            UPDATE review_status
            SET
                wrong_count = wrong_count + 1,
                last_reviewed_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND grammar_id = ?
            """,
            (user_id, correct_grammar_id)
        )

    cur.execute(
        """
        SELECT correct_count, wrong_count
        FROM review_status
        WHERE user_id = ? AND grammar_id = ?
        """,
        (user_id, correct_grammar_id)
    )

    status = cur.fetchone()

    correct_count = status["correct_count"]
    wrong_count = status["wrong_count"]

    mastery_level = calculate_mastery_level(correct_count, wrong_count)

    cur.execute(
        """
        UPDATE review_status
        SET mastery_level = ?
        WHERE user_id = ? AND grammar_id = ?
        """,
        (mastery_level, user_id, correct_grammar_id)
    )

    conn.commit()
    conn.close()

    return mastery_level


def update_recent_questions(question_id):
    if question_id is None:
        return

    recent_question_ids = session.get("recent_question_ids", [])
    recent_question_ids.append(question_id)
    recent_question_ids = recent_question_ids[-COOLDOWN_SIZE:]

    session["recent_question_ids"] = recent_question_ids


def read_quiz_settings_from_form():
    selected_jlpt_level = request.form.get("jlpt_level", "all")
    selected_difficulty = request.form.get("difficulty", "all")
    selected_question_count = request.form.get("question_count", "5")
    selected_mastery_levels = request.form.getlist("mastery_levels")
    mastery_filter_mode = request.form.get("mastery_filter_mode", "include")

    if selected_jlpt_level == "all":
        selected_jlpt_level = None

    if selected_difficulty == "all":
        selected_difficulty = None

    if selected_question_count == "unlimited":
        question_limit = None
    else:
        question_limit = int(selected_question_count)

    session["quiz_jlpt_level"] = selected_jlpt_level
    session["quiz_difficulty"] = selected_difficulty
    session["quiz_question_limit"] = question_limit
    session["quiz_mastery_levels"] = selected_mastery_levels
    session["quiz_mastery_filter_mode"] = mastery_filter_mode

    session["quiz_answered_count"] = 0
    session["recent_question_ids"] = []

    session["quiz_session_correct"] = 0
    session["quiz_session_wrong"] = 0

def get_dashboard_details(user_id, jlpt_level=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    grammar_filter_sql = ""
    grammar_filter_params = []

    if jlpt_level is not None:
        grammar_filter_sql = "WHERE grammar_points.jlpt_level = ?"
        grammar_filter_params.append(jlpt_level)

    cur.execute(
        f"""
        SELECT COUNT(*) AS total_grammar
        FROM grammar_points
        {grammar_filter_sql}
        """,
        grammar_filter_params
    )
    total_grammar = cur.fetchone()["total_grammar"]

    cur.execute(
        f"""
        SELECT COUNT(*) AS total_questions
        FROM questions
        JOIN grammar_points
            ON questions.grammar_id = grammar_points.id
        {grammar_filter_sql}
        """,
        grammar_filter_params
    )
    total_questions = cur.fetchone()["total_questions"]

    answer_filter_sql = ""
    answer_filter_params = [user_id]

    if jlpt_level is not None:
        answer_filter_sql = "AND grammar_points.jlpt_level = ?"
        answer_filter_params.append(jlpt_level)

    cur.execute(
        f"""
        SELECT
            COALESCE(SUM(review_status.correct_count), 0) AS correct,
            COALESCE(SUM(review_status.wrong_count), 0) AS wrong
        FROM review_status
        JOIN grammar_points
            ON review_status.grammar_id = grammar_points.id
        WHERE review_status.user_id = ?
        {answer_filter_sql}
        """,
        answer_filter_params
    )

    answer_row = cur.fetchone()

    correct = answer_row["correct"]
    wrong = answer_row["wrong"]
    total_answered = correct + wrong

    if total_answered > 0:
        accuracy = round((correct / total_answered) * 100, 1)
    else:
        accuracy = 0

    mastery_filter_sql = ""
    mastery_filter_params = [user_id]

    if jlpt_level is not None:
        mastery_filter_sql = "WHERE grammar_points.jlpt_level = ?"
        mastery_filter_params.append(jlpt_level)

    cur.execute(
        f"""
        SELECT
            COALESCE(review_status.mastery_level, 'new') AS mastery_level,
            COUNT(*) AS count
        FROM grammar_points
        LEFT JOIN review_status
            ON grammar_points.id = review_status.grammar_id
            AND review_status.user_id = ?
        {mastery_filter_sql}
        GROUP BY COALESCE(review_status.mastery_level, 'new')
        """,
        mastery_filter_params
    )

    mastery_counts = {
        "new": 0,
        "learning": 0,
        "weak": 0,
        "mastered": 0
    }

    for row in cur.fetchall():
        mastery_level = row["mastery_level"]
        mastery_counts[mastery_level] = row["count"]

    conn.close()

    mastery_summary = {}

    for level_name, count in mastery_counts.items():
        if total_grammar > 0:
            percent = round((count / total_grammar) * 100, 1)
        else:
            percent = 0

        mastery_summary[level_name] = {
            "count": count,
            "percent": percent
        }

    return {
        "selected_level": jlpt_level if jlpt_level is not None else "All levels",
        "total_grammar": total_grammar,
        "total_questions": total_questions,
        "total_answered": total_answered,
        "correct": correct,
        "wrong": wrong,
        "accuracy": accuracy,
        "mastery": mastery_summary
    }


def search_grammar_database(user_id, keyword="", jlpt_level=None, limit=50):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = """
    SELECT
        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.reading,
        grammar_points.meaning,
        grammar_points.formation,
        grammar_points.example_sentence,
        grammar_points.example_translation,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count
    FROM grammar_points
    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?
    WHERE 1 = 1
    """

    params = [user_id]

    if jlpt_level is not None:
        sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    if keyword:
        sql += """
        AND (
            grammar_points.grammar LIKE ?
            OR grammar_points.reading LIKE ?
            OR grammar_points.meaning LIKE ?
            OR grammar_points.formation LIKE ?
            OR grammar_points.example_sentence LIKE ?
            OR grammar_points.example_translation LIKE ?
        )
        """

        like_keyword = f"%{keyword}%"

        params.extend([
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword
        ])

    sql += """
    ORDER BY
        CASE grammar_points.jlpt_level
            WHEN 'N1' THEN 1
            WHEN 'N2' THEN 2
            ELSE 3
        END,
        grammar_points.grammar
    LIMIT ?
    """

    params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()

    conn.close()

    results = []

    for row in rows:
        item = dict(row)

        correct_count = item["correct_count"]
        wrong_count = item["wrong_count"]
        total_answered = correct_count + wrong_count

        if total_answered > 0:
            accuracy = round((correct_count / total_answered) * 100, 1)
        else:
            accuracy = 0

        item["total_answered"] = total_answered
        item["accuracy"] = accuracy

        results.append(item)

    return results


def get_question_history(
    user_id,
    page=1,
    per_page=20,
    status_filter="all",
    jlpt_level="all",
    difficulty="all",
    mastery="all",
    date_from="",
    date_to="",
    sort_by="answered_at",
    sort_order="desc"
):
    ensure_web_answer_history_table()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where_sql = """
    WHERE web_answer_history.user_id = ?
    """

    where_params = [user_id]

    if status_filter == "correct":
        where_sql += " AND web_answer_history.is_correct = 1"
    elif status_filter == "wrong":
        where_sql += " AND web_answer_history.is_correct = 0"

    if jlpt_level != "all":
        where_sql += " AND correct_gp.jlpt_level = ?"
        where_params.append(jlpt_level)

    if difficulty != "all":
        where_sql += " AND questions.difficulty = ?"
        where_params.append(difficulty)

    if mastery != "all":
        where_sql += " AND COALESCE(review_status.mastery_level, 'new') = ?"
        where_params.append(mastery)

    if date_from:
        where_sql += " AND DATE(web_answer_history.answered_at) >= DATE(?)"
        where_params.append(date_from)

    if date_to:
        where_sql += " AND DATE(web_answer_history.answered_at) <= DATE(?)"
        where_params.append(date_to)

    sort_options = {
        "answered_at": "web_answer_history.answered_at",
        "status": "web_answer_history.is_correct",
        "jlpt_level": "correct_gp.jlpt_level",
        "difficulty": "questions.difficulty",
        "mastery": """
            CASE COALESCE(review_status.mastery_level, 'new')
                WHEN 'new' THEN 1
                WHEN 'learning' THEN 2
                WHEN 'weak' THEN 3
                WHEN 'mastered' THEN 4
                ELSE 5
            END
        """,
        "appeared_count": "COALESCE(appearance_counts.appeared_count, 0)",
        "grammar": "correct_gp.grammar"
    }

    order_column = sort_options.get(sort_by, "web_answer_history.answered_at")

    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"

    order_direction = sort_order.upper()

    offset = (page - 1) * per_page

    # Count total matching rows
    count_sql = f"""
    SELECT COUNT(*) AS total_count

    FROM web_answer_history

    LEFT JOIN questions
        ON web_answer_history.question_id = questions.id

    JOIN grammar_points AS correct_gp
        ON web_answer_history.correct_grammar_id = correct_gp.id

    LEFT JOIN review_status
        ON review_status.user_id = ?
        AND review_status.grammar_id = correct_gp.id

    {where_sql}
    """

    count_params = [user_id] + where_params

    cur.execute(count_sql, count_params)
    total_count = cur.fetchone()["total_count"]

    # Get paginated history rows
    sql = f"""
    SELECT
        web_answer_history.id,
        web_answer_history.answered_at,
        web_answer_history.is_correct,

        questions.question_text,
        questions.difficulty,

        correct_gp.jlpt_level AS jlpt_level,
        correct_gp.grammar AS correct_grammar,
        correct_gp.reading AS correct_reading,
        correct_gp.meaning AS correct_meaning,
        correct_gp.formation AS correct_formation,
        correct_gp.example_sentence AS correct_example_sentence,
        correct_gp.example_translation AS correct_example_translation,

        selected_gp.grammar AS selected_grammar,
        selected_gp.reading AS selected_reading,
        selected_gp.meaning AS selected_meaning,
        selected_gp.formation AS selected_formation,
        selected_gp.example_sentence AS selected_example_sentence,
        selected_gp.example_translation AS selected_example_translation,

        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,

        COALESCE(appearance_counts.appeared_count, 0) AS appeared_count

    FROM web_answer_history

    LEFT JOIN questions
        ON web_answer_history.question_id = questions.id

    JOIN grammar_points AS correct_gp
        ON web_answer_history.correct_grammar_id = correct_gp.id

    LEFT JOIN grammar_points AS selected_gp
        ON web_answer_history.selected_grammar_id = selected_gp.id

    LEFT JOIN review_status
        ON review_status.user_id = ?
        AND review_status.grammar_id = correct_gp.id

    LEFT JOIN (
        SELECT
            correct_grammar_id,
            COUNT(*) AS appeared_count
        FROM web_answer_history
        WHERE user_id = ?
        GROUP BY correct_grammar_id
    ) AS appearance_counts
        ON appearance_counts.correct_grammar_id = correct_gp.id

    {where_sql}

    ORDER BY {order_column} {order_direction}, web_answer_history.answered_at DESC

    LIMIT ?
    OFFSET ?
    """

    params = [user_id, user_id] + where_params + [per_page, offset]

    cur.execute(sql, params)
    rows = cur.fetchall()

    conn.close()

    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return {
        "rows": [dict(row) for row in rows],
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }
    

def get_statistics_data(user_id):
    ensure_web_answer_history_table()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Overall answer summary from WEB history only
    cur.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct,
            COALESCE(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END), 0) AS wrong
        FROM web_answer_history
        WHERE user_id = ?
        """,
        (user_id,)
    )

    overall_row = cur.fetchone()

    correct = overall_row["correct"]
    wrong = overall_row["wrong"]
    total_answered = correct + wrong

    if total_answered > 0:
        overall_accuracy = round((correct / total_answered) * 100, 1)
    else:
        overall_accuracy = 0

    # Mastery distribution
    cur.execute(
        """
        SELECT
            COALESCE(review_status.mastery_level, 'new') AS mastery_level,
            COUNT(*) AS count
        FROM grammar_points
        LEFT JOIN review_status
            ON grammar_points.id = review_status.grammar_id
            AND review_status.user_id = ?
        GROUP BY COALESCE(review_status.mastery_level, 'new')
        """,
        (user_id,)
    )

    mastery_counts = {
        "new": 0,
        "learning": 0,
        "weak": 0,
        "mastered": 0
    }

    for row in cur.fetchall():
        mastery_counts[row["mastery_level"]] = row["count"]

    total_grammar = sum(mastery_counts.values())

    mastery_graph = []

    for mastery_level, count in mastery_counts.items():
        if total_grammar > 0:
            percent = round((count / total_grammar) * 100, 1)
        else:
            percent = 0

        mastery_graph.append({
            "label": mastery_level,
            "count": count,
            "percent": percent
        })

    # Accuracy by JLPT level from WEB history only
    cur.execute(
        """
        SELECT
            grammar_points.jlpt_level,
            SUM(CASE WHEN web_answer_history.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN web_answer_history.is_correct = 0 THEN 1 ELSE 0 END) AS wrong
        FROM web_answer_history
        JOIN grammar_points
            ON web_answer_history.correct_grammar_id = grammar_points.id
        WHERE web_answer_history.user_id = ?
        GROUP BY grammar_points.jlpt_level
        ORDER BY grammar_points.jlpt_level
        """,
        (user_id,)
    )

    level_graph = []

    for row in cur.fetchall():
        level_correct = row["correct"]
        level_wrong = row["wrong"]
        level_total = level_correct + level_wrong

        if level_total > 0:
            level_accuracy = round((level_correct / level_total) * 100, 1)
        else:
            level_accuracy = 0

        level_graph.append({
            "label": row["jlpt_level"],
            "correct": level_correct,
            "wrong": level_wrong,
            "total": level_total,
            "accuracy": level_accuracy
        })
        
        
    # Accuracy by difficulty from WEB history only
    cur.execute(
        """
        SELECT
            questions.difficulty,
            SUM(CASE WHEN web_answer_history.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN web_answer_history.is_correct = 0 THEN 1 ELSE 0 END) AS wrong
        FROM web_answer_history
        JOIN questions
            ON web_answer_history.question_id = questions.id
        WHERE web_answer_history.user_id = ?
        GROUP BY questions.difficulty
        ORDER BY
            CASE questions.difficulty
                WHEN 'easy' THEN 1
                WHEN 'normal' THEN 2
                WHEN 'hard' THEN 3
                ELSE 4
            END
        """,
        (user_id,)
    )

    difficulty_graph = []

    for row in cur.fetchall():
        difficulty_correct = row["correct"]
        difficulty_wrong = row["wrong"]
        difficulty_total = difficulty_correct + difficulty_wrong

        if difficulty_total > 0:
            difficulty_accuracy = round((difficulty_correct / difficulty_total) * 100, 1)
        else:
            difficulty_accuracy = 0

        difficulty_graph.append({
            "label": row["difficulty"],
            "correct": difficulty_correct,
            "wrong": difficulty_wrong,
            "total": difficulty_total,
            "accuracy": difficulty_accuracy
        })        
    known_difficulty_correct = sum(item["correct"] for item in difficulty_graph)
    known_difficulty_wrong = sum(item["wrong"] for item in difficulty_graph)

    missing_correct = correct - known_difficulty_correct
    missing_wrong = wrong - known_difficulty_wrong

    if missing_correct > 0 or missing_wrong > 0:
        missing_total = missing_correct + missing_wrong

        if missing_total > 0:
            missing_accuracy = round((missing_correct / missing_total) * 100, 1)
        else:
            missing_accuracy = 0

        difficulty_graph.append({
            "label": "unknown / old data",
            "correct": missing_correct,
            "wrong": missing_wrong,
            "total": missing_total,
            "accuracy": missing_accuracy
        })

    conn.close()

    return {
        "correct": correct,
        "wrong": wrong,
        "total_answered": total_answered,
        "overall_accuracy": overall_accuracy,
        "mastery_graph": mastery_graph,
        "level_graph": level_graph,
        "difficulty_graph": difficulty_graph
    }
 
def get_current_session_stats():
    session_correct = session.get("quiz_session_correct", 0)
    session_wrong = session.get("quiz_session_wrong", 0)

    session_total = session_correct + session_wrong

    if session_total > 0:
        session_accuracy = round((session_correct / session_total) * 100, 1)
    else:
        session_accuracy = 0

    return session_correct, session_wrong, session_accuracy

def reset_web_progress(user_id, reset_scope):
    ensure_web_answer_history_table()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if reset_scope == "all":
        cur.execute(
            """
            DELETE FROM web_answer_history
            WHERE user_id = ?
            """,
            (user_id,)
        )

        cur.execute(
            """
            DELETE FROM review_status
            WHERE user_id = ?
            """,
            (user_id,)
        )

    elif reset_scope in ["N1", "N2"]:
        cur.execute(
            """
            DELETE FROM web_answer_history
            WHERE user_id = ?
            AND correct_grammar_id IN (
                SELECT id
                FROM grammar_points
                WHERE jlpt_level = ?
            )
            """,
            (user_id, reset_scope)
        )

        cur.execute(
            """
            DELETE FROM review_status
            WHERE user_id = ?
            AND grammar_id IN (
                SELECT id
                FROM grammar_points
                WHERE jlpt_level = ?
            )
            """,
            (user_id, reset_scope)
        )

    conn.commit()
    conn.close()


def create_account(username, password):
    ensure_user_account_columns()

    username = username.strip()

    if not username:
        return False, "Username cannot be empty."

    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    existing_user = get_user_by_username(username)

    if existing_user is not None:
        return False, "Username already exists."

    password_hash = generate_password_hash(password)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (username, password_hash, created_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (username, password_hash)
    )

    conn.commit()
    conn.close()

    return True, "Account created successfully."


def login_account(username, password):
    user = get_user_by_username(username.strip())

    if user is None:
        return False, "Username or password is incorrect.", None

    if not user.get("password_hash"):
        return False, "This old user does not have a password yet. Please register a new account or migrate this user later.", None

    if not check_password_hash(user["password_hash"], password):
        return False, "Username or password is incorrect.", None

    return True, "Login successful.", user


def delete_account_with_password(user_id, password):
    ensure_user_account_columns()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, username, password_hash
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )

    user = cur.fetchone()

    if user is None:
        conn.close()
        return False, "Account not found."

    if not user["password_hash"]:
        conn.close()
        return False, "This account does not have a password set yet."

    if not check_password_hash(user["password_hash"], password):
        conn.close()
        return False, "Password is incorrect."

    # Delete progress/history first
    cur.execute(
        """
        DELETE FROM web_answer_history
        WHERE user_id = ?
        """,
        (user_id,)
    )

    cur.execute(
        """
        DELETE FROM review_status
        WHERE user_id = ?
        """,
        (user_id,)
    )

    # Old/local answer records, if they exist for this user
    cur.execute(
        """
        DELETE FROM user_answers
        WHERE user_id = ?
        """,
        (user_id,)
    )

    # Finally delete the user account
    cur.execute(
        """
        DELETE FROM users
        WHERE id = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()

    return True, "Account deleted successfully."


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/select_user", methods=["POST"])
def select_user():
    username = request.form.get("username", "").strip()

    if username == "":
        return redirect(url_for("index"))

    user = get_or_create_user(username)

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["recent_question_ids"] = []

    return redirect(url_for("dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    success = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            error = "Passwords do not match."
        else:
            ok, message = create_account(username, password)

            if ok:
                success = message
            else:
                error = message

    return render_template(
        "register.html",
        error=error,
        success=success
    )


@app.route("/login", methods=["POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    ok, message, user = login_account(username, password)

    if not ok:
        return render_template(
            "login.html",
            error=message
        )

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))

    selected_level = request.args.get("jlpt_level", "all")

    if selected_level == "all":
        selected_level = None

    dashboard_data = get_dashboard_details(
        session["user_id"],
        selected_level
    )

    return render_template(
        "dashboard.html",
        username=session["username"],
        dashboard=dashboard_data
    )


@app.route("/quiz/weighted/setup")
def weighted_quiz_setup():
    if "user_id" not in session:
        return redirect(url_for("index"))

    return render_template(
        "quiz_setup.html",
        username=session["username"],
        quiz_type="Start Quiz",
        start_url=url_for("weighted_quiz_start")
    )


@app.route("/quiz/weighted/start", methods=["POST"])
def weighted_quiz_start():
    if "user_id" not in session:
        return redirect(url_for("index"))

    read_quiz_settings_from_form()

    session["quiz_title"] = "Quiz"
    session["quiz_setup_endpoint"] = "weighted_quiz_setup"
    session["current_next_quiz_endpoint"] = "weighted_quiz"

    return redirect(url_for("weighted_quiz"))


@app.route("/quiz/weighted")
def weighted_quiz():
    if "user_id" not in session:
        return redirect(url_for("index"))

    user_id = session["user_id"]

    question_limit = session.get("quiz_question_limit")
    answered_count = session.get("quiz_answered_count", 0)

    if question_limit is not None and answered_count >= question_limit:
        return redirect(url_for("quiz_finish"))

    jlpt_level = session.get("quiz_jlpt_level")
    difficulty_filter = session.get("quiz_difficulty")

    question = get_weighted_question_for_web(
        user_id,
        jlpt_level,
        difficulty_filter
    )

    if question is None:
        return render_template("no_question.html")

    session["current_question"] = question
    session["current_next_quiz_endpoint"] = "weighted_quiz"

    session_correct, session_wrong, session_accuracy = get_current_session_stats()

    return render_template(
        "quiz.html",
        username=session["username"],
        quiz_title="Quiz",
        question=question,
        answered_count=answered_count,
        question_limit=question_limit,
        session_correct=session_correct,
        session_wrong=session_wrong,
        session_accuracy=session_accuracy
    )


@app.route("/quiz/answer", methods=["POST"])
def quiz_answer():
    if "user_id" not in session:
        return redirect(url_for("index"))

    question = session.get("current_question")

    if question is None:
        return redirect(url_for("weighted_quiz"))

    choice_index_text = request.form.get("choice_index", "-1")

    try:
        choice_index = int(choice_index_text)
    except ValueError:
        choice_index = -1

    selected_choice = None

    if 0 <= choice_index < len(question["choices"]):
        selected_choice = question["choices"][choice_index]

    is_correct = False

    if selected_choice is not None:
        is_correct = selected_choice["grammar_id"] == question["grammar_id"]

    selected_grammar_id = None

    if selected_choice is not None:
        selected_grammar_id = selected_choice["grammar_id"]

    new_mastery_level = save_web_user_answer(
        session["user_id"],
        question.get("question_id"),
        question["grammar_id"],
        selected_grammar_id,
        is_correct
    )

    question["mastery_level"] = new_mastery_level

    update_recent_questions(question.get("question_id"))

    answered_count = session.get("quiz_answered_count", 0) + 1
    session["quiz_answered_count"] = answered_count
    
    session_correct = session.get("quiz_session_correct", 0)
    session_wrong = session.get("quiz_session_wrong", 0)

    if is_correct:
        session_correct += 1
    else:
        session_wrong += 1

    session["quiz_session_correct"] = session_correct
    session["quiz_session_wrong"] = session_wrong

    session_total = session_correct + session_wrong

    if session_total > 0:
        session_accuracy = round((session_correct / session_total) * 100, 1)
    else:
        session_accuracy = 0

    question_limit = session.get("quiz_question_limit")

    is_finished = False
    if question_limit is not None and answered_count >= question_limit:
        is_finished = True

    session_correct, session_wrong, session_accuracy = get_current_session_stats()

    return render_template(
        "feedback.html",
        username=session["username"],
        question=question,
        selected_choice=selected_choice,
        is_correct=is_correct,
        answered_count=answered_count,
        question_limit=question_limit,
        is_finished=is_finished,
        next_quiz_endpoint=session.get("current_next_quiz_endpoint", "weighted_quiz"),
        session_correct=session_correct,
        session_wrong=session_wrong,
        session_accuracy=session_accuracy

    )


@app.route("/quiz/finish")
def quiz_finish():
    if "user_id" not in session:
        return redirect(url_for("index"))

    answered_count = session.get("quiz_answered_count", 0)
    question_limit = session.get("quiz_question_limit")
    quiz_title = session.get("quiz_title", "Quiz")
    quiz_setup_endpoint = session.get("quiz_setup_endpoint", "weighted_quiz_setup")

    session_correct = session.get("quiz_session_correct", 0)
    session_wrong = session.get("quiz_session_wrong", 0)

    session_total = session_correct + session_wrong

    if session_total > 0:
        session_accuracy = round((session_correct / session_total) * 100, 1)
    else:
        session_accuracy = 0
    
    session_correct, session_wrong, session_accuracy = get_current_session_stats()
    
    return render_template(
        "quiz_finish.html",
        username=session["username"],
        answered_count=answered_count,
        question_limit=question_limit,
        quiz_title=quiz_title,
        quiz_setup_endpoint=quiz_setup_endpoint,
        session_correct=session_correct,
        session_wrong=session_wrong,
        session_accuracy=session_accuracy,
    )


@app.route("/search")
def search_grammar():
    if "user_id" not in session:
        return redirect(url_for("index"))

    keyword = request.args.get("q", "").strip()
    selected_level = request.args.get("jlpt_level", "all")

    if selected_level == "all":
        jlpt_level = None
    else:
        jlpt_level = selected_level

    results = []

    if keyword or selected_level != "all":
        results = search_grammar_database(
        user_id=session["user_id"],
        keyword=keyword,
        jlpt_level=jlpt_level,
        limit=100
    )

    return render_template(
        "search.html",
        username=session["username"],
        keyword=keyword,
        selected_level=selected_level,
        results=results
    )


@app.route("/history")
def question_history():
    if "user_id" not in session:
        return redirect(url_for("index"))

    page = 1

    status_filter = request.args.get("status", "all")
    jlpt_level = request.args.get("jlpt_level", "all")
    difficulty = request.args.get("difficulty", "all")
    mastery = request.args.get("mastery", "all")
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    sort_by = request.args.get("sort_by", "answered_at")
    sort_order = request.args.get("sort_order", "desc")

    history_data = get_question_history(
        user_id=session["user_id"],
        page=page,
        per_page=1000,
        status_filter=status_filter,
        jlpt_level=jlpt_level,
        difficulty=difficulty,
        mastery=mastery,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order
    )

    return render_template(
        "history.html",
        username=session["username"],
        history=history_data["rows"],
        total_count=history_data["total_count"],
        page=history_data["page"],
        total_pages=history_data["total_pages"],
        status_filter=status_filter,
        selected_level=jlpt_level,
        selected_difficulty=difficulty,
        selected_mastery=mastery,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order
    )


def get_mastery_grammar_details(
    user_id,
    mastery="all",
    jlpt_level="all",
    sort_by="grammar",
    sort_order="asc"
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where_sql = "WHERE 1 = 1"
    params = [user_id]

    if mastery != "all":
        where_sql += " AND COALESCE(review_status.mastery_level, 'new') = ?"
        params.append(mastery)

    if jlpt_level != "all":
        where_sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    sort_options = {
        "grammar": "grammar_points.grammar",
        "jlpt_level": "grammar_points.jlpt_level",
        "mastery": """
            CASE COALESCE(review_status.mastery_level, 'new')
                WHEN 'new' THEN 1
                WHEN 'learning' THEN 2
                WHEN 'weak' THEN 3
                WHEN 'mastered' THEN 4
                ELSE 5
            END
        """,
        "correct_count": "COALESCE(review_status.correct_count, 0)",
        "wrong_count": "COALESCE(review_status.wrong_count, 0)",
        "accuracy": """
            CASE
                WHEN COALESCE(review_status.correct_count, 0) + COALESCE(review_status.wrong_count, 0) = 0
                THEN 0
                ELSE
                    CAST(COALESCE(review_status.correct_count, 0) AS REAL)
                    / (COALESCE(review_status.correct_count, 0) + COALESCE(review_status.wrong_count, 0))
            END
        """,
        "last_reviewed": "review_status.last_reviewed_at"
    }

    order_column = sort_options.get(sort_by, "grammar_points.grammar")

    if sort_order not in ["asc", "desc"]:
        sort_order = "asc"

    order_direction = sort_order.upper()

    sql = f"""
    SELECT
        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.reading,
        grammar_points.meaning,
        grammar_points.formation,
        grammar_points.example_sentence,
        grammar_points.example_translation,

        COALESCE(review_status.correct_count, 0) AS correct_count,
        COALESCE(review_status.wrong_count, 0) AS wrong_count,
        COALESCE(review_status.mastery_level, 'new') AS mastery_level,
        review_status.last_reviewed_at

    FROM grammar_points

    LEFT JOIN review_status
        ON grammar_points.id = review_status.grammar_id
        AND review_status.user_id = ?

    {where_sql}

    ORDER BY {order_column} {order_direction}
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    results = []

    for row in rows:
        item = dict(row)

        correct_count = item["correct_count"]
        wrong_count = item["wrong_count"]
        total = correct_count + wrong_count

        if total > 0:
            accuracy = round((correct_count / total) * 100, 1)
        else:
            accuracy = 0

        item["total_answered"] = total
        item["accuracy"] = accuracy

        results.append(item)

    return results


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


def get_user_by_username(username):
    ensure_user_account_columns()

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
    conn.close()

    if user is None:
        return None

    return dict(user)


@app.route("/statistics")
def statistics():
    if "user_id" not in session:
        return redirect(url_for("index"))

    stats = get_statistics_data(session["user_id"])

    return render_template(
        "statistics.html",
        username=session["username"],
        stats=stats
    )


@app.route("/reset")
def reset_page():
    if "user_id" not in session:
        return redirect(url_for("index"))

    return render_template(
        "reset.html",
        username=session["username"]
    )
    
@app.route("/reset/confirm", methods=["POST"])
def reset_confirm():
    if "user_id" not in session:
        return redirect(url_for("index"))

    reset_scope = request.form.get("reset_scope", "")

    if reset_scope not in ["all", "N1", "N2"]:
        return redirect(url_for("reset_page"))

    return render_template(
        "reset_confirm.html",
        username=session["username"],
        reset_scope=reset_scope
    )

@app.route("/reset/do", methods=["POST"])
def reset_do():
    if "user_id" not in session:
        return redirect(url_for("index"))

    reset_scope = request.form.get("reset_scope", "")

    if reset_scope not in ["all", "N1", "N2"]:
        return redirect(url_for("reset_page"))

    reset_web_progress(session["user_id"], reset_scope)

    session["recent_question_ids"] = []
    session["quiz_answered_count"] = 0
    session["quiz_session_correct"] = 0
    session["quiz_session_wrong"] = 0

    return render_template(
        "reset_done.html",
        username=session["username"],
        reset_scope=reset_scope
    )

@app.route("/mastery-explanation")
def mastery_explanation():
    if "user_id" not in session:
        return redirect(url_for("index"))

    return render_template(
        "mastery_explanation.html",
        username=session["username"]
    )

@app.route("/question-selection-explanation")
def question_selection_explanation():
    if "user_id" not in session:
        return redirect(url_for("index"))

    return render_template(
        "question_selection_explanation.html",
        username=session["username"]
    )

@app.route("/mastery-details")
def mastery_details():
    if "user_id" not in session:
        return redirect(url_for("index"))

    mastery = request.args.get("mastery", "all")
    jlpt_level = request.args.get("jlpt_level", "all")
    sort_by = request.args.get("sort_by", "grammar")
    sort_order = request.args.get("sort_order", "asc")

    grammar_points = get_mastery_grammar_details(
        user_id=session["user_id"],
        mastery=mastery,
        jlpt_level=jlpt_level,
        sort_by=sort_by,
        sort_order=sort_order
    )

    return render_template(
        "mastery_details.html",
        username=session["username"],
        grammar_points=grammar_points,
        selected_mastery=mastery,
        selected_level=jlpt_level,
        sort_by=sort_by,
        sort_order=sort_order
    )


@app.route("/account")
def account_settings():
    if "user_id" not in session:
        return redirect(url_for("index"))

    return render_template(
        "account.html",
        username=session["username"],
        error=None
    )


@app.route("/account/delete", methods=["POST"])
def delete_account():
    if "user_id" not in session:
        return redirect(url_for("index"))

    password = request.form.get("password", "")
    confirm_text = request.form.get("confirm_text", "").strip()

    if confirm_text != "DELETE":
        return render_template(
            "account.html",
            username=session["username"],
            error="Please type DELETE to confirm account deletion."
        )

    ok, message = delete_account_with_password(
        session["user_id"],
        password
    )

    if not ok:
        return render_template(
            "account.html",
            username=session["username"],
            error=message
        )

    session.clear()

    return render_template(
        "account_deleted.html",
        message=message
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode)