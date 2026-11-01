
import uuid

from async_runner import AsyncRunner
from graph.assessment import (
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentDefinition,
    AssessmentQuestion,
    QuestionOption,
)

runner = AsyncRunner()


try:
    # ساخت آزمون آزمایشی
    assessment_id = str(uuid.uuid4())

    assessment = AssessmentDefinition(
        id=assessment_id,
        purpose="placement",
        title="آزمون آزمایشی تعیین سطح",
        subject="ریاضی",
        topic="مفاهیم پایه",
        questions=[
            AssessmentQuestion(
                id="q1",
                type="multiple_choice",
                prompt="حاصل ۲ + ۲ چیست؟",
                points=2,
                options=[
                    QuestionOption(id="a", text="۳"),
                    QuestionOption(id="b", text="۴"),
                ],
                correct_option_id="b",
            )
        ],
    )

    # ذخیره آزمون
    runner.run(
        runner.save_assessment(assessment),
        timeout=60,
    )

    # بازیابی آزمون
    loaded = runner.run(
        runner.get_assessment(assessment_id),
        timeout=60,
    )

    assert loaded is not None
    assert loaded.id == assessment_id
    assert loaded.total_points == 2

    print("Assessment save/load: OK")

    # ایجاد تلاش کاربر
    attempt_id = str(uuid.uuid4())

    attempt = AssessmentAttempt(
        id=attempt_id,
        assessment_id=assessment_id,
        user_id="test-user-1",
        answers=[
            AssessmentAnswer(
                question_id="q1",
                selected_option_id="b",
            )
        ],
    )

    runner.run(
        runner.create_assessment_attempt(attempt),
        timeout=60,
    )

    # بازیابی تلاش توسط صاحب آن
    loaded_attempt = runner.run(
        runner.get_assessment_attempt(
            attempt_id,
            "test-user-1",
        ),
        timeout=60,
    )

    assert loaded_attempt is not None
    assert loaded_attempt.user_id == "test-user-1"
    assert len(loaded_attempt.answers) == 1

    print("Attempt save/load: OK")

    # بررسی جداسازی کاربران
    unauthorized_attempt = runner.run(
        runner.get_assessment_attempt(
            attempt_id,
            "test-user-2",
        ),
        timeout=60,
    )

    assert unauthorized_attempt is None

    print("User isolation: OK")

    # بررسی تاریخچه
    history = runner.run(
        runner.get_assessment_history("test-user-1"),
        timeout=60,
    )

    assert any(item.id == attempt_id for item in history)

    print("Assessment history: OK")

finally:
    runner.close()
