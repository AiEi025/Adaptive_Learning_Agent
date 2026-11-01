from datetime import UTC, datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from graph.assessment import (
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentDefinition,
    AssessmentFeedback,
    CriterionScore,
    ExternalEvaluation,
    QuestionResult,
)
from graph.assessment_engine import grade_assessment, validate_external_result
from graph.nodes import GENERATE_LLM, get_llm


def _build_assessment_prompt(
    purpose: str,
    subject: str,
    topic: str,
    level: str,
    question_count: int,
    approach: str,
    question_types: list[str],
    custom_instructions: str,
) -> str:
    purpose_description = {
        "placement": (
            "This assessment is intended to determine the user's prior knowledge level. "
            "Do not assume that the user has previously learned this topic with Adapta. "
            "Start with easy questions and gradually increase difficulty."
        ),
        "learning": (
            "This assessment is intended to measure how much the user has learned. "
            "Focus only on the specified learned topics."
        ),
    }

    approach_descriptions = {
        "balanced": (
            "Use a balanced combination of conceptual understanding, "
            "reasoning, and practical application."
        ),
        "conceptual": (
            "Focus on deep conceptual understanding, explanations, "
            "relationships between concepts, and reasoning."
        ),
        "practical": (
            "Focus on practical problem-solving, realistic scenarios, "
            "and applying knowledge to real-world situations."
        ),
        "challenging": (
            "Use challenging questions that test advanced reasoning, "
            "edge cases, and complex problem-solving."
        ),
        "custom": (
            "Follow the user's custom instructions carefully."
        ),
    }

    selected_types = ", ".join(question_types)

    return f"""
Design an educational assessment in Persian.

Assessment purpose:
{purpose_description[purpose]}

Subject: {subject}
Topic: {topic or "Whole subject"}
Expected level: {level}

Number of questions: exactly {question_count}

Selected question types:
{selected_types}

Assessment approach:
{approach_descriptions[approach]}

Custom instructions:
{custom_instructions or "No additional instructions."}

Question design rules:
- Generate exactly {question_count} questions.
- Use only these question types: {selected_types}.
- Do not generate any question type that was not selected.
- If only multiple_choice is selected, every question must be multiple_choice.
- Distribute selected question types reasonably across the assessment.
- Questions must be clear, precise, and relevant to the subject.
- Avoid duplicate and ambiguous questions.
- For placement assessments, arrange questions from easier to harder.
- For learning assessments, focus on the selected learned topics.
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
    approach: str = "balanced",
    question_types: list[str] | None = None,
    custom_instructions: str = "",
) -> AssessmentDefinition:

    if purpose not in {"placement", "learning"}:
        raise ValueError(
            "Assessment purpose must be either 'placement' or 'learning'."
        )

    if not subject.strip():
        raise ValueError("Assessment subject cannot be empty.")

    if not 1 <= question_count <= 20:
        raise ValueError("Question count must be between 1 and 20.")

    allowed_approaches = {
        "balanced",
        "conceptual",
        "practical",
        "challenging",
        "custom",
    }

    if approach not in allowed_approaches:
        raise ValueError("Invalid assessment approach.")

    allowed_types = {
        "multiple_choice",
        "short_answer",
        "essay",
        "practical",
        "coding",
    }

    if question_types is None:
        question_types = ["multiple_choice"]

    if not question_types:
        raise ValueError("At least one question type must be selected.")

    if len(question_types) != len(set(question_types)):
        raise ValueError("Question types must be unique.")

    if not set(question_types).issubset(allowed_types):
        raise ValueError("One or more question types are invalid.")

    prompt = _build_assessment_prompt(
        purpose=purpose,
        subject=subject.strip(),
        topic=topic.strip(),
        level=level.strip(),
        question_count=question_count,
        approach=approach,
        question_types=question_types,
        custom_instructions=custom_instructions.strip(),
    )

    llm = get_llm(
        GENERATE_LLM,
        reasoning_effort="none",
    )

    structured_llm = llm.with_structured_output(AssessmentDefinition)

    try:
        assessment = await structured_llm.ainvoke(prompt)

        assessment.id = str(uuid4())
        assessment.status = "draft"

        assessment.approach = approach
        assessment.question_types = question_types
        assessment.question_count = question_count
        assessment.custom_instructions = custom_instructions.strip()

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
    approach: str = "balanced",
    question_types: list[str] | None = None,
    custom_instructions: str = "",
) -> AssessmentDefinition:

    assessment = await generate_assessment(
        purpose=purpose,
        subject=subject,
        topic=topic,
        level=level,
        question_count=question_count,
        approach=approach,
        question_types=question_types,
        custom_instructions=custom_instructions,
    )

    assessment.status = "active"

    await backend.save_assessment(assessment)

    return assessment

async def evaluate_open_question(
    question,
    answer: AssessmentAnswer,
) -> QuestionResult:
    if question.type == "coding":
        answer_content = answer.code or ""
    else:
        answer_content = answer.answer_text or ""

    if not answer_content.strip():
        raise ValueError(
            f"Question {question.id} has no answer to evaluate."
        )

    rubric_data = [
        {
            "criterion_id": criterion.id,
            "description": criterion.description,
            "max_points": criterion.max_points,
        }
        for criterion in question.rubric
    ]

    prompt = f"""
