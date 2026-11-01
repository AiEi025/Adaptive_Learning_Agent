from uuid import uuid4

from pydantic import ValidationError

from graph.assessment import AssessmentDefinition
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