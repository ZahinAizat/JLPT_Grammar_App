from database import get_first_question, save_user_answer


question = get_first_question()

if question is None:
    print("No question found.")
else:
    print("=== QUESTION ===")
    print(question["question_text"])
    print()

    print("=== CHOICES ===")
    for choice in question["choices"]:
        print(f'{choice["choice_number"]}. {choice["choice_text"]}')

    print()
    selected_number = int(input("Choose answer number: "))

    selected_choice_id = None

    for choice in question["choices"]:
        if choice["choice_number"] == selected_number:
            selected_choice_id = choice["choice_id"]
            break

    if selected_choice_id is None:
        print("Invalid choice.")
    else:
        is_correct = save_user_answer(
            question["question_id"],
            selected_choice_id
        )

        if is_correct:
            print("Correct!")
        else:
            print("Wrong.")

        print()
        print("Explanation:")
        print(question["explanation"])