import random

from database import (
    get_all_users,
    get_or_create_user,
    get_weighted_question_excluding,
    get_weak_question_excluding,
    get_new_question_excluding,
    save_user_answer,
    get_review_progress,
    search_grammar_points,
    reset_user_progress,
    get_user_dashboard
)


COOLDOWN_SIZE = 2


def wait_for_enter(message="\nPress Enter to continue..."):
    while True:
        user_input = input(message)

        if user_input == "":
            return

        print("Invalid input. Please press Enter only.")
        message = "Press Enter only: "

def select_user():
    while True:
        users = get_all_users()

        print()
        print("=" * 50)
        print("Select User")
        print("=" * 50)

        if users:
            for index, user in enumerate(users, start=1):
                print(f'{index}. {user["username"]}')

        print("N. Create new user")
        print("Q. Quit")
        print()

        choice = input("Choose user number, N, or Q: ").strip()

        if choice.lower() == "q":
            return None

        if choice.lower() == "n":
            username = input("Enter new username: ").strip()

            if username == "":
                print("Username cannot be empty.")
                wait_for_enter()
                continue

            user = get_or_create_user(username)
            confirm_user(user)
            return user

        if choice.isdigit():
            selected_index = int(choice)

            if 1 <= selected_index <= len(users):
                user = users[selected_index - 1]
                confirm_user(user)
                return user

        print("Invalid user selection.")
        wait_for_enter()


def confirm_user(user):
    print()
    print("=" * 50)
    print("User Selected")
    print("=" * 50)
    print(f'Current user: {user["username"]}')
    wait_for_enter("\nPress Enter to continue to main menu...")


def format_accuracy(accuracy):
    if accuracy is None:
        return "N/A"

    return f"{accuracy:.1f}%"


def format_question_header_stats(question, selected_jlpt_level, selected_difficulty):
    total_asked = question["total_asked"]
    correct_count = question["correct_count"]

    if total_asked == 0:
        asked_text = "0/0"
    else:
        asked_text = f"{correct_count}/{total_asked}"

    accuracy_text = format_accuracy(question["accuracy"])
    mastery_text = question["mastery_level"]

    header_text = f"asked {asked_text}  accuracy {accuracy_text}  mastery: {mastery_text}"

    if selected_jlpt_level is None:
        header_text += f'  level: {question["jlpt_level"]}'

    if selected_difficulty is None:
        header_text += f'  difficulty: {question["difficulty"]}'

    return header_text

# untuk debugging
#def format_question_header_stats(question, selected_jlpt_level, selected_difficulty):
#    total_asked = question["total_asked"]
#    correct_count = question["correct_count"]
#
#    if total_asked == 0:
#        asked_text = "0/0"
#    else:
#        asked_text = f"{correct_count}/{total_asked}"
#
#    accuracy_text = format_accuracy(question["accuracy"])
#    mastery_text = question["mastery_level"]
#
#    header_text = f"asked {asked_text}  accuracy {accuracy_text}  mastery: {mastery_text}"
#    header_text += f'  level: {question["jlpt_level"]}'
#    header_text += f'  difficulty: {question["difficulty"]}'
#
#   return header_text


def select_jlpt_level():
    while True:
        print()
        print("=" * 50)
        print("Choose JLPT Level")
        print("=" * 50)
        print("1. All levels")
        print("2. N1 only")
        print("3. N2 only")
        print("Q. Return to menu")
        print()

        choice = input("Choose level: ").strip().lower()

        if choice == "1":
            return None

        if choice == "2":
            return "N1"

        if choice == "3":
            return "N2"

        if choice == "q":
            return "menu"

        print("Invalid level choice.")
        wait_for_enter()    


def select_question_limit():
    while True:
        print()
        print("=" * 50)
        print("Choose Number of Questions")
        print("=" * 50)
        print("1. 5 questions")
        print("2. 10 questions")
        print("3. 20 questions")
        print("4. Unlimited")
        print("Q. Return to menu")
        print()

        choice = input("Choose question count: ").strip().lower()

        if choice == "1":
            return 5

        if choice == "2":
            return 10

        if choice == "3":
            return 20

        if choice == "4":
            return None

        if choice == "q":
            return "menu"

        print("Invalid question count choice.")
        wait_for_enter()


