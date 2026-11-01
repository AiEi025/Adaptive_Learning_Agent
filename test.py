
import asyncio

from graph.assessment_service import generate_assessment


async def main():
    assessment = await generate_assessment(
        purpose="placement",
        subject="Python",
        topic="متغیرها و انواع داده",
        level="مبتدی",
        question_count=5,
    )

    print("Title:", assessment.title)
    print("Subject:", assessment.subject)
    print("Question count:", len(assessment.questions))
    print("Total points:", assessment.total_points)

    for index, question in enumerate(assessment.questions, start=1):
        print(f"\nQuestion {index}:")
        print("Type:", question.type)
        print("Prompt:", question.prompt)

        for option in question.options:
            print("-", option.id, option.text)


asyncio.run(main())
