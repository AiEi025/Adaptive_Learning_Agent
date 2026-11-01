
from collections.abc import Iterable

from graph.assessment import (
    AssessmentAnswer,
    AssessmentDefinition,
    AssessmentResult,
    CriterionScore,
    QuestionResult,
)

# --------------------------------------------------
# ابزارهای عمومی
# --------------------------------------------------

def normalize_answer(text: str) -> str:
    """
    نرمال‌سازی پاسخ برای مقایسه دقیق.
    فاصله‌های اضافی حذف و حروف کوچک می‌شوند.
    """
    return " ".join(text.strip().casefold().split())


def calculate_percentage(earned_points: float, total_points: float) -> float:
    """
    محاسبه درصد نهایی آزمون.
    """
    if total_points <= 0:
        raise ValueError("نمره کل آزمون باید بزرگ‌تر از صفر باشد.")

    percentage = (earned_points / total_points) * 100

    return round(percentage, 2)


# --------------------------------------------------
# ارزیابی سؤال چندگزینه‌ای
# --------------------------------------------------

def grade_multiple_choice(
    question,
    answer: AssessmentAnswer,
) -> QuestionResult:
    """
    تصحیح خودکار سؤال چندگزینه‌ای.
    """

    selected_option = answer.selected_option_id

    if selected_option is None:
        return QuestionResult(
            question_id=question.id,
            earned_points=0,
            max_points=question.points,
            is_correct=False,
            feedback="پاسخی برای این سؤال ثبت نشده است.",
        )

    is_correct = selected_option == question.correct_option_id

    earned_points = question.points if is_correct else 0

    if is_correct:
        feedback = "پاسخ شما صحیح است."
    else:
        feedback = "پاسخ شما صحیح نیست."

    return QuestionResult(
        question_id=question.id,
        earned_points=earned_points,
        max_points=question.points,
        is_correct=is_correct,
        feedback=feedback,
    )


# --------------------------------------------------
# ارزیابی سؤال کوتاه‌پاسخ
# --------------------------------------------------

def grade_short_answer(
    question,
    answer: AssessmentAnswer,
) -> QuestionResult:
    """
    در این نسخه، پاسخ کوتاه فقط با پاسخ مرجع
    و به‌صورت تطبیق دقیق بررسی می‌شود.

    ارزیابی معنایی در مرحله بعد با LLM اضافه خواهد شد.
    """

    user_answer = answer.answer_text or ""
    expected_answer = question.expected_answer or ""

    if not user_answer.strip():
        return QuestionResult(
            question_id=question.id,
            earned_points=0,
            max_points=question.points,
            is_correct=False,
            feedback="پاسخی برای این سؤال ثبت نشده است.",
        )

    if not expected_answer.strip():
        raise ValueError(
            f"سؤال {question.id} پاسخ مرجع ندارد؛ "
            "برای ارزیابی آن باید از ارزیاب بیرونی استفاده شود."
        )

    is_correct = (
        normalize_answer(user_answer)
        == normalize_answer(expected_answer)
    )

    earned_points = question.points if is_correct else 0

    return QuestionResult(
        question_id=question.id,
        earned_points=earned_points,
        max_points=question.points,
        is_correct=is_correct,
        feedback=(
            "پاسخ شما صحیح است."
            if is_correct
            else "پاسخ شما با پاسخ مرجع مطابقت ندارد."
        ),
    )


# --------------------------------------------------
# دریافت نتیجه ارزیاب بیرونی
# --------------------------------------------------

def validate_external_result(
    question,
    criterion_scores: Iterable[CriterionScore],
    feedback: str = "",
) -> QuestionResult:
    criterion_scores = list(criterion_scores)

    rubric_by_id = {
        criterion.id: criterion
        for criterion in question.rubric
    }

    if not rubric_by_id:
        raise ValueError(
            f"Question {question.id} has no evaluation rubric."
        )

    received_ids = [
        item.criterion_id for item in criterion_scores
    ]

    if len(received_ids) != len(set(received_ids)):
        raise ValueError("Duplicate rubric criteria were received.")

    unknown_ids = set(received_ids) - set(rubric_by_id)

    if unknown_ids:
        raise ValueError(
            f"Unknown rubric criteria: {unknown_ids}"
        )

    missing_ids = set(rubric_by_id) - set(received_ids)

    if missing_ids:
        raise ValueError(
            f"Missing rubric criteria: {missing_ids}"
        )

    for item in criterion_scores:
        criterion = rubric_by_id[item.criterion_id]

        if item.earned_points > criterion.max_points:
            raise ValueError(
                f"Score for criterion {item.criterion_id} "
                "exceeds its maximum points."
            )

    earned_points = sum(
        item.earned_points for item in criterion_scores
    )

    rubric_total = sum(
        criterion.max_points
        for criterion in question.rubric
    )

    if rubric_total <= 0:
        raise ValueError("The total rubric points must be positive.")

    normalized_score = round(
        (earned_points / rubric_total) * question.points,
        2,
    )

    return QuestionResult(
        question_id=question.id,
        earned_points=normalized_score,
        max_points=question.points,
        is_correct=normalized_score == question.points,
        feedback=feedback,
        criterion_scores=criterion_scores,
    )
