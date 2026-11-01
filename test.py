
import asyncio
from uuid import uuid4

from app import get_backend

from graph.assessment import (
    AssessmentAnswer,
    AssessmentAttempt,
)

from graph.assessment_service import (
    submit_assessment_attempt,
)


ASSESSMENT_ID = "5b1a66a4-bb3c-4791-9d0c-b83ff23de6dd"
TEST_USER_ID = "test_user_001"
TEST_THREAD_ID = "test_thread_001"


async def main():
    backend = get_backend()

    # Step 1: Load the assessment
    assessment = await backend.get_assessment(ASSESSMENT_ID)

    if assessment is None:
        raise ValueError("Assessment not found.")

    print("\nAssessment loaded successfully.")
    print("Title:", assessment.title)
    print("Question count:", len(assessment.questions))

    # Step 2: Create a new assessment attempt
    attempt = AssessmentAttempt(
        id=str(uuid4()),
        assessment_id=assessment.id,
        user_id=TEST_USER_ID,
        thread_id=TEST_THREAD_ID,
        status="in_progress",
        answers=[],
    )

    await backend.create_assessment_attempt(attempt)

    print("\nAssessment attempt created.")
    print("Attempt ID:", attempt.id)
    print("Status:", attempt.status)

    # Step 3: Generate test answers
    answers = []

    for question in assessment.questions:
        if question.type == "multiple_choice":
            answer = AssessmentAnswer(
                question_id=question.id,
                selected_option_id=question.correct_option_id,
            )

        elif question.type == "short_answer":
            answer = AssessmentAnswer(
                question_id=question.id,
                answer_text=question.expected_answer,
            )

        else:
            continue

        answers.append(answer)

    print("\nGenerated answers:")

    for answer in answers:
        print(
            "Question ID:",
            answer.question_id,
            "| Selected option:",
            answer.selected_option_id,
            "| Text:",
            answer.answer_text,
        )

    # Step 4: Save answers
    attempt.answers = answers

    await backend.save_assessment_attempt(attempt)

    print("\nAnswers saved successfully.")
    print("Saved answer count:", len(attempt.answers))

    # Step 5: Verify saved answers
    saved_attempt = await backend.get_assessment_attempt(
        attempt.id,
        TEST_USER_ID,
    )

    if saved_attempt is None:
        raise ValueError("Saved attempt could not be loaded.")

    print("\nAnswers loaded from database.")
    print("Reloaded answer count:", len(saved_attempt.answers))

    for answer in saved_attempt.answers:
        print(
            "Question ID:",
            answer.question_id,
            "| Selected option:",
            answer.selected_option_id,
            "| Text:",
            answer.answer_text,
            "| Code:",
            answer.code,
        )

    # Step 6: Submit assessment and calculate the result
    completed_attempt = await submit_assessment_attempt(
        backend=backend,
        attempt_id=attempt.id,
        user_id=TEST_USER_ID,
    )

    print("\nAssessment submitted successfully.")
    print("Status:", completed_attempt.status)

    if completed_attempt.result is None:
        raise ValueError("Assessment result was not generated.")

    print("Earned points:", completed_attempt.result.earned_points)
    print("Total points:", completed_attempt.result.total_points)
    print("Score:", completed_attempt.result.score_percent)

    # Step 7: Display individual question results
    print("\nQuestion results:")

    for question_result in completed_attempt.result.question_results:
        print(
            "Question ID:",
            question_result.question_id,
            "| Earned:",
            question_result.earned_points,
            "| Maximum:",
            question_result.max_points,
            "| Correct:",
            question_result.is_correct,
        )

    # Step 8: Verify final result in database
    final_attempt = await backend.get_assessment_attempt(
        attempt.id,
        TEST_USER_ID,
    )

    if final_attempt is None:
        raise ValueError("Final attempt could not be loaded.")

    print("\nFinal attempt loaded from database.")
    print("Status:", final_attempt.status)
    print("Has result:", final_attempt.result is not None)

    if final_attempt.result:
        print("Saved score:", final_attempt.result.score_percent)

    print("\nAll assessment tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
