import os
import random
import sqlite3
import html

import re
from markupsafe import Markup, escape

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    get_all_users,
    get_or_create_user,
    get_user_dashboard,
    get_weighted_question_excluding
)


app = Flask(__name__)

@app.template_filter("markdown_note")
def markdown_note_filter(text):
    if text is None:
        return ""

    escaped_text = str(escape(str(text)))
    escaped_text = escaped_text.replace("\r\n", "\n").replace("\r", "\n")

    escaped_text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<strong>\1</strong>",
        escaped_text
    )

    paragraphs = escaped_text.split("\n\n")
    html_parts = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if paragraph:
            paragraph = paragraph.replace("\n", "<br>")
            html_parts.append(f"<p>{paragraph}</p>")

    return Markup("".join(html_parts))

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
        item["note_count"] = get_note_count_for_grammar(user_id, item["grammar_id"])

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
        web_answer_history.correct_grammar_id AS correct_grammar_id,
        web_answer_history.selected_grammar_id AS selected_grammar_id,
        
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
    history_rows = []

    for row in rows:
        item = dict(row)

        item["correct_note_count"] = get_note_count_for_grammar(
            user_id,
            item["correct_grammar_id"]
        )

        if item.get("selected_grammar_id"):
            item["selected_note_count"] = get_note_count_for_grammar(
                user_id,
                item["selected_grammar_id"]
            )
        else:
            item["selected_note_count"] = 0

        history_rows.append(item)

    conn.close()
    
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return {
        "rows": history_rows,
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
        item["note_count"] = get_note_count_for_grammar(user_id, item["grammar_id"])

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


def ensure_notes_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS grammar_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS grammar_note_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        grammar_id INTEGER NOT NULL,
        relation_type TEXT DEFAULT 'related',
        FOREIGN KEY (note_id) REFERENCES grammar_notes(id),
        FOREIGN KEY (grammar_id) REFERENCES grammar_points(id)
    )
    """)

    conn.commit()
    conn.close()


def get_grammar_detail(grammar_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT
        id AS grammar_id,
        jlpt_level,
        grammar,
        reading,
        meaning,
        formation,
        example_sentence,
        example_translation
    FROM grammar_points
    WHERE id = ?
    """, (grammar_id,))

    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def get_question_explanations_for_grammar(grammar_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT
        id AS question_id,
        question_text,
        explanation,
        difficulty
    FROM questions
    WHERE grammar_id = ?
    ORDER BY
        CASE difficulty
            WHEN 'easy' THEN 1
            WHEN 'normal' THEN 2
            WHEN 'hard' THEN 3
            ELSE 4
        END
    LIMIT 3
    """, (grammar_id,))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_notes_for_grammar(user_id, grammar_id):
    ensure_notes_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT
        grammar_notes.id AS note_id,
        grammar_notes.title,
        grammar_notes.content,
        grammar_notes.created_at,
        grammar_notes.updated_at,
        grammar_note_links.relation_type
    FROM grammar_notes
    JOIN grammar_note_links
        ON grammar_notes.id = grammar_note_links.note_id
    WHERE grammar_notes.user_id = ?
      AND grammar_note_links.grammar_id = ?
    ORDER BY grammar_notes.updated_at DESC
    """, (user_id, grammar_id))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_all_notes_for_user(
    user_id,
    keyword="",
    relation_type="all",
    jlpt_level="all",
    connection_filter="all",
    sort_by="updated_desc"
):
    ensure_notes_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where_sql = """
    WHERE grammar_notes.user_id = ?
    """

    params = [user_id]

    keyword = keyword.strip()

    if keyword:
        where_sql += """
        AND (
            grammar_notes.title LIKE ?
            OR grammar_notes.content LIKE ?
            OR grammar_points.grammar LIKE ?
            OR grammar_points.reading LIKE ?
            OR grammar_points.meaning LIKE ?
        )
        """

        like_keyword = f"%{keyword}%"

        params.extend([
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword
        ])

    if relation_type != "all":
        where_sql += " AND grammar_note_links.relation_type = ?"
        params.append(relation_type)

    if jlpt_level != "all":
        where_sql += " AND grammar_points.jlpt_level = ?"
        params.append(jlpt_level)

    sort_options = {
        "updated_desc": "grammar_notes.updated_at DESC",
        "updated_asc": "grammar_notes.updated_at ASC",
        "created_desc": "grammar_notes.created_at DESC",
        "created_asc": "grammar_notes.created_at ASC",
        "title_asc": "grammar_notes.title ASC",
        "title_desc": "grammar_notes.title DESC"
    }

    order_sql = sort_options.get(sort_by, "grammar_notes.updated_at DESC")

    sql = f"""
    SELECT
        grammar_notes.id AS note_id,
        grammar_notes.title,
        grammar_notes.content,
        grammar_notes.created_at,
        grammar_notes.updated_at,

        grammar_note_links.relation_type,

        grammar_points.id AS grammar_id,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.reading,
        grammar_points.meaning,
        grammar_points.formation,
        grammar_points.example_sentence,
        grammar_points.example_translation

    FROM grammar_notes

    JOIN grammar_note_links
        ON grammar_notes.id = grammar_note_links.note_id

    JOIN grammar_points
        ON grammar_note_links.grammar_id = grammar_points.id

    {where_sql}

    ORDER BY {order_sql}, grammar_notes.id DESC
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    notes_dict = {}

    for row in rows:
        row = dict(row)
        note_id = row["note_id"]

        if note_id not in notes_dict:
            notes_dict[note_id] = {
                "note_id": note_id,
                "title": row["title"],
                "content": row["content"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "connected_grammar": []
            }

        grammar_id = row["grammar_id"]

        notes_dict[note_id]["connected_grammar"].append({
            "grammar_id": grammar_id,
            "jlpt_level": row["jlpt_level"],
            "grammar": row["grammar"],
            "reading": row["reading"],
            "meaning": row["meaning"],
            "formation": row["formation"],
            "example_sentence": row["example_sentence"],
            "example_translation": row["example_translation"],
            "relation_type": row["relation_type"],
            "question_explanations": get_question_explanations_for_grammar(grammar_id)
        })

    notes = list(notes_dict.values())

    for note in notes:
        note["connection_count"] = len(note["connected_grammar"])

    if connection_filter == "multiple":
        notes = [
            note for note in notes
            if note["connection_count"] >= 2
        ]

    elif connection_filter == "single":
        notes = [
            note for note in notes
            if note["connection_count"] == 1
        ]

    if sort_by == "connection_count_desc":
        notes.sort(key=lambda note: note["connection_count"], reverse=True)

    elif sort_by == "connection_count_asc":
        notes.sort(key=lambda note: note["connection_count"])

    return notes


def create_note_with_links(user_id, title, content, grammar_links):
    """
    grammar_links should be a list of dictionaries:
    [
        {"grammar_id": 1, "relation_type": "related"},
        {"grammar_id": 2, "relation_type": "opposite"}
    ]
    """

    ensure_notes_tables()

    title = title.strip()
    content = content.strip()

    if not title:
        return False, "Note title cannot be empty."

    if not content:
        return False, "Note content cannot be empty."

    if not grammar_links:
        return False, "Please connect the note to at least one grammar point."

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO grammar_notes (
        user_id,
        title,
        content,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (user_id, title, content))

    note_id = cur.lastrowid

    for link in grammar_links:
        grammar_id = link["grammar_id"]
        relation_type = link.get("relation_type", "related")

        cur.execute("""
        INSERT INTO grammar_note_links (
            note_id,
            grammar_id,
            relation_type
        )
        VALUES (?, ?, ?)
        """, (note_id, grammar_id, relation_type))

    conn.commit()
    conn.close()

    return True, "Note created successfully."


def search_grammar_for_note_link(keyword="", limit=30):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    keyword = keyword.strip()

    if keyword:
        like_keyword = f"%{keyword}%"

        cur.execute("""
        SELECT
            id AS grammar_id,
            jlpt_level,
            grammar,
            reading,
            meaning
        FROM grammar_points
        WHERE grammar LIKE ?
           OR reading LIKE ?
           OR meaning LIKE ?
           OR formation LIKE ?
        ORDER BY
            CASE jlpt_level
                WHEN 'N1' THEN 1
                WHEN 'N2' THEN 2
                ELSE 3
            END,
            grammar
        LIMIT ?
        """, (
            like_keyword,
            like_keyword,
            like_keyword,
            like_keyword,
            limit
        ))
    else:
        cur.execute("""
        SELECT
            id AS grammar_id,
            jlpt_level,
            grammar,
            reading,
            meaning
        FROM grammar_points
        ORDER BY
            CASE jlpt_level
                WHEN 'N1' THEN 1
                WHEN 'N2' THEN 2
                ELSE 3
            END,
            grammar
        LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_note_detail(user_id, note_id):
    ensure_notes_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT
        id AS note_id,
        title,
        content,
        created_at,
        updated_at
    FROM grammar_notes
    WHERE id = ?
      AND user_id = ?
    """, (note_id, user_id))

    note = cur.fetchone()

    if note is None:
        conn.close()
        return None

    note = dict(note)

    cur.execute("""
    SELECT
        grammar_note_links.grammar_id,
        grammar_note_links.relation_type,
        grammar_points.jlpt_level,
        grammar_points.grammar,
        grammar_points.reading,
        grammar_points.meaning
    FROM grammar_note_links
    JOIN grammar_points
        ON grammar_note_links.grammar_id = grammar_points.id
    WHERE grammar_note_links.note_id = ?
    ORDER BY grammar_points.jlpt_level, grammar_points.grammar
    """, (note_id,))

    note["connected_grammar"] = [dict(row) for row in cur.fetchall()]

    conn.close()

    return note


def update_note_with_links(user_id, note_id, title, content, grammar_links):
    ensure_notes_tables()

    title = title.strip()
    content = content.strip()

    if not title:
        return False, "Note title cannot be empty."

    if not content:
        return False, "Note content cannot be empty."

    if not grammar_links:
        return False, "Please connect the note to at least one grammar point."

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT id
    FROM grammar_notes
    WHERE id = ?
      AND user_id = ?
    """, (note_id, user_id))

    note = cur.fetchone()

    if note is None:
        conn.close()
        return False, "Note not found."

    cur.execute("""
    UPDATE grammar_notes
    SET
        title = ?,
        content = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
      AND user_id = ?
    """, (title, content, note_id, user_id))

    cur.execute("""
    DELETE FROM grammar_note_links
    WHERE note_id = ?
    """, (note_id,))

    for link in grammar_links:
        grammar_id = link["grammar_id"]
        relation_type = link.get("relation_type", "related")

        cur.execute("""
        INSERT INTO grammar_note_links (
            note_id,
            grammar_id,
            relation_type
        )
        VALUES (?, ?, ?)
        """, (note_id, grammar_id, relation_type))

    conn.commit()
    conn.close()

    return True, "Note updated successfully."


