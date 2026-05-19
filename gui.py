import random
import sqlite3
import tkinter as tk
from tkinter import messagebox

from database import (
    get_connection,
    initialize_database_updates,
    get_all_users,
    get_or_create_user,
    get_user_dashboard,
    get_review_progress,
    search_grammar_points,
    reset_user_progress,
    get_weighted_question_excluding,
    get_weak_question_excluding,
    get_new_question_excluding,
    save_user_answer
)


COOLDOWN_SIZE = 2


class JLPTGrammarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JLPT Grammar App")
        self.root.geometry("900x700")

        initialize_database_updates()

        self.current_user = None

        self.current_quiz_level = None
        self.current_quiz_difficulty = None
        self.current_quiz_limit = None
        self.current_quiz_title = None
        self.current_question_getter = None

        self.session_total_answered = 0
        self.session_correct_count = 0
        self.session_wrong_count = 0

        self.recent_question_ids = []
        self.current_question = None
        self.current_display_choices = []
        self.answer_buttons = []

        self.about_page_index = 0
        self.about_pages = []

        self.show_user_select_screen()

    # -----------------------------
    # Helper functions
    # -----------------------------

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def format_accuracy(self, accuracy):
        if accuracy is None:
            return "N/A"

        return f"{accuracy:.1f}%"

    def add_title(self, text):
        title = tk.Label(
            self.root,
            text=text,
            font=("Arial", 22, "bold")
        )
        title.pack(pady=14)
        return title

    def add_button(self, text, command, width=30):
        button = tk.Button(
            self.root,
            text=text,
            width=width,
            command=command
        )
        button.pack(pady=5)
        return button

    def create_scroll_text_box(self, height=18):
        frame = tk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=25, pady=10)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        text_box = tk.Text(
            frame,
            wrap="word",
            yscrollcommand=scrollbar.set,
            font=("Arial", 10),
            height=height
        )
        text_box.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=text_box.yview)

        return text_box

    def add_menu_back_button(self):
        self.add_button("Back to Menu", self.show_main_menu)

    # -----------------------------
    # User selection
    # -----------------------------

    def show_user_select_screen(self):
        self.clear_screen()

        self.add_title("Select User")

        users = get_all_users()

        for user in users:
            self.add_button(
                user["username"],
                lambda u=user: self.select_user(u)
            )

        tk.Label(
            self.root,
            text="Create new user",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        self.username_entry = tk.Entry(self.root, width=35)
        self.username_entry.pack(pady=5)

        self.add_button("Create User", self.create_user, width=25)

    def select_user(self, user):
        self.current_user = user
        self.show_main_menu()

    def create_user(self):
        username = self.username_entry.get().strip()

        if username == "":
            messagebox.showwarning("Invalid username", "Username cannot be empty.")
            return

        user = get_or_create_user(username)
        self.current_user = user
        self.show_main_menu()

    # -----------------------------
    # Main menu
    # -----------------------------

    def show_main_menu(self):
        self.clear_screen()

        self.add_title("JLPT Grammar App")

        tk.Label(
            self.root,
            text=f'Current user: {self.current_user["username"]}',
            font=("Arial", 12)
        ).pack(pady=5)

        buttons = [
            (
                "Start Weighted Quiz",
                lambda: self.show_quiz_setup(
                    "Weighted Quiz",
                    get_weighted_question_excluding
                )
            ),
            (
                "Review Weak Grammar",
                lambda: self.show_quiz_setup(
                    "Weak Grammar Review",
                    get_weak_question_excluding
                )
            ),
            (
                "Study New Grammar",
                lambda: self.show_quiz_setup(
                    "Study New Grammar",
                    get_new_question_excluding
                )
            ),
            ("Dashboard", self.show_dashboard_setup),
            ("View Progress", self.show_progress_setup),
            ("Search Grammar", self.show_search_screen),
            ("Manage Grammar / Questions", self.show_manage_screen),
            ("About / How This App Works", self.show_about_screen),
            ("Reset Progress", self.show_reset_progress_screen),
            ("Switch User", self.show_user_select_screen),
        ]

        for text, command in buttons:
            self.add_button(text, command)

    # -----------------------------
    # About screen
    # -----------------------------

    def show_about_screen(self):
        self.about_page_index = 0

        self.about_pages = [
            (
                "What This App Is",
                """
This app is a JLPT grammar quiz and review application.

It helps users study JLPT N1 and N2 grammar through:
- quiz practice
- weak grammar review
- new grammar study
- progress tracking
- grammar search
- manual grammar/question management

Each user has separate progress.
"""
            ),
            (
                "How Quiz Feedback Works",
                """
Before answering, the app hides the grammar point and meaning so the answer is not spoiled.

After answering, the app shows:
- whether your chosen answer was correct or wrong
- the correct answer
- the main grammar point
- the main meaning
- the question explanation
- detailed information for every choice

Choice details can be shown if:
1. the choice is linked to a grammar ID, or
2. the choice text matches an existing grammar point.
"""
            ),
            (
                "Progress Filter: Show Except",
                """
The Progress page supports three filter modes:

1. Show all mastery levels
This shows everything.

2. Show only selected mastery levels
This shows only the mastery levels you select.

3. Show except selected mastery levels
This hides the mastery levels you select and shows the rest.

For example:
If you choose Show except and select mastered,
the app shows new, learning, and weak grammar only.
"""
            ),
            (
                "Mastery Ranking",
                """
The app tracks mastery by grammar point.

Mastery levels:
- new
- learning
- weak
- mastered

Weak:
wrong_count is 3 or more and accuracy is below 80%.

Mastered:
correct_count is 5 or more and accuracy is 90% or higher.

Accuracy:
correct_count / total_answers * 100
"""
            )
        ]

        self.show_about_page()

    def show_about_page(self):
        self.clear_screen()

        page_title, page_text = self.about_pages[self.about_page_index]

        self.add_title("About / How This App Works")

        tk.Label(
            self.root,
            text=f"Page {self.about_page_index + 1} of {len(self.about_pages)}: {page_title}",
            font=("Arial", 13, "bold")
        ).pack(pady=5)

        text_box = self.create_scroll_text_box()
        text_box.insert("end", page_text.strip())
        text_box.config(state="disabled")

        nav_frame = tk.Frame(self.root)
        nav_frame.pack(pady=8)

        previous_button = tk.Button(
            nav_frame,
            text="Previous Page",
            width=18,
            command=self.previous_about_page
        )
        previous_button.grid(row=0, column=0, padx=5)

        next_button = tk.Button(
            nav_frame,
            text="Next Page",
            width=18,
            command=self.next_about_page
        )
        next_button.grid(row=0, column=1, padx=5)

        if self.about_page_index == 0:
            previous_button.config(state="disabled")

        if self.about_page_index == len(self.about_pages) - 1:
            next_button.config(state="disabled")

        self.add_menu_back_button()

    def next_about_page(self):
        if self.about_page_index < len(self.about_pages) - 1:
            self.about_page_index += 1
            self.show_about_page()

    def previous_about_page(self):
        if self.about_page_index > 0:
            self.about_page_index -= 1
            self.show_about_page()

    # -----------------------------
    # Dashboard
    # -----------------------------

    def show_dashboard_setup(self):
        self.clear_screen()

        self.add_title("Dashboard")

        tk.Label(
            self.root,
            text="Choose JLPT Level",
            font=("Arial", 12, "bold")
        ).pack(pady=5)

        self.dashboard_level_var = tk.StringVar(value="All")

        for text, value in [
            ("All levels", "All"),
            ("N1 only", "N1"),
            ("N2 only", "N2")
        ]:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.dashboard_level_var,
                value=value
            ).pack()

        self.add_button("Show Dashboard", self.show_dashboard_results, width=25)
        self.add_menu_back_button()

    def show_dashboard_results(self):
        selected_level = self.dashboard_level_var.get()

        if selected_level == "All":
            jlpt_level = None
            level_text = "All levels"
        else:
            jlpt_level = selected_level
            level_text = selected_level

        dashboard = get_user_dashboard(self.current_user["id"], jlpt_level)

        self.clear_screen()
        self.add_title("Dashboard Results")

        accuracy_text = self.format_accuracy(dashboard["accuracy"])
        total_grammar = dashboard["total_grammar"]

        if total_grammar == 0:
            new_percent = 0
            learning_percent = 0
            weak_percent = 0
            mastered_percent = 0
        else:
            new_percent = dashboard["new_count"] / total_grammar * 100
            learning_percent = dashboard["learning_count"] / total_grammar * 100
            weak_percent = dashboard["weak_count"] / total_grammar * 100
            mastered_percent = dashboard["mastered_count"] / total_grammar * 100

        info = f"""
User: {self.current_user["username"]}
Level: {level_text}

Database:
Total grammar points: {dashboard["total_grammar"]}
Total questions: {dashboard["total_questions"]}

Answer Summary:
Total answered: {dashboard["total_answered"]}
Correct: {dashboard["correct_count"]}
Wrong: {dashboard["wrong_count"]}
Overall accuracy: {accuracy_text}

Mastery Summary:
New: {dashboard["new_count"]} ({new_percent:.1f}%)
Learning: {dashboard["learning_count"]} ({learning_percent:.1f}%)
Weak: {dashboard["weak_count"]} ({weak_percent:.1f}%)
Mastered: {dashboard["mastered_count"]} ({mastered_percent:.1f}%)
"""

        tk.Label(
            self.root,
            text=info,
            font=("Arial", 12),
            justify="left"
        ).pack(pady=10)

        self.add_button("Back to Dashboard Filter", self.show_dashboard_setup)
        self.add_menu_back_button()

    # -----------------------------
    # Quiz setup
    # -----------------------------

    def show_quiz_setup(self, quiz_title, question_getter):
        self.clear_screen()

        self.current_quiz_title = quiz_title
        self.current_question_getter = question_getter

        self.add_title(quiz_title)

        tk.Label(
            self.root,
            text="Choose JLPT Level",
            font=("Arial", 12, "bold")
        ).pack(pady=5)

        self.quiz_level_var = tk.StringVar(value="All")

        for text, value in [
            ("All levels", "All"),
            ("N1 only", "N1"),
            ("N2 only", "N2")
        ]:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.quiz_level_var,
                value=value
            ).pack()

        tk.Label(
            self.root,
            text="Choose Difficulty",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        self.quiz_difficulty_var = tk.StringVar(value="All")

        for text, value in [
            ("All difficulties", "All"),
            ("Easy only", "easy"),
            ("Normal only", "normal"),
            ("Hard only", "hard")
        ]:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.quiz_difficulty_var,
                value=value
            ).pack()

        tk.Label(
            self.root,
            text="Choose Number of Questions",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        self.quiz_limit_var = tk.StringVar(value="5")

        for text, value in [
            ("5 questions", "5"),
            ("10 questions", "10"),
            ("20 questions", "20"),
            ("Unlimited", "Unlimited")
        ]:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.quiz_limit_var,
                value=value
            ).pack()

        self.add_button("Start Quiz", self.start_quiz, width=25)
        self.add_menu_back_button()

    def start_quiz(self):
        level = self.quiz_level_var.get()
        difficulty = self.quiz_difficulty_var.get()
        limit = self.quiz_limit_var.get()

        self.current_quiz_level = None if level == "All" else level
        self.current_quiz_difficulty = None if difficulty == "All" else difficulty
        self.current_quiz_limit = None if limit == "Unlimited" else int(limit)

        self.session_total_answered = 0
        self.session_correct_count = 0
        self.session_wrong_count = 0

        self.recent_question_ids = []
        self.current_question = None
        self.current_display_choices = []

        self.load_question()

    # -----------------------------
    # Quiz question screen
    # -----------------------------

    def load_question(self):
        if (
            self.current_quiz_limit is not None
            and self.session_total_answered >= self.current_quiz_limit
        ):
            self.show_session_score()
            return

        question = self.current_question_getter(
            self.current_user["id"],
            self.recent_question_ids,
            self.current_quiz_level,
            self.current_quiz_difficulty
        )

        if question is None and self.recent_question_ids:
            self.recent_question_ids.clear()

            question = self.current_question_getter(
                self.current_user["id"],
                self.recent_question_ids,
                self.current_quiz_level,
                self.current_quiz_difficulty
            )

        if question is None:
            if self.session_total_answered > 0:
                self.show_session_score()
            else:
                self.show_no_question_screen()
            return

        self.current_question = question
        self.current_display_choices = question["choices"].copy()
        random.shuffle(self.current_display_choices)

        self.show_question_screen()

    def show_question_screen(self):
        self.clear_screen()

        question = self.current_question

        self.add_title(self.current_quiz_title)

        limit_text = "Unlimited" if self.current_quiz_limit is None else str(self.current_quiz_limit)

        session_text = (
            f'User: {self.current_user["username"]}\n'
            f'Level: {question["jlpt_level"]}    Difficulty: {question["difficulty"]}\n'
            f'Session: {self.session_total_answered}/{limit_text} answered    '
            f'Correct: {self.session_correct_count}    Wrong: {self.session_wrong_count}'
        )

        tk.Label(
            self.root,
            text=session_text,
            font=("Arial", 11),
            justify="left"
        ).pack(pady=8)

        tk.Label(
            self.root,
            text=question["question_text"],
            font=("Arial", 15),
            wraplength=780,
            justify="left"
        ).pack(pady=16)

        self.answer_buttons = []

        for index, choice in enumerate(self.current_display_choices, start=1):
            button = tk.Button(
                self.root,
                text=f'{index}. {choice["choice_text"]}',
                width=75,
                wraplength=700,
                command=lambda c=choice: self.choose_answer(c)
            )
            button.pack(pady=4)
            self.answer_buttons.append(button)

        self.feedback_status_label = tk.Label(
            self.root,
            text="Choose an answer to see feedback.",
            font=("Arial", 12, "bold"),
            wraplength=780,
            justify="left"
        )
        self.feedback_status_label.pack(pady=8)

        self.feedback_button_frame = tk.Frame(self.root)
        self.feedback_button_frame.pack(pady=5)

        self.feedback_text_box = self.create_scroll_text_box(height=8)
        self.feedback_text_box.config(state="disabled")

        self.add_menu_back_button()

    def build_choice_feedback_text(self, selected_choice, is_correct):
        question = self.current_question

        correct_answer_text = ""

        for choice in question["choices"]:
            if choice["is_correct"] == 1:
                correct_answer_text = choice["choice_text"]
                break

        if is_correct:
            result_text = "Correct!"
        else:
            result_text = f"Wrong.\nCorrect answer: {correct_answer_text}"

        feedback_lines = []

        feedback_lines.append(result_text)
        feedback_lines.append("")
        feedback_lines.append("Main Question Details:")
        feedback_lines.append(f'Grammar: {question["grammar"]}')
        feedback_lines.append(f'Meaning: {question["meaning"]}')
        feedback_lines.append("")
        feedback_lines.append("Question Explanation:")
        feedback_lines.append(question["explanation"])
        feedback_lines.append("")
        feedback_lines.append("=" * 70)
        feedback_lines.append("Choice Details")
        feedback_lines.append("=" * 70)

        for index, choice in enumerate(self.current_display_choices, start=1):
            status_parts = []

            if choice["choice_id"] == selected_choice["choice_id"]:
                status_parts.append("Your answer")

            if choice["is_correct"] == 1:
                status_parts.append("Correct answer")
            else:
                status_parts.append("Wrong choice")

            status_text = " / ".join(status_parts)

            feedback_lines.append("")
            feedback_lines.append(f'{index}. {choice["choice_text"]}')
            feedback_lines.append(f"Status: {status_text}")

            detail_grammar = choice.get("choice_detail_grammar")
            detail_meaning = choice.get("choice_detail_meaning")

            if detail_grammar is None and detail_meaning is None:
                feedback_lines.append("Details: No linked grammar details found for this choice.")
                feedback_lines.append("Tip: Add a Choice Grammar ID when creating questions to show full details.")
                continue

            feedback_lines.append(f'JLPT Level: {choice.get("choice_detail_jlpt_level") or "N/A"}')
            feedback_lines.append(f'Grammar: {choice.get("choice_detail_grammar") or "N/A"}')
            feedback_lines.append(f'Reading: {choice.get("choice_detail_reading") or "N/A"}')
            feedback_lines.append(f'Romaji: {choice.get("choice_detail_romaji") or "N/A"}')
            feedback_lines.append(f'Meaning: {choice.get("choice_detail_meaning") or "N/A"}')
            feedback_lines.append(f'Formation: {choice.get("choice_detail_formation") or "N/A"}')
            feedback_lines.append(f'Example: {choice.get("choice_detail_example_sentence") or "N/A"}')
            feedback_lines.append(f'Translation: {choice.get("choice_detail_example_translation") or "N/A"}')
            feedback_lines.append(f'Source: {choice.get("choice_detail_source") or "N/A"}')

        return "\n".join(feedback_lines)


    def get_correct_choice(self):
        for choice in self.current_question["choices"]:
            if choice["is_correct"] == 1:
                return choice

        return None


    def build_result_feedback_text(self, selected_choice, is_correct):
        correct_choice = self.get_correct_choice()

        if correct_choice is None:
            correct_answer_text = "N/A"
        else:
            correct_answer_text = correct_choice["choice_text"]

        if is_correct:
            result_text = "Correct!"
        else:
            result_text = "Wrong."

        return (
            f"{result_text}\n\n"
            f'Your answer:\n{selected_choice["choice_text"]}\n\n'
            f"Correct answer:\n{correct_answer_text}"
        )


    def build_main_explanation_text(self):
        question = self.current_question

        return (
            "Main Question Details\n"
            + "=" * 50 + "\n\n"
            f'Grammar: {question["grammar"]}\n'
            f'Meaning: {question["meaning"]}\n\n'
            f'Explanation:\n{question["explanation"]}'
        )


    def build_correct_answer_text(self):
        correct_choice = self.get_correct_choice()

        if correct_choice is None:
            return "Correct answer not found."

        return self.build_single_choice_detail_text(correct_choice, "Correct answer")


    def build_single_choice_detail_text(self, choice, extra_status=""):
        status_parts = []

        if extra_status != "":
            status_parts.append(extra_status)

        if choice["is_correct"] == 1:
            status_parts.append("Correct answer")
        else:
            status_parts.append("Wrong choice")

        status_text = " / ".join(status_parts)

        lines = []

        lines.append(f'Choice: {choice["choice_text"]}')
        lines.append(f"Status: {status_text}")
        lines.append("")

        detail_grammar = choice.get("choice_detail_grammar")
        detail_meaning = choice.get("choice_detail_meaning")

        if detail_grammar is None and detail_meaning is None:
            lines.append("Details: No linked grammar details found for this choice.")
            lines.append("")
            lines.append("Tip:")
            lines.append("To show full details, link this choice to a Grammar ID when creating questions.")
            return "\n".join(lines)

        lines.append(f'JLPT Level: {choice.get("choice_detail_jlpt_level") or "N/A"}')
        lines.append(f'Grammar: {choice.get("choice_detail_grammar") or "N/A"}')
        lines.append(f'Reading: {choice.get("choice_detail_reading") or "N/A"}')
        lines.append(f'Romaji: {choice.get("choice_detail_romaji") or "N/A"}')
        lines.append(f'Meaning: {choice.get("choice_detail_meaning") or "N/A"}')
        lines.append(f'Formation: {choice.get("choice_detail_formation") or "N/A"}')
        lines.append(f'Example: {choice.get("choice_detail_example_sentence") or "N/A"}')
        lines.append(f'Translation: {choice.get("choice_detail_example_translation") or "N/A"}')
        lines.append(f'Source: {choice.get("choice_detail_source") or "N/A"}')

        return "\n".join(lines)


    def build_all_choices_text(self, selected_choice):
        lines = []

        lines.append("All Choice Details")
        lines.append("=" * 50)

        for index, choice in enumerate(self.current_display_choices, start=1):
            extra_status = ""

            if choice["choice_id"] == selected_choice["choice_id"]:
                extra_status = "Your answer"

            lines.append("")
            lines.append("-" * 50)
            lines.append(f"Choice {index}")
            lines.append("-" * 50)
            lines.append(self.build_single_choice_detail_text(choice, extra_status))

        return "\n".join(lines)


    def show_feedback_text(self, text):
        self.feedback_text_box.config(state="normal")
        self.feedback_text_box.delete("1.0", "end")
        self.feedback_text_box.insert("end", text)
        self.feedback_text_box.config(state="disabled")


    def clear_feedback_buttons(self):
        for widget in self.feedback_button_frame.winfo_children():
            widget.destroy()


    def create_feedback_buttons(self, selected_choice, is_correct):
        self.clear_feedback_buttons()

        result_text = self.build_result_feedback_text(selected_choice, is_correct)
        main_text = self.build_main_explanation_text()
        correct_text = self.build_correct_answer_text()
        all_choices_text = self.build_all_choices_text(selected_choice)

        tk.Button(
            self.feedback_button_frame,
            text="Result",
            width=16,
            command=lambda: self.show_feedback_text(result_text)
        ).grid(row=0, column=0, padx=3, pady=3)

        tk.Button(
            self.feedback_button_frame,
            text="Main Explanation",
            width=18,
            command=lambda: self.show_feedback_text(main_text)
        ).grid(row=0, column=1, padx=3, pady=3)

        tk.Button(
            self.feedback_button_frame,
            text="Correct Answer",
            width=16,
            command=lambda: self.show_feedback_text(correct_text)
        ).grid(row=0, column=2, padx=3, pady=3)

        tk.Button(
            self.feedback_button_frame,
            text="All Choices",
            width=16,
            command=lambda: self.show_feedback_text(all_choices_text)
        ).grid(row=0, column=3, padx=3, pady=3)

        for index, choice in enumerate(self.current_display_choices, start=1):
            button_text = f"Choice {index}"

            detail_text = self.build_single_choice_detail_text(
                choice,
                "Your answer" if choice["choice_id"] == selected_choice["choice_id"] else ""
            )

            tk.Button(
                self.feedback_button_frame,
                text=button_text,
                width=16,
                command=lambda text=detail_text: self.show_feedback_text(text)
            ).grid(row=1, column=index - 1, padx=3, pady=3)

    def choose_answer(self, selected_choice):
        question = self.current_question

        is_correct = save_user_answer(
            self.current_user["id"],
            question["question_id"],
            selected_choice["choice_id"]
        )

        self.recent_question_ids.append(question["question_id"])

        if len(self.recent_question_ids) > COOLDOWN_SIZE:
            self.recent_question_ids.pop(0)

        self.session_total_answered += 1

        if is_correct:
            self.session_correct_count += 1
        else:
            self.session_wrong_count += 1

        for button in self.answer_buttons:
            button.config(state="disabled")

        if is_correct:
            self.feedback_status_label.config(text="Correct! Choose a feedback section below.")
        else:
            self.feedback_status_label.config(text="Wrong. Choose a feedback section below.")

        self.create_feedback_buttons(selected_choice, is_correct)

        result_text = self.build_result_feedback_text(selected_choice, is_correct)
        self.show_feedback_text(result_text)

        if (
            self.current_quiz_limit is not None
            and self.session_total_answered >= self.current_quiz_limit
        ):
            next_text = "Show Session Score"
            next_command = self.show_session_score
        else:
            next_text = "Next Question"
            next_command = self.load_question

        self.add_button(next_text, next_command, width=25)

    def show_session_score(self):
        self.clear_screen()

        self.add_title("Session Score")

        if self.session_total_answered == 0:
            accuracy_text = "N/A"
        else:
            accuracy = self.session_correct_count / self.session_total_answered * 100
            accuracy_text = f"{accuracy:.1f}%"

        level_text = "All levels" if self.current_quiz_level is None else self.current_quiz_level
        difficulty_text = "All difficulties" if self.current_quiz_difficulty is None else self.current_quiz_difficulty
        limit_text = "Unlimited" if self.current_quiz_limit is None else str(self.current_quiz_limit)

        score_text = f"""
Mode: {self.current_quiz_title}
Level: {level_text}
Difficulty: {difficulty_text}
Question limit: {limit_text}

Total answered: {self.session_total_answered}
Correct: {self.session_correct_count}
Wrong: {self.session_wrong_count}
Accuracy: {accuracy_text}
"""

        tk.Label(
            self.root,
            text=score_text,
            font=("Arial", 13),
            justify="left"
        ).pack(pady=20)

        self.add_button("Restart Same Quiz", self.restart_same_quiz, width=25)
        self.add_menu_back_button()

    def restart_same_quiz(self):
        self.session_total_answered = 0
        self.session_correct_count = 0
        self.session_wrong_count = 0
        self.recent_question_ids = []
        self.load_question()

    def show_no_question_screen(self):
        self.clear_screen()

        self.add_title("No Question Found")

        level_text = "All levels" if self.current_quiz_level is None else self.current_quiz_level
        difficulty_text = "All difficulties" if self.current_quiz_difficulty is None else self.current_quiz_difficulty

        message = (
            "No question was found for this filter.\n\n"
            f"Mode: {self.current_quiz_title}\n"
            f"Level: {level_text}\n"
            f"Difficulty: {difficulty_text}"
        )

        tk.Label(
            self.root,
            text=message,
            font=("Arial", 12),
            justify="left"
        ).pack(pady=20)

        self.add_menu_back_button()

    # -----------------------------
    # Progress screen with Show Except
    # -----------------------------

    def show_progress_setup(self):
        self.clear_screen()

        self.add_title("View Progress")

        tk.Label(
            self.root,
            text="Choose JLPT Level",
            font=("Arial", 12, "bold")
        ).pack(pady=5)

        self.progress_level_var = tk.StringVar(value="All")

        for text, value in [
            ("All levels", "All"),
            ("N1 only", "N1"),
            ("N2 only", "N2")
        ]:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.progress_level_var,
                value=value
            ).pack()

        tk.Label(
            self.root,
            text="Progress Filter Mode",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        self.progress_filter_mode_var = tk.StringVar(value="all")

        filter_modes = [
            ("Show all mastery levels", "all"),
            ("Show only selected mastery levels", "only"),
            ("Show except selected mastery levels", "except")
        ]

        for text, value in filter_modes:
            tk.Radiobutton(
                self.root,
                text=text,
                variable=self.progress_filter_mode_var,
                value=value
            ).pack()

        tk.Label(
            self.root,
            text="Choose Mastery Levels",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        self.progress_mastery_vars = {
            "new": tk.IntVar(value=0),
            "learning": tk.IntVar(value=0),
            "weak": tk.IntVar(value=0),
            "mastered": tk.IntVar(value=0)
        }

        mastery_frame = tk.Frame(self.root)
        mastery_frame.pack(pady=5)

        for index, mastery in enumerate(["new", "learning", "weak", "mastered"]):
            tk.Checkbutton(
                mastery_frame,
                text=mastery,
                variable=self.progress_mastery_vars[mastery]
            ).grid(row=0, column=index, padx=10)

        self.add_button("Show Progress", self.show_progress_results, width=25)
        self.add_menu_back_button()

    def show_progress_results(self):
        level = self.progress_level_var.get()
        filter_mode = self.progress_filter_mode_var.get()

        if level == "All":
            jlpt_level = None
            level_text = "All levels"
        else:
            jlpt_level = level
            level_text = level

        selected_mastery = []

        for mastery, var in self.progress_mastery_vars.items():
            if var.get() == 1:
                selected_mastery.append(mastery)

        mastery_filter = None
        excluded_mastery_levels = None

        if filter_mode == "all":
            filter_text = "All mastery levels"

        elif filter_mode == "only":
            mastery_filter = selected_mastery
            filter_text = "Show only: " + ", ".join(selected_mastery)

            if not selected_mastery:
                messagebox.showwarning(
                    "No mastery selected",
                    "Please select at least one mastery level."
                )
                return

        else:
            excluded_mastery_levels = selected_mastery
            filter_text = "Show except: " + ", ".join(selected_mastery)

            if not selected_mastery:
                messagebox.showwarning(
                    "No mastery selected",
                    "Please select at least one mastery level to exclude."
                )
                return

        progress_list = get_review_progress(
            self.current_user["id"],
            jlpt_level,
            mastery_filter,
            excluded_mastery_levels
        )

        self.clear_screen()

        self.add_title("Progress Results")

        tk.Label(
            self.root,
            text=(
                f'User: {self.current_user["username"]}\n'
                f"Level: {level_text}\n"
                f"Filter: {filter_text}\n"
                f"Results: {len(progress_list)}"
            ),
            font=("Arial", 11),
            justify="left"
        ).pack(pady=5)

        text_box = self.create_scroll_text_box()

        if not progress_list:
            text_box.insert("end", "No grammar progress found for this filter.")
        else:
            for item in progress_list:
                text_box.insert("end", "-" * 60 + "\n")
                text_box.insert("end", f'ID: {item["id"]}\n')
                text_box.insert("end", f'Level: {item["jlpt_level"]}\n')
                text_box.insert("end", f'Grammar: {item["grammar"]}\n')
                text_box.insert("end", f'Meaning: {item["meaning"]}\n')
                text_box.insert("end", f'Times asked: {item["total_asked"]}\n')
                text_box.insert("end", f'Correct: {item["correct_count"]}\n')
                text_box.insert("end", f'Wrong: {item["wrong_count"]}\n')
                text_box.insert("end", f'Accuracy: {self.format_accuracy(item["accuracy"])}\n')
                text_box.insert("end", f'Mastery: {item["mastery_level"]}\n')
                text_box.insert("end", f'Last reviewed: {item["last_reviewed_at"]}\n\n')

        text_box.config(state="disabled")

        self.add_button("Back to Progress Filter", self.show_progress_setup)
        self.add_menu_back_button()

    # -----------------------------
    # Search grammar screen
    # -----------------------------

    def show_search_screen(self):
        self.clear_screen()

        self.add_title("Search Grammar")

        tk.Label(
            self.root,
            text="Search by grammar, reading, romaji, meaning, formation, or example sentence.",
            font=("Arial", 11),
            wraplength=780
        ).pack(pady=10)

        self.search_entry = tk.Entry(self.root, width=55)
        self.search_entry.pack(pady=10)
        self.search_entry.focus()

        self.search_entry.bind(
            "<Return>",
            lambda event: self.show_search_results()
        )

        self.add_button("Search", self.show_search_results, width=25)
        self.add_menu_back_button()

    def show_search_results(self):
        keyword = self.search_entry.get().strip()

        if keyword == "":
            messagebox.showwarning("Empty search", "Please enter a search keyword.")
            return

        results = search_grammar_points(
            self.current_user["id"],
            keyword
        )

        self.clear_screen()
        self.add_title("Search Results")

        tk.Label(
            self.root,
            text=(
                f'User: {self.current_user["username"]}\n'
                f"Keyword: {keyword}\n"
                f"Results found: {len(results)}"
            ),
            font=("Arial", 11),
            justify="left"
        ).pack(pady=5)

        text_box = self.create_scroll_text_box()

        if not results:
            text_box.insert("end", "No matching grammar found.")
        else:
            for item in results:
                text_box.insert("end", "-" * 60 + "\n")
                text_box.insert("end", f'ID: {item["id"]}\n')
                text_box.insert("end", f'Level: {item["jlpt_level"]}\n')
                text_box.insert("end", f'Grammar: {item["grammar"]}\n')
                text_box.insert("end", f'Reading: {item["reading"]}\n')
                text_box.insert("end", f'Romaji: {item["romaji"]}\n')
                text_box.insert("end", f'Meaning: {item["meaning"]}\n')
                text_box.insert("end", f'Formation: {item["formation"]}\n')
                text_box.insert("end", f'Example: {item["example_sentence"]}\n')
                text_box.insert("end", f'Translation: {item["example_translation"]}\n')
                text_box.insert("end", f'Source: {item["source"]}\n')
                text_box.insert("end", "\nYour progress:\n")
                text_box.insert("end", f'Times asked: {item["total_asked"]}\n')
                text_box.insert("end", f'Correct: {item["correct_count"]}\n')
                text_box.insert("end", f'Wrong: {item["wrong_count"]}\n')
                text_box.insert("end", f'Accuracy: {self.format_accuracy(item["accuracy"])}\n')
                text_box.insert("end", f'Mastery: {item["mastery_level"]}\n')
                text_box.insert("end", f'Last reviewed: {item["last_reviewed_at"]}\n\n')

        text_box.config(state="disabled")

        self.add_button("Back to Search", self.show_search_screen)
        self.add_menu_back_button()

    # -----------------------------
    # Manage grammar / questions
    # -----------------------------

    def show_manage_screen(self):
        self.clear_screen()

        self.add_title("Manage Grammar / Questions")

        info = (
            "This screen lets you manually add grammar points and quiz questions.\n"
            "For detailed choice feedback, each answer choice can optionally be linked to a grammar ID."
        )

        tk.Label(
            self.root,
            text=info,
            font=("Arial", 12),
            wraplength=780,
            justify="left"
        ).pack(pady=15)

        self.add_button("Add Grammar Point", self.show_add_grammar_screen)
        self.add_button("Add Question", self.show_add_question_screen)
        self.add_menu_back_button()

    def show_add_grammar_screen(self):
        self.clear_screen()

        self.add_title("Add Grammar Point")

        self.add_grammar_entries = {}

        fields = [
            ("JLPT Level", "jlpt_level"),
            ("Grammar", "grammar"),
            ("Reading", "reading"),
            ("Romaji", "romaji"),
            ("Meaning", "meaning"),
            ("Formation", "formation"),
            ("Example Sentence", "example_sentence"),
            ("Example Translation", "example_translation"),
            ("Source", "source")
        ]

        form_frame = tk.Frame(self.root)
        form_frame.pack(pady=5)

        for row_index, (label_text, key) in enumerate(fields):
            tk.Label(
                form_frame,
                text=label_text,
                width=20,
                anchor="e"
            ).grid(row=row_index, column=0, padx=5, pady=4)

            entry = tk.Entry(form_frame, width=60)
            entry.grid(row=row_index, column=1, padx=5, pady=4)

            self.add_grammar_entries[key] = entry

        self.add_grammar_entries["jlpt_level"].insert(0, "N2")

        self.add_button("Save Grammar Point", self.save_new_grammar, width=25)
        self.add_button("Back to Manage", self.show_manage_screen, width=25)
        self.add_menu_back_button()

    def save_new_grammar(self):
        data = {}

        for key, entry in self.add_grammar_entries.items():
            data[key] = entry.get().strip()

        if data["jlpt_level"] not in ["N1", "N2"]:
            messagebox.showwarning(
                "Invalid JLPT level",
                "JLPT Level must be N1 or N2."
            )
            return

        if data["grammar"] == "" or data["meaning"] == "":
            messagebox.showwarning(
                "Missing required fields",
                "Grammar and Meaning are required."
            )
            return

        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            SELECT id
            FROM grammar_points
            WHERE jlpt_level = ?
              AND grammar = ?
            """, (
                data["jlpt_level"],
                data["grammar"]
            ))

            duplicate = cursor.fetchone()

            if duplicate is not None:
                messagebox.showwarning(
                    "Duplicate grammar",
                    f'This grammar already exists.\nExisting ID: {duplicate["id"]}'
                )
                return

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
                data["jlpt_level"],
                data["grammar"],
                data["reading"],
                data["romaji"],
                data["meaning"],
                data["formation"],
                data["example_sentence"],
                data["example_translation"],
                data["source"]
            ))

            grammar_id = cursor.lastrowid
            conn.commit()

            messagebox.showinfo(
                "Grammar Added",
                f"Grammar point was added successfully.\nNew grammar ID: {grammar_id}"
            )

            self.show_manage_screen()

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not add grammar point.\n\n{error}"
            )

        finally:
            if conn is not None:
                conn.close()

    def show_add_question_screen(self):
        self.clear_screen()

        self.add_title("Add Question")

        form_frame = tk.Frame(self.root)
        form_frame.pack(pady=5)

        tk.Label(
            form_frame,
            text="Grammar ID",
            width=18,
            anchor="e"
        ).grid(row=0, column=0, padx=5, pady=4)

        self.question_grammar_id_entry = tk.Entry(form_frame, width=20)
        self.question_grammar_id_entry.grid(row=0, column=1, padx=5, pady=4, sticky="w")

        tk.Label(
            form_frame,
            text="Difficulty",
            width=18,
            anchor="e"
        ).grid(row=1, column=0, padx=5, pady=4)

        self.question_difficulty_var = tk.StringVar(value="normal")

        difficulty_frame = tk.Frame(form_frame)
        difficulty_frame.grid(row=1, column=1, padx=5, pady=4, sticky="w")

        for difficulty in ["easy", "normal", "hard"]:
            tk.Radiobutton(
                difficulty_frame,
                text=difficulty,
                variable=self.question_difficulty_var,
                value=difficulty
            ).pack(side="left")

        tk.Label(
            self.root,
            text="Question Text",
            font=("Arial", 11, "bold")
        ).pack(pady=3)

        self.question_text_box = tk.Text(self.root, height=4, width=85)
        self.question_text_box.pack(pady=3)

        tk.Label(
            self.root,
            text="Explanation",
            font=("Arial", 11, "bold")
        ).pack(pady=3)

        self.question_explanation_box = tk.Text(self.root, height=4, width=85)
        self.question_explanation_box.pack(pady=3)

        self.choice_entries = []
        self.choice_grammar_id_entries = []

        choice_frame = tk.Frame(self.root)
        choice_frame.pack(pady=8)

        self.correct_choice_var = tk.IntVar(value=1)

        tk.Label(choice_frame, text="Choice", width=10).grid(row=0, column=0)
        tk.Label(choice_frame, text="Choice Text", width=45).grid(row=0, column=1)
        tk.Label(choice_frame, text="Grammar ID optional", width=20).grid(row=0, column=2)
        tk.Label(choice_frame, text="Correct", width=10).grid(row=0, column=3)

        for index in range(4):
            tk.Label(
                choice_frame,
                text=f"Choice {index + 1}",
                width=10,
                anchor="e"
            ).grid(row=index + 1, column=0, padx=5, pady=4)

            entry = tk.Entry(choice_frame, width=45)
            entry.grid(row=index + 1, column=1, padx=5, pady=4)
            self.choice_entries.append(entry)

            grammar_id_entry = tk.Entry(choice_frame, width=18)
            grammar_id_entry.grid(row=index + 1, column=2, padx=5, pady=4)
            self.choice_grammar_id_entries.append(grammar_id_entry)

            tk.Radiobutton(
                choice_frame,
                variable=self.correct_choice_var,
                value=index + 1
            ).grid(row=index + 1, column=3, padx=5, pady=4)

        self.add_button("Save Question", self.save_new_question, width=25)
        self.add_button("Back to Manage", self.show_manage_screen, width=25)
        self.add_menu_back_button()

    def save_new_question(self):
        grammar_id_text = self.question_grammar_id_entry.get().strip()
        difficulty = self.question_difficulty_var.get()
        question_text = self.question_text_box.get("1.0", "end").strip()
        explanation = self.question_explanation_box.get("1.0", "end").strip()

        choices = []
        choice_grammar_ids = []

        for entry in self.choice_entries:
            choices.append(entry.get().strip())

        for entry in self.choice_grammar_id_entries:
            grammar_id_text_for_choice = entry.get().strip()

            if grammar_id_text_for_choice == "":
                choice_grammar_ids.append(None)
            elif grammar_id_text_for_choice.isdigit():
                choice_grammar_ids.append(int(grammar_id_text_for_choice))
            else:
                messagebox.showwarning(
                    "Invalid Choice Grammar ID",
                    "Choice Grammar ID must be blank or a number."
                )
                return

        correct_choice_number = self.correct_choice_var.get()

        if not grammar_id_text.isdigit():
            messagebox.showwarning(
                "Invalid Grammar ID",
                "Grammar ID must be a number."
            )
            return

        grammar_id = int(grammar_id_text)

        if question_text == "":
            messagebox.showwarning(
                "Missing question",
                "Question text is required."
            )
            return

        if explanation == "":
            messagebox.showwarning(
                "Missing explanation",
                "Explanation is required."
            )
            return

        for choice in choices:
            if choice == "":
                messagebox.showwarning(
                    "Missing choice",
                    "All 4 choices are required."
                )
                return

        conn = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            SELECT id
            FROM grammar_points
            WHERE id = ?
            """, (grammar_id,))

            grammar_row = cursor.fetchone()

            if grammar_row is None:
                messagebox.showwarning(
                    "Grammar not found",
                    f"No grammar point found with ID {grammar_id}."
                )
                return

            for choice_grammar_id in choice_grammar_ids:
                if choice_grammar_id is None:
                    continue

                cursor.execute("""
                SELECT id
                FROM grammar_points
                WHERE id = ?
                """, (choice_grammar_id,))

                choice_grammar_row = cursor.fetchone()

                if choice_grammar_row is None:
                    messagebox.showwarning(
                        "Choice Grammar ID not found",
                        f"No grammar point found with ID {choice_grammar_id}."
                    )
                    return

            cursor.execute("""
            INSERT INTO questions (
                grammar_id,
                question_text,
                explanation,
                difficulty
            )
            VALUES (?, ?, ?, ?)
            """, (
                grammar_id,
                question_text,
                explanation,
                difficulty
            ))

            question_id = cursor.lastrowid

            for index, choice_text in enumerate(choices, start=1):
                is_correct = 1 if index == correct_choice_number else 0
                choice_grammar_id = choice_grammar_ids[index - 1]

                cursor.execute("""
                INSERT INTO choices (
                    question_id,
                    choice_number,
                    choice_text,
                    is_correct,
                    grammar_id
                )
                VALUES (?, ?, ?, ?, ?)
                """, (
                    question_id,
                    index,
                    choice_text,
                    is_correct,
                    choice_grammar_id
                ))

            conn.commit()

            messagebox.showinfo(
                "Question Added",
                f"Question was added successfully.\nNew question ID: {question_id}"
            )

            self.show_manage_screen()

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not add question.\n\n{error}"
            )

        finally:
            if conn is not None:
                conn.close()

    # -----------------------------
    # Reset progress screen
    # -----------------------------

    def show_reset_progress_screen(self):
        self.clear_screen()

        self.add_title("Reset Progress")

        warning_text = (
            f'Current user: {self.current_user["username"]}\n\n'
            "This will delete:\n"
            "- answer history\n"
            "- correct/wrong counts\n"
            "- mastery levels\n\n"
            "Grammar points and questions will NOT be deleted.\n\n"
            "Type RESET below to confirm."
        )

        tk.Label(
            self.root,
            text=warning_text,
            font=("Arial", 12),
            justify="left",
            wraplength=780
        ).pack(pady=10)

        self.reset_entry = tk.Entry(self.root, width=30)
        self.reset_entry.pack(pady=10)

        self.add_button("Reset My Progress", self.perform_reset_progress)
        self.add_menu_back_button()

    def perform_reset_progress(self):
        confirm_text = self.reset_entry.get().strip()

        if confirm_text != "RESET":
            messagebox.showwarning(
                "Reset cancelled",
                "You must type RESET exactly to confirm."
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Reset",
            "Are you sure you want to delete this user's progress?"
        )

        if not confirm:
            return

        reset_user_progress(self.current_user["id"])

        messagebox.showinfo(
            "Progress Reset",
            "Progress was reset successfully."
        )

        self.show_main_menu()


if __name__ == "__main__":
    root = tk.Tk()
    app = JLPTGrammarApp(root)
    root.mainloop()