def select_difficulty_filter():
    while True:
        print()
        print("=" * 50)
        print("Choose Difficulty")
        print("=" * 50)
        print("1. All difficulties")
        print("2. Easy only")
        print("3. Normal only")
        print("4. Hard only")
        print("Q. Return to menu")
        print()

        choice = input("Choose difficulty: ").strip().lower()

        if choice == "1":
            return None

        if choice == "2":
            return "easy"

        if choice == "3":
            return "normal"

        if choice == "4":
            return "hard"

        if choice == "q":
            return "menu"

        print("Invalid difficulty choice.")
        wait_for_enter()
  

def format_level_text(jlpt_level):
    if jlpt_level is None:
        return "All levels"

    return jlpt_level


def select_mastery_filter():
    while True:
        print()
        print("=" * 50)
        print("Choose Mastery Filter")
        print("=" * 50)
        print("1. All mastery levels")
        print("2. New only")
        print("3. Learning only")
        print("4. Weak only")
        print("5. Mastered only")
        print("Q. Return to menu")
        print()

        choice = input("Choose mastery filter: ").strip().lower()

        if choice == "1":
            return None

        if choice == "2":
            return "new"

        if choice == "3":
            return "learning"

        if choice == "4":
            return "weak"

        if choice == "5":
            return "mastered"

        if choice == "q":
            return "menu"

        print("Invalid mastery filter choice.")
        wait_for_enter()


def format_mastery_filter_text(mastery_filter):
    if mastery_filter is None:
        return "All mastery levels"

    return mastery_filter
    
        
def update_recent_questions(recent_question_ids, question_id):
    recent_question_ids.append(question_id)

    if len(recent_question_ids) > COOLDOWN_SIZE:
        recent_question_ids.pop(0)


def ask_one_question(user, question_getter, quiz_title, recent_question_ids, jlpt_level, difficulty_filter):
    question = question_getter(user["id"], recent_question_ids, jlpt_level, difficulty_filter)

    # If cooldown blocks all possible questions, clear cooldown and try again.
    if question is None and recent_question_ids:
        recent_question_ids.clear()
        question = question_getter(user["id"], recent_question_ids, jlpt_level, difficulty_filter)

    if question is None:
        print()
        print("No question found.")
        print(f"Mode: {quiz_title}")
        print(f"Level: {format_level_text(jlpt_level)}")

        if difficulty_filter is None:
            print("Difficulty: All difficulties")
        else:
            print(f"Difficulty: {difficulty_filter}")

        wait_for_enter("\nPress Enter to return...")
        return "no_question"

    #print("DEBUG difficulty:", question["difficulty"])

    display_choices = question["choices"].copy()
    random.shuffle(display_choices)

    if jlpt_level is None:
        level_text = "All"
    else:
        level_text = jlpt_level
    print()
    print("=" * 50)
    print(quiz_title)
    print("=" * 50)
    print(f'User: {user["username"]}')
    print(f"Level: {level_text}")

    print()
    print("Question:")
    print(format_question_header_stats(question, jlpt_level, difficulty_filter))
    print()
    print(question["question_text"])
    print()

    print("Choices:")
    for index, choice in enumerate(display_choices, start=1):
        print(f'{index}. {choice["choice_text"]}')

    print()
    user_input = input("Choose answer number, or type q to return to menu: ")

    if user_input.lower() == "q":
        return "menu"

    if not user_input.isdigit():
        print("Please enter a number.")
        wait_for_enter()
        return None

    selected_number = int(user_input)

    if selected_number < 1 or selected_number > len(display_choices):
        print("Invalid choice number.")
        wait_for_enter()
        return None

    selected_choice = display_choices[selected_number - 1]
    selected_choice_id = selected_choice["choice_id"]

    is_correct = save_user_answer(
        user["id"],
        question["question_id"],
        selected_choice_id
    )

    update_recent_questions(
        recent_question_ids,
        question["question_id"]
    )

    print()

    if is_correct:
        print("Correct!")
    else:
        print("Wrong.")

        correct_answer_text = None

        for choice in question["choices"]:
            if choice["is_correct"] == 1:
                correct_answer_text = choice["choice_text"]
                break

        if correct_answer_text is not None:
            print(f"Correct answer: {correct_answer_text}")

    print()
    print("Explanation:")
    print(question["explanation"])
    print()
    print("Grammar:")
    print(question["grammar"])
    print()
    print("Meaning:")
    print(question["meaning"])

    wait_for_enter("\nPress Enter for next question...")

    return is_correct