def get_note_draft_key(note_id=None):
    if note_id is None:
        return "new_note_connections"

    return f"edit_note_connections_{note_id}"


def get_draft_connections(note_id=None):
    key = get_note_draft_key(note_id)
    return session.get(key, [])


def save_draft_connections(connections, note_id=None):
    key = get_note_draft_key(note_id)
    session[key] = connections
    session.modified = True


def clear_draft_connections(note_id=None):
    key = get_note_draft_key(note_id)

    if key in session:
        session.pop(key)
        session.modified = True


def add_draft_connection(grammar_id, relation_type="related", note_id=None):
    connections = get_draft_connections(note_id)

    grammar_id = int(grammar_id)

    # If already connected, update relation type instead of duplicating.
    updated = False

    for connection in connections:
        if int(connection["grammar_id"]) == grammar_id:
            connection["relation_type"] = relation_type
            updated = True
            break

    if not updated:
        connections.append({
            "grammar_id": grammar_id,
            "relation_type": relation_type
        })

    save_draft_connections(connections, note_id)


def remove_draft_connection(grammar_id, note_id=None):
    connections = get_draft_connections(note_id)

    grammar_id = int(grammar_id)

    new_connections = [
        connection
        for connection in connections
        if int(connection["grammar_id"]) != grammar_id
    ]

    save_draft_connections(new_connections, note_id)