# --------------------------------------------------
# ارزیابی یک سؤال
# --------------------------------------------------

def grade_question(
    question,
    answer: AssessmentAnswer | None,
    external_result: QuestionResult | None = None,
) -> QuestionResult:
    def unanswered_result() -> QuestionResult:
        return QuestionResult(
            question_id=question.id,
            earned_points=0,
            max_points=question.points,
            is_correct=False,
            feedback="This question was not answered.",
        )

    if answer is None:
        if external_result is not None:
            raise ValueError(
                "External evaluation cannot be provided for an unanswered question."
            )
        return unanswered_result()

    if answer.question_id != question.id:
        raise ValueError(
            "Answer question ID does not match."
        )

    has_answer = any(
        value and value.strip()
        for value in (
            answer.selected_option_id,
            answer.answer_text,
            answer.code,
        )
    )

    if not has_answer:
        if external_result is not None:
            raise ValueError(
                "External evaluation cannot be provided for an empty answer."
            )
        return unanswered_result()

    if external_result is not None:
        if external_result.question_id != question.id:
            raise ValueError(
                "External result question ID does not match."
            )

        if external_result.max_points != question.points:
            raise ValueError(
                "External result maximum points do not match."
            )

        if not question.rubric:
            raise ValueError(
                f"Question {question.id} has no evaluation rubric."
            )

        if question.type not in {
            "essay",
            "practical",
            "coding",
        } and not (
            question.type == "short_answer"
            and not question.expected_answer
        ):
            raise ValueError(
                "External evaluation is not allowed for this question type."
            )

        return validate_external_result(
            question=question,
            criterion_scores=external_result.criterion_scores,
            feedback=external_result.feedback,
        )

    if question.type == "multiple_choice":
        return grade_multiple_choice(question, answer)

    if question.type == "short_answer":
        if question.expected_answer:
            return grade_short_answer(question, answer)

        raise ValueError(
            f"Short-answer question {question.id} "
            "requires external evaluation."
        )

    if question.type in {"essay", "practical", "coding"}:
        raise ValueError(
            f"Question {question.id} of type {question.type} "
            "requires external evaluation."
        )

    raise ValueError(
        f"Unsupported question type: {question.type}"
    )

# --------------------------------------------------
# ارزیابی کل آزمون
# --------------------------------------------------

def grade_assessment(
    assessment: AssessmentDefinition,
    answers: list[AssessmentAnswer],
    external_results: list[QuestionResult] | None = None,
    summary: str = "",
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> AssessmentResult:
    """
    ارزیابی تمام سؤال‌های یک آزمون و ساخت نتیجه نهایی.

    answers:
        پاسخ‌های کاربر

    external_results:
        نتیجه ارزیابی سؤال‌هایی که به ارزیاب بیرونی
        (مثلاً LLM یا اجراکننده کد ایزوله) نیاز دارند.
    """

    external_results = external_results or []

    answer_map = {
        answer.question_id: answer
        for answer in answers
    }

    if len(answer_map) != len(answers):
        raise ValueError(
            "برای یک سؤال چند پاسخ متفاوت ارسال شده است."
        )

    question_map = {
        question.id: question
        for question in assessment.questions
    }

    unknown_answer_ids = set(answer_map) - set(question_map)

    if unknown_answer_ids:
        raise ValueError(
            f"پاسخ برای سؤال‌های ناشناخته ارسال شده است: "
            f"{unknown_answer_ids}"
        )

    external_map = {
        result.question_id: result
        for result in external_results
    }

    if len(external_map) != len(external_results):
        raise ValueError(
            "برای یک سؤال چند نتیجه ارزیابی ارسال شده است."
        )

    unknown_result_ids = set(external_map) - set(question_map)

    if unknown_result_ids:
        raise ValueError(
            f"نتیجه برای سؤال‌های ناشناخته ارسال شده است: "
            f"{unknown_result_ids}"
        )

    question_results = []

    for question in assessment.questions:
        result = grade_question(
            question=question,
            answer=answer_map.get(question.id),
            external_result=external_map.get(question.id),
        )

        question_results.append(result)

    earned_points = sum(
        result.earned_points
        for result in question_results
    )

    total_points = assessment.total_points

    percentage = calculate_percentage(
        earned_points,
        total_points,
    )

    return AssessmentResult(
        earned_points=round(earned_points, 2),
        total_points=round(total_points, 2),
        score_percent=percentage,
        question_results=question_results,
        summary=summary,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        recommendations=recommendations or [],
    )