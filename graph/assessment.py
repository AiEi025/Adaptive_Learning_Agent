from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------
# انواع پایه
# --------------------------------------------------

AssessmentPurpose = Literal["placement", "learning"]

QuestionType = Literal[
    "multiple_choice",
    "short_answer",
    "essay",
    "practical",
    "coding",
]

AssessmentStatus = Literal["draft", "active", "archived"]

AttemptStatus = Literal["in_progress", "completed", "submitted"]


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------
# گزینه‌های سؤال چندگزینه‌ای
# --------------------------------------------------

class QuestionOption(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


# --------------------------------------------------
# معیارهای ارزیابی سؤال‌های تشریحی و عملی
# --------------------------------------------------

class RubricCriterion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    max_points: float = Field(gt=0)


# --------------------------------------------------
# تعریف سؤال
# --------------------------------------------------

class AssessmentQuestion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    type: QuestionType
    prompt: str = Field(min_length=1)

    points: float = Field(default=1, gt=0)

    options: list[QuestionOption] = Field(default_factory=list)
    correct_option_id: str | None = None

    expected_answer: str | None = None
    rubric: list[RubricCriterion] = Field(default_factory=list)

    explanation: str = ""

    @model_validator(mode="after")
    def validate_question(self):
        # گزینه‌های سؤال چندگزینه‌ای باید شناسه یکتا داشته باشند.
        option_ids = [option.id for option in self.options]

        if len(option_ids) != len(set(option_ids)):
            raise ValueError("شناسه گزینه‌های سؤال باید یکتا باشد.")

        if self.type == "multiple_choice":
            if len(self.options) < 2:
                raise ValueError(
                    "سؤال چندگزینه‌ای باید حداقل دو گزینه داشته باشد."
                )

            if self.correct_option_id not in option_ids:
                raise ValueError(
                    "گزینه صحیح باید به یکی از گزینه‌های سؤال اشاره کند."
                )

        elif self.correct_option_id is not None:
            raise ValueError(
                "correct_option_id فقط برای سؤال چندگزینه‌ای استفاده می‌شود."
            )

        # سؤال کوتاه‌پاسخ باید پاسخ مرجع یا معیار ارزیابی داشته باشد.
        if self.type == "short_answer":
            if not self.expected_answer and not self.rubric:
                raise ValueError(
                    "سؤال کوتاه‌پاسخ باید expected_answer یا rubric داشته باشد."
                )

        # برای سؤال‌های تشریحی، عملی و کدنویسی معیار ارزیابی لازم است.
        if self.type in {"essay", "practical", "coding"} and not self.rubric:
            raise ValueError(
                "این نوع سؤال باید حداقل یک معیار ارزیابی داشته باشد."
            )

        criterion_ids = [item.id for item in self.rubric]

        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("شناسه معیارهای ارزیابی باید یکتا باشد.")

        return self


# --------------------------------------------------
# تعریف کامل آزمون
# --------------------------------------------------

class AssessmentDefinition(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)

    purpose: AssessmentPurpose
    title: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    topic: str = ""

    instructions: str = ""

    questions: list[AssessmentQuestion] = Field(min_length=1)

    status: AssessmentStatus = "draft"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_assessment(self):
        question_ids = [question.id for question in self.questions]

        if len(question_ids) != len(set(question_ids)):
            raise ValueError("شناسه سؤال‌های آزمون باید یکتا باشد.")

        return self

    @property
    def total_points(self) -> float:
        return sum(question.points for question in self.questions)


# --------------------------------------------------
# پاسخ کاربر به یک سؤال
# --------------------------------------------------

class AssessmentAnswer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: str = Field(min_length=1)

    selected_option_id: str | None = None
    answer_text: str | None = None
    code: str | None = None

    submitted_at: datetime = Field(default_factory=utc_now)


# --------------------------------------------------
# نتیجه ارزیابی یک معیار
# --------------------------------------------------

class CriterionScore(BaseModel):
    criterion_id: str = Field(min_length=1)

    earned_points: float = Field(ge=0)
    feedback: str = ""


# --------------------------------------------------
# نتیجه ارزیابی یک سؤال
# --------------------------------------------------

class QuestionResult(BaseModel):
    question_id: str = Field(min_length=1)

    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)

    is_correct: bool | None = None
    feedback: str = ""

    criterion_scores: list[CriterionScore] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_score(self):
        if self.earned_points > self.max_points:
            raise ValueError("نمره کسب‌شده نمی‌تواند بیشتر از نمره سؤال باشد.")

        criterion_ids = [
            item.criterion_id for item in self.criterion_scores
        ]

        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("شناسه معیارهای ارزیابی باید یکتا باشد.")

        return self


# --------------------------------------------------
# نتیجه نهایی آزمون
# --------------------------------------------------

class AssessmentResult(BaseModel):
    earned_points: float = Field(ge=0)
    total_points: float = Field(gt=0)
    score_percent: float = Field(ge=0, le=100)

    question_results: list[QuestionResult] = Field(default_factory=list)

    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    evaluated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_result(self):
        if self.earned_points > self.total_points:
            raise ValueError("نمره کسب‌شده نمی‌تواند بیشتر از نمره کل باشد.")

        expected_percent = (
            self.earned_points / self.total_points
        ) * 100

        if abs(self.score_percent - expected_percent) > 0.01:
            raise ValueError("درصد نهایی با نمره کسب‌شده مطابقت ندارد.")

        question_ids = [
            item.question_id for item in self.question_results
        ]

        if len(question_ids) != len(set(question_ids)):
            raise ValueError("نتیجه هر سؤال باید فقط یک بار ثبت شود.")

        return self


# --------------------------------------------------
# یک نوبت شرکت کاربر در آزمون
# --------------------------------------------------

class AssessmentAttempt(BaseModel):
    id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)

    user_id: str = Field(min_length=1)
    thread_id: str = ""

    status: AttemptStatus = "in_progress"

    answers: list[AssessmentAnswer] = Field(default_factory=list)
    result: AssessmentResult | None = None

    started_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None

    @model_validator(mode="after")
    def validate_attempt(self):
        question_ids = [answer.question_id for answer in self.answers]

        if len(question_ids) != len(set(question_ids)):
            raise ValueError("برای هر سؤال فقط یک پاسخ ذخیره می‌شود.")

        return self