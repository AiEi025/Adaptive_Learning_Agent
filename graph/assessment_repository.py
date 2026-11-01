
from typing import Any

from psycopg.types.json import Jsonb

from graph.assessment import (
    AssessmentDefinition,
    AssessmentAttempt,
)


class AssessmentRepository:
    """
    مدیریت ذخیره‌سازی تعریف آزمون‌ها و تلاش‌های کاربران
    در PostgreSQL.

    pool باید همان AsyncConnectionPool موجود در AsyncRunner باشد.
    """

    def __init__(self, pool):
        self.pool = pool

    # --------------------------------------------------
    # ایجاد جدول‌ها
    # --------------------------------------------------

    async def initialize(self) -> None:
        async with self.pool.connection() as conn:

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY,
                    purpose TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    definition JSONB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_assessments_subject
                ON assessments (subject);
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS assessment_attempts (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL
                        REFERENCES assessments(id)
                        ON DELETE CASCADE,

                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL DEFAULT '',

                    status TEXT NOT NULL DEFAULT 'in_progress',

                    answers JSONB NOT NULL DEFAULT '[]'::jsonb,
                    result JSONB,

                    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    submitted_at TIMESTAMPTZ
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_assessment_attempts_user_time
                ON assessment_attempts (user_id, started_at DESC);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_assessment_attempts_assessment
                ON assessment_attempts (assessment_id);
            """)

    # --------------------------------------------------
    # تبدیل JSON دریافتی از PostgreSQL
    # --------------------------------------------------

    @staticmethod
    def _json_value(value: Any) -> Any:
        """
        psycopg معمولاً JSONB را به dict/list تبدیل می‌کند.
        این تابع برای حالت‌های مختلف داده، مقدار مناسب را برمی‌گرداند.
        """
        return value

    # --------------------------------------------------
    # ذخیره تعریف آزمون
    # --------------------------------------------------

    async def create_assessment(
        self,
        assessment: AssessmentDefinition,
    ) -> None:

        data = assessment.model_dump(mode="json")

        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO assessments (
                    id,
                    purpose,
                    subject,
                    topic,
                    definition,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING;
                """,
                (
                    assessment.id,
                    assessment.purpose,
                    assessment.subject,
                    assessment.topic,
                    Jsonb(data),
                    assessment.status,
                    assessment.created_at,
                ),
            )

    # --------------------------------------------------
    # دریافت تعریف آزمون
    # --------------------------------------------------

    async def get_assessment(
        self,
        assessment_id: str,
    ) -> AssessmentDefinition | None:

        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT definition
                FROM assessments
                WHERE id = %s;
                """,
                (assessment_id,),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        data = self._json_value(row["definition"])

        return AssessmentDefinition.model_validate(data)

    # --------------------------------------------------
    # ایجاد تلاش جدید کاربر
    # --------------------------------------------------

    async def create_attempt(
        self,
        attempt: AssessmentAttempt,
    ) -> None:

        data = attempt.model_dump(mode="json")

        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO assessment_attempts (
                    id,
                    assessment_id,
                    user_id,
                    thread_id,
                    status,
                    answers,
                    result,
                    started_at,
                    submitted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    attempt.id,
                    attempt.assessment_id,
                    attempt.user_id,
                    attempt.thread_id,
                    attempt.status,
                    Jsonb(data["answers"]),
                    Jsonb(data["result"]) if data["result"] is not None else None,
                    attempt.started_at,
                    attempt.submitted_at,
                ),
            )

    # --------------------------------------------------
    # دریافت یک تلاش متعلق به کاربر
    # --------------------------------------------------

    async def get_attempt(
        self,
        attempt_id: str,
        user_id: str,
    ) -> AssessmentAttempt | None:

        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    id,
                    assessment_id,
                    user_id,
                    thread_id,
                    status,
                    answers,
                    result,
                    started_at,
                    submitted_at
                FROM assessment_attempts
                WHERE id = %s AND user_id = %s;
                """,
                (attempt_id, user_id),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        data = {
            "id": row["id"],
            "assessment_id": row["assessment_id"],
            "user_id": row["user_id"],
            "thread_id": row["thread_id"],
            "status": row["status"],
            "answers": self._json_value(row["answers"]),
            "result": self._json_value(row["result"]),
            "started_at": row["started_at"],
            "submitted_at": row["submitted_at"],
        }

        return AssessmentAttempt.model_validate(data)

    # --------------------------------------------------
    # ذخیره پاسخ‌ها و نتیجه تلاش
    # --------------------------------------------------

    async def save_attempt(
        self,
        attempt: AssessmentAttempt,
    ) -> bool:
        """
        تلاش موجود را فقط در صورتی به‌روزرسانی می‌کند
        که متعلق به همان user_id باشد.

        خروجی:
            True  : ذخیره موفق
            False : تلاش پیدا نشد یا متعلق به کاربر نبود
        """

        data = attempt.model_dump(mode="json")

        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE assessment_attempts
                SET
                    status = %s,
                    answers = %s,
                    result = %s,
                    submitted_at = %s
                WHERE id = %s AND user_id = %s;
                """,
                (
                    attempt.status,
                    Jsonb(data["answers"]),
                    Jsonb(data["result"]) if data["result"] is not None else None,
                    attempt.submitted_at,
                    attempt.id,
                    attempt.user_id,
                ),
            )

        return cursor.rowcount == 1

    # --------------------------------------------------
    # تاریخچه تلاش‌های کاربر
    # --------------------------------------------------

    async def list_attempts(
        self,
        user_id: str,
        assessment_id: str | None = None,
        limit: int = 50,
    ) -> list[AssessmentAttempt]:

        if limit < 1:
            raise ValueError("limit باید حداقل ۱ باشد.")

        async with self.pool.connection() as conn:

            if assessment_id is None:
                cursor = await conn.execute(
                    """
                    SELECT
                        id,
                        assessment_id,
                        user_id,
                        thread_id,
                        status,
                        answers,
                        result,
                        started_at,
                        submitted_at
                    FROM assessment_attempts
                    WHERE user_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s;
                    """,
                    (user_id, limit),
                )

            else:
                cursor = await conn.execute(
                    """
                    SELECT
                        id,
                        assessment_id,
                        user_id,
                        thread_id,
                        status,
                        answers,
                        result,
                        started_at,
                        submitted_at
                    FROM assessment_attempts
                    WHERE user_id = %s AND assessment_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s;
                    """,
                    (user_id, assessment_id, limit),
                )

            rows = await cursor.fetchall()

        attempts = []

        for row in rows:
            data = {
            "id": row["id"],
            "assessment_id": row["assessment_id"],
            "user_id": row["user_id"],
            "thread_id": row["thread_id"],
            "status": row["status"],
            "answers": self._json_value(row["answers"]),
            "result": self._json_value(row["result"]),
            "started_at": row["started_at"],
            "submitted_at": row["submitted_at"],
            }

            attempts.append(
                AssessmentAttempt.model_validate(data)
            )

        return attempts
