from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from graph.assessment import AssessmentDefinition
from graph.assessment_engine import grade_assessment
from graph.nodes import GENERATE_LLM, get_llm


def _build_assessment_prompt(
    purpose: str,
    subject: str,
    topic: str,
    level: str,
    question_count: int,
) -> str:
    purpose_description = {
        "placement": (
            "This assessment is intended to determine the user's prior knowledge level. "
            "Do not assume that the user has previously learned this topic with Adapta."
        ),
        "learning": (
            "This assessment is intended to measure how much the user has learned. "
            "The questions should focus on content that the user has learned."
        ),
    }

    return f"""
Design a standard educational assessment in Persian.

Assessment purpose:
{purpose_description[purpose]}

Subject: {subject}
Topic: {topic or "Whole subject"}
Expected level: {level}
Number of questions: exactly {question_count}

Design rules:
- Questions must be clear, precise, and relevant to the subject.
- Avoid duplicate and ambiguous questions.
- Question difficulty should match the expected level.
- Use different question types, but most questions should be multiple-choice.
- For multiple-choice questions, define at least four options.
- Option IDs within each question must be unique.
- correct_option_id must refer to one of the option IDs.
- For short-answer questions, specify expected_answer.
- For essay, practical, and coding questions, define rubric criteria.
- The total points must be reasonable and positive.
- Write a short explanation for each question.
- All question and option IDs must be unique.
- Do not include any correct answer in the question prompt text.

The output must conform to the AssessmentDefinition structure.
"""


async def generate_assessment(
    purpose: str,
    subject: str,
    topic: str = "",
    level: str = "Beginner",
    question_count: int = 5,
) -> AssessmentDefinition:
    """
    Generate an assessment definition using an LLM.
    The final output is validated with AssessmentDefinition.
    """

    if purpose not in {"placement", "learning"}:
        raise ValueError("Assessment purpose must be either 'placement' or 'learning'.")

    if not subject.strip():
        raise ValueError("Assessment subject cannot be empty.")

    if not 1 <= question_count <= 20:
        raise ValueError("Question count must be between 1 and 20.")

    prompt = _build_assessment_prompt(
        purpose=purpose,
        subject=subject.strip(),
        topic=topic.strip(),
        level=level.strip(),
        question_count=question_count,
    )

    llm = get_llm(
        GENERATE_LLM,
        reasoning_effort="none",
    )

    structured_llm = llm.with_structured_output(AssessmentDefinition)

    try:
        assessment = await structured_llm.ainvoke(prompt)

        # Generate the assessment ID in the application,
        # not by the model.
        assessment.id = str(uuid4())
        assessment.status = "draft"

        return AssessmentDefinition.model_validate(
            assessment.model_dump()
        )

    except ValidationError as exc:
        raise ValueError(
            "The generated assessment structure is invalid."
        ) from exc


async def create_and_save_assessment(
    backend,
    purpose: str,
    subject: str,
    topic: str = "",
    level: str = "Beginner",
    question_count: int = 5,
) -> AssessmentDefinition:
    """
    Generate an assessment, save it, and return its definition.
    """

    assessment = await generate_assessment(
        purpose=purpose,
        subject=subject,
        topic=topic,
        level=level,
        question_count=question_count,
    )

    assessment.status = "active"

    await backend.save_assessment(assessment)

    return assessment

async def submit_assessment_attempt(
    backend,
    attempt_id: str,
    user_id: str,
    external_results=None,
    summary: str = "",
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    recommendations: list[str] | None = None,
):
    attempt = await backend.get_assessment_attempt(
        attempt_id,
        user_id,
    )

    if attempt is None:
        raise ValueError("Assessment attempt not found.")

    if attempt.status != "in_progress":
        raise ValueError("This assessment attempt is not in progress.")

    assessment = await backend.get_assessment(attempt.assessment_id)

    if assessment is None:
        raise ValueError("Assessment not found.")

    answer_map = {
        answer.question_id: answer
        for answer in attempt.answers
    }

    question_map = {
        question.id: question
        for question in assessment.questions
    }

    unknown_answer_ids = set(answer_map) - set(question_map)

    if unknown_answer_ids:
        raise ValueError("Answers contain unknown question IDs.")

    external_question_types = {"essay", "practical", "coding"}

    for question in assessment.questions:
        if question.id not in answer_map:
            continue

        if question.type in external_question_types:
            if not external_results or question.id not in {
                result.question_id for result in external_results
            }:
                raise ValueError(
                    f"Question {question.id} requires external evaluation."
                )

        if (
            question.type == "short_answer"
            and not question.expected_answer
            and not any(
                result.question_id == question.id
                for result in (external_results or [])
            )
        ):
            raise ValueError(
                f"Question {question.id} requires external evaluation."
            )

    result = grade_assessment(
        assessment=assessment,
        answers=attempt.answers,
        external_results=external_results,
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
    )

    attempt.result = result
    attempt.status = "completed"
    attempt.submitted_at = datetime.now(timezone.utc)

    await backend.save_assessment_attempt(attempt)

    return attempt
