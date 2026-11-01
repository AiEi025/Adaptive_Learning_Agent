
from graph.assessment import (
    AssessmentDefinition,
    AssessmentQuestion,
    AssessmentAnswer,
    QuestionOption,
    RubricCriterion,
    CriterionScore,
)

from graph.assessment_engine import (
    grade_assessment,
    validate_external_result,
)


# --------------------------------
# آزمون چندگزینه‌ای
# --------------------------------

q1 = AssessmentQuestion(
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


# --------------------------------
# آزمون کوتاه‌پاسخ
# --------------------------------

q2 = AssessmentQuestion(
    id="q2",
    type="short_answer",
    prompt="پایتخت ایران چیست؟",
    points=2,
    expected_answer="تهران",
)


# --------------------------------
# آزمون تشریحی
# --------------------------------

q3 = AssessmentQuestion(
    id="q3",
    type="essay",
    prompt="یادگیری ماشین را توضیح دهید.",
    points=6,
    rubric=[
        RubricCriterion(
            id="c1",
            description="تعریف درست یادگیری ماشین",
            max_points=3,
        ),
        RubricCriterion(
            id="c2",
            description="ارائه مثال مناسب",
            max_points=3,
        ),
    ],
)


# --------------------------------
# تعریف آزمون
# --------------------------------

assessment = AssessmentDefinition(
    id="test-1",
    purpose="placement",
    title="آزمون آزمایشی",
    subject="دانش عمومی",
    questions=[q1, q2, q3],
)


# --------------------------------
# پاسخ‌های کاربر
# --------------------------------

answers = [
    AssessmentAnswer(
        question_id="q1",
        selected_option_id="b",
    ),
    AssessmentAnswer(
        question_id="q2",
        answer_text="تهران",
    ),
    AssessmentAnswer(
        question_id="q3",
        answer_text="یادگیری ماشین روشی برای یادگیری از داده‌ها است.",
    ),
]


# --------------------------------
# نتیجه ارزیاب بیرونی برای سؤال تشریحی
# --------------------------------

essay_result = validate_external_result(
    question=q3,
    criterion_scores=[
        CriterionScore(
            criterion_id="c1",
            earned_points=3,
            feedback="تعریف صحیح بود.",
        ),
        CriterionScore(
            criterion_id="c2",
            earned_points=2,
            feedback="مثال می‌توانست کامل‌تر باشد.",
        ),
    ],
    feedback="پاسخ خوبی بود.",
)


# --------------------------------
# ارزیابی کل آزمون
# --------------------------------

result = grade_assessment(
    assessment=assessment,
    answers=answers,
    external_results=[essay_result],
    summary="عملکرد خوبی داشتی.",
    strengths=["درک مفاهیم پایه"],
    weaknesses=["نیاز به تمرین بیشتر در مثال‌ها"],
    recommendations=["مطالعه مثال‌های بیشتر"],
)


print("عنوان آزمون:", assessment.title)
print("نمره کسب‌شده:", result.earned_points)
print("نمره کل:", result.total_points)
print("درصد:", result.score_percent)

print("\nنتیجه سؤال‌ها:")

for item in result.question_results:
    print(
        item.question_id,
        item.earned_points,
        "/",
        item.max_points,
        item.feedback,
    )