You are an objective educational assessment evaluator.

Evaluate the learner's answer using only the question and the
provided rubric.

Question type:
{question.type}

Question:
{question.prompt}

Maximum question points:
{question.points}

Expected answer, if available:
{question.expected_answer or "No reference answer provided."}

Learner's answer:
{answer_content}

Evaluation rubric:
{rubric_data}

Instructions:
1. Evaluate every rubric criterion exactly once.
2. Use the exact criterion_id provided in the rubric.
3. Award each criterion a score between zero and its max_points.
4. Do not exceed the maximum points of any criterion.
5. Do not invent additional criteria.
6. Evaluate correctness, completeness, and relevance.
7. For coding answers, evaluate the code logically. Do not claim
   that code was executed or tested.
8. Be fair and do not award points for unsupported claims.
9. Write concise, constructive feedback.
10. Return criterion scores and feedback in the required structure.
"""

    llm = get_llm(
        GENERATE_LLM,
        reasoning_effort="none",
    ).with_structured_output(ExternalEvaluation)

    evaluation = await llm.ainvoke(prompt)

    return validate_external_result(
        question=question,
        criterion_scores=evaluation.criterion_scores,
        feedback=evaluation.feedback,
    )
async def generate_assessment_feedback(
    assessment,
    answers,
    result,
) -> AssessmentFeedback:
    answer_map = {
        answer.question_id: answer
        for answer in answers
    }

    question_map = {
        question.id: question
        for question in assessment.questions
    }

    performance_data = []

    for question_result in result.question_results:
        question = question_map[question_result.question_id]
        answer = answer_map.get(question.id)

        performance_data.append({
            "question": question.prompt,
            "question_type": question.type,
            "learner_answer": (
                answer.code
                or answer.answer_text
                or answer.selected_option_id
                if answer
                else ""
            ),
            "earned_points": question_result.earned_points,
            "max_points": question_result.max_points,
            "feedback": question_result.feedback,
            "explanation": question.explanation,
        })

    prompt = f"""
You are an educational assessment feedback specialist.

Analyze the learner's assessment performance.

Subject:
{assessment.subject}

Assessment purpose:
{assessment.purpose}

Performance data:
{performance_data}

Final score:
{result.score_percent}%

Instructions:
1. Write a concise overall summary.
2. Identify demonstrated strengths based on the answers.
3. Identify weaknesses based on incorrect or incomplete answers.
4. Provide specific and actionable learning recommendations.
5. Do not claim the learner has mastered topics without sufficient evidence.
6. Do not invent information that is not supported by the assessment.
7. Keep feedback constructive and educational.
8. Return the result using the required structured format.
"""

    llm = get_llm(
        GENERATE_LLM,
        reasoning_effort="none",
    ).with_structured_output(AssessmentFeedback)

    return await llm.ainvoke(prompt)
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
        raise ValueError("Assessment attempt was not found.")

    if attempt.status != "in_progress":
        raise ValueError("This assessment attempt is not in progress.")

    assessment = await backend.get_assessment(
        attempt.assessment_id
    )

    if assessment is None:
        raise ValueError("Assessment definition was not found.")

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
        raise ValueError(
            f"Unknown answer question IDs: {unknown_answer_ids}"
        )

    external_results = list(external_results or [])

    external_result_map = {}

    for result in external_results:
        if result.question_id in external_result_map:
            raise ValueError(
                f"Duplicate external result for question "
                f"{result.question_id}."
            )

        if result.question_id not in question_map:
            raise ValueError(
                f"Unknown external result question ID: "
                f"{result.question_id}"
            )

        if result.question_id not in answer_map:
            raise ValueError(
                f"External evaluation was provided for unanswered "
                f"question {result.question_id}."
            )

        external_result_map[result.question_id] = result

    for question in assessment.questions:
        answer = answer_map.get(question.id)

        if answer is None:
            continue

        requires_external_evaluation = (
            question.type in {"essay", "practical", "coding"}
            or (
                question.type == "short_answer"
                and not question.expected_answer
            )
        )

        if not requires_external_evaluation:
            if question.id in external_result_map:
                raise ValueError(
                    f"External evaluation is not allowed for "
                    f"question {question.id}."
                )
            continue

        if question.id not in external_result_map:
            evaluation_result = await evaluate_open_question(
                question=question,
                answer=answer,
            )

            external_result_map[question.id] = evaluation_result

    final_external_results = list(
        external_result_map.values()
    )

    result = grade_assessment(
    assessment=assessment,
    answers=attempt.answers,
    external_results=final_external_results,)

    if not summary and not strengths and not weaknesses and not recommendations:
        feedback = await generate_assessment_feedback(
            assessment=assessment,
            answers=attempt.answers,
            result=result,
        )

        result.summary = feedback.summary
        result.strengths = feedback.strengths
        result.weaknesses = feedback.weaknesses
        result.recommendations = feedback.recommendations
    else:
        result.summary = summary
        result.strengths = strengths or []
        result.weaknesses = weaknesses or []
        result.recommendations = recommendations or []

    attempt.result = result
    attempt.status = "completed"
    attempt.submitted_at = datetime.now(UTC)

    await backend.save_assessment_attempt(attempt)

    return attempt