def get_draft_connection_details(note_id=None):
    connections = get_draft_connections(note_id)

    if not connections:
        return []

    grammar_ids = [int(connection["grammar_id"]) for connection in connections]
    relation_map = {
        int(connection["grammar_id"]): connection["relation_type"]
        for connection in connections
    }

    placeholders = ",".join("?" for _ in grammar_ids)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(f"""
    SELECT
        id AS grammar_id,
        jlpt_level,
        grammar,
        reading,
        meaning
    FROM grammar_points
    WHERE id IN ({placeholders})
    ORDER BY
        CASE jlpt_level
            WHEN 'N1' THEN 1
            WHEN 'N2' THEN 2
            ELSE 3
        END,
        grammar
    """, grammar_ids)

    rows = cur.fetchall()
    conn.close()

    results = []

    for row in rows:
        item = dict(row)
        item["relation_type"] = relation_map.get(item["grammar_id"], "related")
        results.append(item)

    return results


def delete_note_for_user(user_id, note_id):
    ensure_notes_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT id
    FROM grammar_notes
    WHERE id = ?
      AND user_id = ?
    """, (note_id, user_id))

    note = cur.fetchone()

    if note is None:
        conn.close()
        return False, "Note not found."

    cur.execute("""
    DELETE FROM grammar_note_links
    WHERE note_id = ?
    """, (note_id,))

    cur.execute("""
    DELETE FROM grammar_notes
    WHERE id = ?
      AND user_id = ?
    """, (note_id, user_id))

    conn.commit()
    conn.close()

    return True, "Note deleted successfully."


def get_note_detail_with_explanations(user_id, note_id):
    note = get_note_detail(user_id, note_id)

    if note is None:
        return None

    connected_grammar_with_details = []

    for grammar in note["connected_grammar"]:
        grammar_id = grammar["grammar_id"]

        full_grammar = get_grammar_detail(grammar_id)

        if full_grammar is None:
            continue

        full_grammar["relation_type"] = grammar["relation_type"]
        full_grammar["question_explanations"] = get_question_explanations_for_grammar(grammar_id)

        connected_grammar_with_details.append(full_grammar)

    note["connected_grammar"] = connected_grammar_with_details

    return note


def get_note_count_for_grammar(user_id, grammar_id):
    ensure_notes_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
    SELECT COUNT(DISTINCT grammar_notes.id) AS note_count
    FROM grammar_notes
    JOIN grammar_note_links
        ON grammar_notes.id = grammar_note_links.note_id
    WHERE grammar_notes.user_id = ?
      AND grammar_note_links.grammar_id = ?
    """, (user_id, grammar_id))

    row = cur.fetchone()
    conn.close()

    if row is None:
        return 0

    return row["note_count"]