def show_session_score(total_answered, correct_count, wrong_count):
    print()
    print("=" * 50)
    print("Session Score")
    print("=" * 50)

    if total_answered == 0:
        print("No questions answered yet.")
    else:
        accuracy = correct_count / total_answered * 100

        print(f"Total answered: {total_answered}")
        print(f"Correct: {correct_count}")
        print(f"Wrong: {wrong_count}")
        print(f"Accuracy: {accuracy:.1f}%")

    print("=" * 50)


def start_quiz(user, question_getter, quiz_title):
    jlpt_level = select_jlpt_level()

    if jlpt_level == "menu":
        return
        
    difficulty_filter = select_difficulty_filter()

    if difficulty_filter == "menu":
        return
        
    question_limit = select_question_limit()

    if question_limit == "menu":
        return

    total_answered = 0
    correct_count = 0
    wrong_count = 0
    recent_question_ids = []

    while True:
        result = ask_one_question(
            user,
            question_getter,
            quiz_title,
            recent_question_ids,
            jlpt_level,
            difficulty_filter
        )

        if result == "no_question":
            break

        if result == "menu":
            show_session_score(total_answered, correct_count, wrong_count)
            wait_for_enter("\nPress Enter to return to menu...")
            break

        if result is True:
            total_answered += 1
            correct_count += 1
        elif result is False:
            total_answered += 1
            wrong_count += 1

        if question_limit is not None and total_answered >= question_limit:
            show_session_score(total_answered, correct_count, wrong_count)
            wait_for_enter("\nQuestion limit reached. Press Enter to return to menu...")
            break

def show_progress(user):
    jlpt_level = select_jlpt_level()

    if jlpt_level == "menu":
        return

    mastery_filter = select_mastery_filter()

    if mastery_filter == "menu":
        return

    progress_list = get_review_progress(
        user["id"],
        jlpt_level,
        mastery_filter
    )

    print()
    print("=" * 50)
    print("JLPT Grammar Review Progress")
    print("=" * 50)
    print(f'User: {user["username"]}')
    print(f'Level: {format_level_text(jlpt_level)}')
    print(f'Mastery filter: {format_mastery_filter_text(mastery_filter)}')

    if not progress_list:
        print()
        print("No grammar progress found for this filter.")
        wait_for_enter("\nPress Enter to return to menu...")
        return

    for item in progress_list:
        print()
        print(f'ID: {item["id"]}')
        print(f'Level: {item["jlpt_level"]}')
        print(f'Grammar: {item["grammar"]}')
        print(f'Meaning: {item["meaning"]}')
        print(f'Times asked: {item["total_asked"]}')
        print(f'Correct: {item["correct_count"]}')
        print(f'Wrong: {item["wrong_count"]}')
        print(f'Accuracy: {format_accuracy(item["accuracy"])}')
        print(f'Mastery: {item["mastery_level"]}')
        print(f'Last reviewed: {item["last_reviewed_at"]}')

    wait_for_enter("\nPress Enter to return to menu...")


def search_grammar_menu(user):
    print()
    print("=" * 50)
    print("Search Grammar")
    print("=" * 50)
    print("You can search by grammar, reading, romaji, meaning, formation, or example sentence.")
    print("Type q to return to menu.")
    print()

    keyword = input("Search keyword: ").strip()

    if keyword.lower() == "q":
        return

    if keyword == "":
        print("Search keyword cannot be empty.")
        wait_for_enter()
        return

    results = search_grammar_points(user["id"], keyword)

    print()
    print("=" * 50)
    print("Search Results")
    print("=" * 50)
    print(f'Keyword: {keyword}')
    print(f"Results found: {len(results)}")

    if not results:
        print()
        print("No matching grammar found.")
        wait_for_enter("\nPress Enter to return to menu...")
        return

    for item in results:
        print()
        print("-" * 50)
        print(f'ID: {item["id"]}')
        print(f'Level: {item["jlpt_level"]}')
        print(f'Grammar: {item["grammar"]}')
        print(f'Reading: {item["reading"]}')
        print(f'Romaji: {item["romaji"]}')
        print(f'Meaning: {item["meaning"]}')
        print(f'Formation: {item["formation"]}')
        print(f'Example: {item["example_sentence"]}')
        print(f'Translation: {item["example_translation"]}')
        print(f'Source: {item["source"]}')
        print()
        print("Your progress:")
        print(f'Times asked: {item["total_asked"]}')
        print(f'Correct: {item["correct_count"]}')
        print(f'Wrong: {item["wrong_count"]}')
        print(f'Accuracy: {format_accuracy(item["accuracy"])}')
        print(f'Mastery: {item["mastery_level"]}')
        print(f'Last reviewed: {item["last_reviewed_at"]}')

    wait_for_enter("\nPress Enter to return to menu...")


