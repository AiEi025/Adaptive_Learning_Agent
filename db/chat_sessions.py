import os

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

load_dotenv()

DEFAULT_TITLE = "گفتگوی جدید"
MAX_TITLE = 80


def _clean_title(title: str) -> str:
    title = " ".join((title or "").split()).strip() or DEFAULT_TITLE
    return title[: MAX_TITLE - 3] + "..." if len(title) > MAX_TITLE else title


def _conninfo() -> str:
    """مثل Crud و runner از DATABASE_URL استفاده می‌کند؛ اگر نبود از POSTGRES_*."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return make_conninfo(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


class ChatSessionsRepository:
    """فهرست گفتگوهای هر کاربر (عنوان، زمان‌ها، حذف نرم).

    به‌جای یک اتصال تکی از pool استفاده می‌کند: اگر اتصال قطع شود (idle timeout،
    ری‌استارت دیتابیس) pool خودش اتصال تازه می‌سازد.
    """

    def __init__(self):
        self.pool = AsyncConnectionPool(
            conninfo=_conninfo(),
            min_size=1,
            max_size=3,
            open=False,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "prepare_threshold": 0,
            },
        )

    async def open(self):
        await self.pool.open()
        await self.pool.wait()
        await self.create_table()

    async def close(self):
        await self.pool.close()

    async def create_table(self):
        async with self.pool.connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    thread_id UUID PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT 'گفتگوی جدید',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    deleted_at TIMESTAMPTZ NULL
                );
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_activity
                ON chat_sessions (user_id, updated_at DESC)
                WHERE deleted_at IS NULL;
            """)

    async def create_chat(self, user_id: str, thread_id: str, title: str = DEFAULT_TITLE):
        async with self.pool.connection() as conn:
            cur = await conn.execute("""
                INSERT INTO chat_sessions (thread_id, user_id, title)
                VALUES (%s, %s, %s)
                ON CONFLICT (thread_id)
                DO UPDATE SET
                    title = CASE
                        WHEN chat_sessions.title = 'گفتگوی جدید'
                        THEN EXCLUDED.title
                        ELSE chat_sessions.title
                    END,
                    updated_at = NOW()
                WHERE chat_sessions.user_id = EXCLUDED.user_id
                  AND chat_sessions.deleted_at IS NULL
                RETURNING thread_id, user_id, title, created_at, updated_at;
            """, (thread_id, str(user_id), _clean_title(title)))
            return await cur.fetchone()

    async def list_chats(self, user_id: str) -> list:
        async with self.pool.connection() as conn:
            cur = await conn.execute("""
                SELECT thread_id, title, created_at, updated_at
                FROM chat_sessions
                WHERE user_id = %s AND deleted_at IS NULL
                ORDER BY updated_at DESC;
            """, (str(user_id),))
            return await cur.fetchall()

    async def rename_chat(self, user_id: str, thread_id: str, title: str):
        async with self.pool.connection() as conn:
            cur = await conn.execute("""
                UPDATE chat_sessions
                SET title = %s, updated_at = NOW()
                WHERE thread_id = %s AND user_id = %s AND deleted_at IS NULL
                RETURNING thread_id, title, updated_at;
            """, (_clean_title(title), thread_id, str(user_id)))
            return await cur.fetchone()

    async def update_chat_activity(self, user_id: str, thread_id: str):
        async with self.pool.connection() as conn:
            await conn.execute("""
                UPDATE chat_sessions
                SET updated_at = NOW()
                WHERE thread_id = %s AND user_id = %s AND deleted_at IS NULL;
            """, (thread_id, str(user_id)))

    async def delete_chat(self, user_id: str, thread_id: str):
        """حذف نرم؛ اگر گفتگو واقعاً مال همین کاربر بود ردیف، وگرنه None برمی‌گرداند."""
        async with self.pool.connection() as conn:
            cur = await conn.execute("""
                UPDATE chat_sessions
                SET deleted_at = NOW()
                WHERE thread_id = %s AND user_id = %s AND deleted_at IS NULL
                RETURNING thread_id;
            """, (thread_id, str(user_id)))
            return await cur.fetchone()