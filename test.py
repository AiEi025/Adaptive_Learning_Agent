from graph.assessment import (
    AssessmentDefinition,
    AssessmentQuestion,
    QuestionOption,
)

question = AssessmentQuestion(
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

assessment = AssessmentDefinition(
    id="test-1",
    purpose="placement",
    title="آزمون تعیین سطح ریاضی",
    subject="ریاضی",
    questions=[question],
)

print("عنوان:", assessment.title)
print("تعداد سؤال:", len(assessment.questions))
print("نمره کل:", assessment.total_points)