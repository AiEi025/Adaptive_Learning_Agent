import asyncio
import logging
import os
import selectors
import sys
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError

from dotenv import load_dotenv

from graph import learner
from graph.assessment_repository import AssessmentRepository

load_dotenv()
logger = logging.getLogger("adapta.runner")

TITLE_LLM = "gpt-6.1-sol"


def _text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
        return "".join(parts).strip()
    return str(content)


class AsyncRunner:
    """
    پل بین Streamlit (sync) و کدهای async (psycopg، LangGraph، ...).

    یک event loop در یک thread پس‌زمینه تا پایان عمر سرور زنده می‌ماند،
    پس pool دیتابیس و اتصال‌های آن بین rerunها از بین نمی‌روند.
    فقط یک بار (با st.cache_resource) ساخته شود.

    علاوه بر پل، graph (checkpointer + store) هم این‌جا ساخته و نگه‌داری می‌شود.
    """

    def __init__(self):
        # psycopg در حالت async روی ویندوز با ProactorEventLoop (پیش‌فرض ویندوز)
        # کار نمی‌کند و باید از SelectorEventLoop استفاده شود.
        self.loop = (
            asyncio.SelectorEventLoop(selectors.SelectSelector())
            if sys.platform == "win32"
            else asyncio.new_event_loop()
        )
        self._thread = threading.Thread(
            target=self._run_loop, name="async-runner", daemon=True
        )
        self._thread.start()

        # --- graph (به‌صورت lazy در اولین استفاده ساخته می‌شود) ---
        self.graph = None
        self.checkpointer = None
        self.store = None
        self._graph_pool = None
        self._graph_lock = None
        self._title_llm = None
        self.assessment_repository = None

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout: float | None = None): #pre = 180
        """کوروتین را روی loop پس‌زمینه اجرا می‌کند و تا آماده شدن نتیجه منتظر می‌ماند."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout)
        except FutureTimeoutError:
            future.cancel()
            raise TimeoutError(f"اجرای عملیات بیش از {timeout} ثانیه طول کشید") from None

    def close(self):
        """توقف loop (معمولاً لازم نیست؛ thread از نوع daemon است)."""
        if self._graph_pool is not None:
            try:
                self.run(self._graph_pool.close(), timeout=10)
            except Exception:
                logger.exception("closing graph pool failed")
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)

    # ============================================================
    # Graph: checkpointer + store
    # ============================================================

    async def init_graph(self):
        """
        graph را یک بار می‌سازد (روی loop پس‌زمینه). امن برای فراخوانی چندباره.
        این pool جدا از pool مربوط به Crud است؛ checkpointer/store طبق مستندات
        LangGraph به autocommit=True و row_factory=dict_row نیاز دارند.
        """
        if self._graph_lock is None:
            self._graph_lock = asyncio.Lock()

        async with self._graph_lock:
            if self.graph is not None:
                return self.graph

            # import سنگین‌ها فقط وقت نیاز
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres.aio import AsyncPostgresStore
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            from graph.graph import build_graph

            pool = AsyncConnectionPool(
                conninfo=os.environ["DATABASE_URL"],
                min_size=1,
                max_size=5,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row},
            )
            await pool.open()
            await pool.wait()

            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            store = AsyncPostgresStore(pool)
            await store.setup()
            assessment_repository = AssessmentRepository(pool)
            await assessment_repository.initialize()

            async with pool.connection() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS learning_events (
                        id BIGSERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        thread_id TEXT,
                        subject TEXT NOT NULL DEFAULT '',
                        topic TEXT,
                        kind TEXT NOT NULL,
                        correct BOOLEAN,
                        difficulty TEXT,
                        mastery_after REAL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_learning_events_user_time
                    ON learning_events (user_id, created_at DESC);
                """)

            self._graph_pool = pool
            self.checkpointer = checkpointer
            self.store = store
            self.assessment_repository = assessment_repository
            learner.set_event_sink(self.log_learning_events)
            self.graph = build_graph(checkpointer, store)
            return self.graph

    async def log_learning_events(self, user_id: str, thread_id: str, events: list):
        """رویدادهای یادگیری را برای داشبورد ثبت می‌کند (از router_node صدا زده می‌شود)."""
        rows = [
            (user_id, thread_id, e["subject"], e["topic"], e["kind"],
             e["correct"], e["difficulty"], e["mastery_after"])
            for e in events
        ]
        async with self._graph_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany("""
                    INSERT INTO learning_events
                        (user_id, thread_id, subject, topic, kind, correct, difficulty, mastery_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, rows)

    async def run_graph(
        self, user_id: str, thread_id: str, user_input: str, has_files: bool = False
    ) -> str:
        """یک نوبت گفتگو را اجرا می‌کند و متن جواب نهایی را برمی‌گرداند."""
        from counting.counting import RetryContext
        from langchain_core.messages import AIMessage, HumanMessage

        graph = await self.init_graph()
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "question": user_input,
                "thread_id": thread_id,
                "user_id": user_id,          # فقط از نشست واردشده
                "has_files": has_files,
                "retry": RetryContext(),     # تازه برای هر پیام
            },
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 25,
            },
        )
        for message in reversed(result["messages"]):
            if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
                text = _text(message)
                if text:
                    return text
        return ""

    async def get_chat_messages(self, thread_id: str) -> list:
        """پیام‌های ذخیره‌شده‌ی thread به شکل [{'role','content'}] (بعد از refresh هم برمی‌گردد)."""
        from langchain_core.messages import AIMessage, HumanMessage

        graph = await self.init_graph()
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        values = getattr(snapshot, "values", None) or {}
        raw = values.get("messages", []) if isinstance(values, dict) else getattr(values, "messages", [])

        messages = []
        for m in raw:
            text = _text(m)
            if not text:
                continue
            if isinstance(m, HumanMessage):
                messages.append({"role": "user", "content": text})
            elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                messages.append({"role": "assistant", "content": text})
        return messages

    async def delete_thread(self, thread_id: str):
        """حذف checkpointهای یک گفتگو."""
        await self.init_graph()
        if hasattr(self.checkpointer, "adelete_thread"):
            await self.checkpointer.adelete_thread(thread_id)

    async def generate_title(self, user_input: str) -> str:
        """عنوان کوتاه گفتگو از روی اولین پیام."""
        fallback = user_input.strip().replace("\n", " ")[:40] or "گفتگوی جدید"
        try:
            if self._title_llm is None:
                from model.model import Llm_model

                self._title_llm = Llm_model(
                    model_name=TITLE_LLM, reasoning_effort="none"
                ).chose_model()
            prompt = (
                "Write a short, precise title (max 6 words) for a conversation that starts "
                "with the message below. Use the same language as the message. "
                "Output only the title: no quotes, no punctuation at the end, no explanation.\n\n"
                f"Message:\n{user_input[:500]}"
            )
            response = await self._title_llm.ainvoke(prompt)
            title = _text(response).strip("\"'«» ").replace("\n", " ")[:80]
            return title or fallback
        except Exception:
            logger.exception("title generation failed")
            return fallback

    # ============================================================
    # حافظه‌ی یادگیرنده (برای صفحه‌ی پروفایل / داشبورد)
    # ============================================================

    async def _load_profile_item(self, user_id: str):
        await self.init_graph()
        return await self.store.aget(learner.namespace(user_id), learner.PROFILE_KEY)

    async def get_learner_memory(self, user_id: str) -> list:
        """لیست موضوع‌ها با تسلط، نقشه‌ی راه و پیشنهاد مرور (نمای داشبورد)."""
        item = await self._load_profile_item(user_id)
        if item is None:
            return []
        subjects = learner.dashboard_view(item.value, learner.today())
        for s in subjects:
            s["updated_at"] = item.updated_at
        return subjects

    async def get_learner_about(self, user_id: str) -> dict:
        """بخش «درباره‌ی تو»: نام، شغل، علایق، اهداف، یادداشت‌ها، آخرین جلسه."""
        item = await self._load_profile_item(user_id)
        return learner.about_view(item.value if item is not None else None)

    async def reset_learner_memory(self, user_id: str, subject: str):
        """حذف یک موضوع از حافظه و رویدادهای مربوط به آن."""
        item = await self._load_profile_item(user_id)
        if item is None:
            return
        profile = learner.migrate(item.value)
        profile["subjects"].pop(subject, None)
        if (profile.get("last_session") or {}).get("subject") == subject:
            profile["last_session"] = {}
        await self.store.aput(learner.namespace(user_id), learner.PROFILE_KEY, profile)
        async with self._graph_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM learning_events WHERE user_id = %s AND subject = %s",
                (user_id, subject),
            )
        # ============================================================
    # Assessment: آزمون‌ها و تلاش‌های کاربران
    # ============================================================

    async def save_assessment(self, assessment):
        """ذخیره تعریف یک آزمون."""
        await self.init_graph()
        await self.assessment_repository.create_assessment(assessment)

    async def get_assessment(self, assessment_id: str):
        """دریافت تعریف آزمون."""
        await self.init_graph()
        return await self.assessment_repository.get_assessment(
            assessment_id
        )

    async def create_assessment_attempt(self, attempt):
        """ثبت شروع شرکت کاربر در آزمون."""
        await self.init_graph()
        await self.assessment_repository.create_attempt(attempt)

    async def get_assessment_attempt(
        self,
        attempt_id: str,
        user_id: str,
    ):
        """دریافت تلاش فقط در صورتی که متعلق به کاربر باشد."""
        await self.init_graph()
        return await self.assessment_repository.get_attempt(
            attempt_id,
            user_id,
        )

    async def save_assessment_attempt(self, attempt):
        """ذخیره پاسخ‌ها یا نتیجه نهایی آزمون."""
        await self.init_graph()
        return await self.assessment_repository.save_attempt(attempt)

    async def get_assessment_history(
        self,
        user_id: str,
        assessment_id: str | None = None,
        limit: int = 50,
    ):
        """دریافت تاریخچه آزمون‌های کاربر."""
        await self.init_graph()
        return await self.assessment_repository.list_attempts(
            user_id=user_id,
            assessment_id=assessment_id,
            limit=limit,
        )