def render_note_markdown(text):
    if text is None:
        return ""

    escaped_text = html.escape(text)

    rendered_html = markdown.markdown(
        escaped_text,
        extensions=[
            "nl2br",
            "sane_lists"
        ]
    )

    return rendered_html


app.jinja_env.filters["markdown_note"] = render_note_markdown


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

    question["note_count"] = get_note_count_for_grammar(
        session["user_id"],
        question["grammar_id"]
    )

    for choice in question["choices"]:
        choice["note_count"] = get_note_count_for_grammar(
            session["user_id"],
            choice["grammar_id"]
        )

    if selected_choice is not None:
        selected_choice["note_count"] = get_note_count_for_grammar(
            session["user_id"],
            selected_choice["grammar_id"]
        )

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


@app.route("/grammar/<int:grammar_id>/notes", methods=["GET", "POST"])
def grammar_notes(grammar_id):
    if "user_id" not in session:
        return redirect(url_for("index"))

    ensure_notes_tables()

    grammar = get_grammar_detail(grammar_id)

    if grammar is None:
        return "Grammar point not found.", 404

    error = None
    success = None

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        relation_type = request.form.get("relation_type", "related").strip()

        grammar_links = [
            {
                "grammar_id": grammar_id,
                "relation_type": relation_type
            }
        ]

        ok, message = create_note_with_links(
            user_id=session["user_id"],
            title=title,
            content=content,
            grammar_links=grammar_links
        )

        if ok:
            success = message
        else:
            error = message

    notes = get_notes_for_grammar(
        user_id=session["user_id"],
        grammar_id=grammar_id
    )

    question_explanations = get_question_explanations_for_grammar(grammar_id)

    return render_template(
        "grammar_notes.html",
        username=session["username"],
        grammar=grammar,
        notes=notes,
        question_explanations=question_explanations,
        error=error,
        success=success
    )