def reset_progress_menu(user):
    print()
    print("=" * 50)
    print("Reset Progress")
    print("=" * 50)
    print(f'Current user: {user["username"]}')
    print()
    print("This will delete:")
    print("- answer history")
    print("- correct/wrong counts")
    print("- mastery levels")
    print()
    print("Grammar points and questions will NOT be deleted.")
    print()

    confirm = input("Type RESET to confirm, or anything else to cancel: ")

    if confirm == "RESET":
        reset_user_progress(user["id"])
        print("Progress reset successfully.")
    else:
        print("Reset cancelled.")

    wait_for_enter()


def show_dashboard(user):
    jlpt_level = select_jlpt_level()

    if jlpt_level == "menu":
        return

    dashboard = get_user_dashboard(user["id"], jlpt_level)

    print()
    print("=" * 50)
    print("JLPT Grammar Dashboard")
    print("=" * 50)
    print(f'User: {user["username"]}')
    print(f'Level: {format_level_text(jlpt_level)}')
    print()

    print("Database:")
    print(f'Total grammar points: {dashboard["total_grammar"]}')
    print(f'Total questions: {dashboard["total_questions"]}')
    print()

    print("Answer Summary:")
    print(f'Total answered: {dashboard["total_answered"]}')
    print(f'Correct: {dashboard["correct_count"]}')
    print(f'Wrong: {dashboard["wrong_count"]}')
    print(f'Overall accuracy: {format_accuracy(dashboard["accuracy"])}')
    print()

    print("Mastery Summary:")
    print(f'New: {dashboard["new_count"]}')
    print(f'Learning: {dashboard["learning_count"]}')
    print(f'Weak: {dashboard["weak_count"]}')
    print(f'Mastered: {dashboard["mastered_count"]}')
    print()

    if dashboard["total_questions"] == 0:
        print("Recommended next action:")
        print("Import questions for this JLPT level.")
    elif dashboard["weak_count"] > 0:
        print("Recommended next action:")
        print("Review weak grammar.")
    elif dashboard["total_answered"] == 0:
        print("Recommended next action:")
        print("Start weighted quiz.")
    else:
        print("Recommended next action:")
        print("Continue weighted quiz.")

    wait_for_enter("\nPress Enter to return to menu...")    


def show_menu(user):
    print()
    print("=" * 50)
    print("JLPT Grammar App")
    print("=" * 50)
    print(f'Current user: {user["username"]}')
    print()
    print("1. Start weighted quiz")
    print("2. Review weak grammar")
    print("3. Study new grammar")
    print("4. Dashboard")
    print("5. View progress")
    print("6. Search grammar")
    print("7. Reset current user progress")
    print("8. Switch user")
    print("9. Exit")
    print()


def main_menu(user):
    while True:
        show_menu(user)

        choice = input("Choose menu number: ")

        if choice == "1":
            start_quiz(
                user,
                get_weighted_question_excluding,
                "JLPT Weighted Quiz"
            )

        elif choice == "2":
            start_quiz(
                user,
                get_weak_question_excluding,
                "Weak Grammar Review"
            )

        elif choice == "3":
            start_quiz(
                user,
                get_new_question_excluding,
                "Study New Grammar"
            )

        elif choice == "4":
            show_dashboard(user)

        elif choice == "5":
            show_progress(user)

        elif choice == "6":
            search_grammar_menu(user)

        elif choice == "7":
            reset_progress_menu(user)

        elif choice == "8":
            return "switch"

        elif choice == "9":
            print("Goodbye!")
            return "exit"

        else:
            print("Invalid menu choice.")
            wait_for_enter()


def main():
    while True:
        user = select_user()

        if user is None:
            print("Goodbye!")
            break

        result = main_menu(user)

        if result == "exit":
            break


if __name__ == "__main__":
    main()