@app.route("/notes")
def notes_collection():
    if "user_id" not in session:
        return redirect(url_for("index"))

    keyword = request.args.get("keyword", "").strip()
    relation_type = request.args.get("relation_type", "all")
    jlpt_level = request.args.get("jlpt_level", "all")
    connection_filter = request.args.get("connection_filter", "all")
    sort_by = request.args.get("sort_by", "updated_desc")

    notes = get_all_notes_for_user(
        user_id=session["user_id"],
        keyword=keyword,
        relation_type=relation_type,
        jlpt_level=jlpt_level,
        connection_filter=connection_filter,
        sort_by=sort_by
    )

    return render_template(
        "notes_collection.html",
        username=session["username"],
        notes=notes,
        keyword=keyword,
        selected_relation=relation_type,
        selected_level=jlpt_level,
        selected_connection_filter=connection_filter,
        sort_by=sort_by
    )


@app.route("/notes/new", methods=["GET", "POST"])
def new_note():
    if "user_id" not in session:
        return redirect(url_for("index"))

    ensure_notes_tables()

    error = None

    keyword = request.args.get("keyword", "").strip()

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "add_connection":
            grammar_id = request.form.get("grammar_id")
            relation_type = request.form.get("relation_type", "related")

            if grammar_id:
                add_draft_connection(grammar_id, relation_type, note_id=None)

            keyword = request.form.get("keyword", "").strip()
            return redirect(url_for("new_note", keyword=keyword))

        if action == "remove_connection":
            grammar_id = request.form.get("grammar_id")

            if grammar_id:
                remove_draft_connection(grammar_id, note_id=None)

            keyword = request.form.get("keyword", "").strip()
            return redirect(url_for("new_note", keyword=keyword))

        if action == "clear_connections":
            clear_draft_connections(note_id=None)
            keyword = request.form.get("keyword", "").strip()
            return redirect(url_for("new_note", keyword=keyword))

        if action == "create_note":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            
            if not content:
                content = request.form.get("note_content", "").strip()
            grammar_links = get_draft_connections(note_id=None)

            ok, message = create_note_with_links(
                user_id=session["user_id"],
                title=title,
                content=content,
                grammar_links=grammar_links
            )

            if ok:
                clear_draft_connections(note_id=None)
                return redirect(url_for("notes_collection"))

            error = message

    if keyword:
        grammar_results = search_grammar_for_note_link(keyword=keyword, limit=50)
    else:
        grammar_results = []

    connected_grammar = get_draft_connection_details(note_id=None)

    return render_template(
        "new_note.html",
        username=session["username"],
        grammar_results=grammar_results,
        connected_grammar=connected_grammar,
        keyword=keyword,
        error=error
    )

@app.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
def edit_note(note_id):
    if "user_id" not in session:
        return redirect(url_for("index"))

    ensure_notes_tables()

    note = get_note_detail(
        user_id=session["user_id"],
        note_id=note_id
    )

    if note is None:
        return "Note not found.", 404

    draft_key = get_note_draft_key(note_id)

    # First time opening edit page: load DB connections into draft.
    if draft_key not in session:
        initial_connections = []

        for grammar in note["connected_grammar"]:
            initial_connections.append({
                "grammar_id": grammar["grammar_id"],
                "relation_type": grammar["relation_type"]
            })

        save_draft_connections(initial_connections, note_id=note_id)

    error = None
    keyword = request.args.get("keyword", "").strip()

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "add_connection":
            grammar_id = request.form.get("grammar_id")
            relation_type = request.form.get("relation_type", "related")

            if grammar_id:
                add_draft_connection(grammar_id, relation_type, note_id=note_id)

            keyword = request.form.get("keyword", "").strip()
            return redirect(url_for("edit_note", note_id=note_id, keyword=keyword))

        if action == "remove_connection":
            grammar_id = request.form.get("grammar_id")

            if grammar_id:
                remove_draft_connection(grammar_id, note_id=note_id)

            keyword = request.form.get("keyword", "").strip()
            return redirect(url_for("edit_note", note_id=note_id, keyword=keyword))

        if action == "reset_connections":
            clear_draft_connections(note_id=note_id)
            return redirect(url_for("edit_note", note_id=note_id, keyword=keyword))

        if action == "save_note":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            
            if not content:
                content = request.form.get("note_content", "").strip()
            
            grammar_links = get_draft_connections(note_id=note_id)

            ok, message = update_note_with_links(
                user_id=session["user_id"],
                note_id=note_id,
                title=title,
                content=content,
                grammar_links=grammar_links
            )

            if ok:
                clear_draft_connections(note_id=note_id)
                return redirect(url_for("notes_collection"))

            error = message

    if keyword:
        grammar_results = search_grammar_for_note_link(keyword=keyword, limit=50)
    else:
        grammar_results = []

    connected_grammar = get_draft_connection_details(note_id=note_id)

    return render_template(
        "edit_note.html",
        username=session["username"],
        note=note,
        grammar_results=grammar_results,
        connected_grammar=connected_grammar,
        keyword=keyword,
        error=error
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/notes/<int:note_id>/delete", methods=["GET", "POST"])
def delete_note(note_id):
    if "user_id" not in session:
        return redirect(url_for("index"))

    note = get_note_detail(
        user_id=session["user_id"],
        note_id=note_id
    )

    if note is None:
        return "Note not found.", 404

    error = None

    if request.method == "POST":
        confirm_text = request.form.get("confirm_text", "").strip()

        if confirm_text != "DELETE":
            error = "Please type DELETE to confirm note deletion."
        else:
            ok, message = delete_note_for_user(
                user_id=session["user_id"],
                note_id=note_id
            )

            if ok:
                return redirect(url_for("notes_collection"))

            error = message

    return render_template(
        "delete_note.html",
        username=session["username"],
        note=note,
        error=error
    )


@app.route("/notes/<int:note_id>")
def note_detail(note_id):
    if "user_id" not in session:
        return redirect(url_for("index"))

    note = get_note_detail_with_explanations(
        user_id=session["user_id"],
        note_id=note_id
    )

    if note is None:
        return "Note not found.", 404

    return render_template(
        "note_detail.html",
        username=session["username"],
        note=note
    )


ensure_user_account_columns()
ensure_notes_tables()


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode)