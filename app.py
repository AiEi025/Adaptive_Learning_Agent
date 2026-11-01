"""
Adapta - مربی تطبیقی (هر موضوعی)
================================
رابط کاربری Streamlit.

ساختار فایل:
  1) تنظیمات صفحه
  2) تم و CSS
  3) Runner، Repositoryها و Backend
  4) State و توابع کمکی
  5) صفحه ورود / ثبت‌نام
  6) Sidebar
  7) صفحه چت، پروفایل، داشبورد
  8) مسیریابی
"""

import asyncio
import copy
import html as html_lib
import logging
import re
import sys
import uuid

import streamlit as st

from async_runner import AsyncRunner
from db.chat_sessions import ChatSessionsRepository
from db.crud import Crud
from graph.assessment import AssessmentAnswer, AssessmentAttempt
from graph.assessment_service import (
    create_and_save_assessment,
    submit_assessment_attempt,
)

# from file_manager.file_manager import File_Manager

# ============================================================
# 1) PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Adapta",
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_NAME = "Adapta"
DEFAULT_CHAT_TITLE = "گفتگوی جدید"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

# ============================================================
# 2) THEME + CSS
# ============================================================
# رنگ ویجت‌های بومی از .streamlit/config.toml می‌آید.
# قاعده‌ی مهم: به sidebar، header و دکمه‌ی باز/بسته‌ی آن دست نمی‌زنیم،
# و فونت را روی «همه‌ی» المان‌ها اعمال نمی‌کنیم (آیکون‌ها فونت خودشان را دارند).

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700&display=swap');

:root {
    --n-100:#ECEEF3; --n-200:#D9DCE4; --n-300:#BBBFCB; --n-400:#8B90A0;
    --n-500:#6B7080; --n-600:#555A68; --n-700:#444753; --n-800:#363845;
    --n-900:#292B35; --n-950:#1A1B22;
    --g-100:#F2EFD2; --g-200:#E6E0A8; --g-300:#D8CF7A; --g-400:#C8BE60;
    --g-500:#BCB957; --g-950:#2E2C15;
}

/* ---------- فونت (فقط روی متن‌ها) ---------- */
.stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp input, .stApp textarea, .stApp button {
    font-family: 'Vazirmatn', system-ui, sans-serif;
}
/* ---------- راست‌به‌چپ و مدیریت هوشمند متن‌های ترکیبی ---------- */
[data-testid="stMain"], [data-testid="stBottom"], [data-testid="stSidebarUserContent"] {
    direction: rtl;
}

/* این بخش جدید مشکل ترکیب فارسی و انگلیسی را حل می‌کند */
.stMarkdown p, 
.stMarkdown li, 
.stMarkdown h1, 
.stMarkdown h2, 
.stMarkdown h3, 
.stMarkdown h4, 
[data-testid="stChatMessage"] p {
    unicode-bidi: plaintext; /* تشخیص خودکار جهت متن بر اساس اولین حرف */
    text-align: start;       /* تراز کردن متن به سمت راست یا چپ بر اساس جهت تشخیص داده شده */
}

/* کدها همیشه باید انگلیسی، چپ‌چین و از چپ به راست باشند */
pre, code, pre *, code * { 
    direction: ltr !important; 
    text-align: left !important; 
    unicode-bidi: normal !important;
}

#MainMenu, footer { visibility: hidden; }
.block-container { max-width: 860px; padding-top: 2rem; padding-bottom: 8rem; }

/* ---------- آیکون‌ها ---------- */
[data-testid="stIconMaterial"] { color: var(--g-400); }
[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"],
button[kind="primary"] [data-testid="stIconMaterial"] { color: var(--n-950); }

/* ---------- دکمه‌ها ---------- */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"],
button[kind="primary"] {
    background: var(--g-400); color: var(--n-950); border: 1px solid var(--g-400);
    font-weight: 700; border-radius: 12px;
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover,
button[kind="primary"]:hover { background: var(--g-300); border-color: var(--g-300); color: var(--n-950); }
[data-testid="stBaseButton-secondary"], button[kind="secondary"] {
    background: transparent; color: var(--n-200);
    border: 1px solid var(--n-700); border-radius: 12px;
}
[data-testid="stBaseButton-secondary"]:hover, button[kind="secondary"]:hover {
    border-color: var(--g-400); color: var(--g-200); background: var(--n-800);
}

/* ---------- sidebar (فقط رنگ) ---------- */
section[data-testid="stSidebar"] { background: var(--n-950); }

/* ---------- برند ---------- */
.brand { display:flex; align-items:center; gap:.6rem; margin:0; }
.brand-dot {
    width:14px; height:14px; border-radius:4px; background: var(--g-400);
    box-shadow: 0 0 0 4px var(--g-950);
}
.brand-name { font-size:1.5rem; font-weight:700; color: var(--n-100); }
.brand-tag { margin:.35rem 0 0 0; font-size:.85rem; color: var(--n-400); }

/* ---------- ورودی‌ها ---------- */
[data-testid="stTextInput"] input {
    background: var(--n-950); border: 1px solid var(--n-700);
    color: var(--n-100); border-radius: 12px;
}
[data-testid="stTextInput"] input:focus { border-color: var(--g-400); box-shadow: 0 0 0 1px var(--g-400); }

/* ---------- پیام‌های چت ---------- */
[data-testid="stChatMessage"] { background: transparent; border-radius: 14px; padding: .9rem 1rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--n-800); }

/* ---------- چت‌باکس شناور ---------- */
[data-testid="stBottom"] > div { background: transparent !important; }
[data-testid="stChatInput"] {
    max-width: 820px; margin: 0 auto 1.1rem auto;
    background: var(--n-800); border: 1px solid var(--n-600);
    border-radius: 20px; box-shadow: 0 12px 32px rgba(0,0,0,.40);
}
[data-testid="stChatInput"]:focus-within { border-color: var(--g-400); }
[data-testid="stChatInput"] textarea { color: var(--n-100); }
[data-testid="stChatInputSubmitButton"] { color: var(--g-400); }

/* ---------- پروفایل ---------- */
.avatar {
    width:64px; height:64px; border-radius:50%; background: var(--g-950);
    border:2px solid var(--g-400); color: var(--g-300);
    display:flex; align-items:center; justify-content:center;
    font-size:1.6rem; font-weight:700;
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
/* ---------- دکمه پروفایل کاربر در سایدبار ---------- */
/* هدف قرار دادن دکمه با استفاده از کلید آن */
div[class*="st-key-nav_profile"] button {
    border-radius: 50px !important; /* گرد کردن کامل دکمه */
    padding: 8px 16px !important; /* فاصله داخلی مناسب */
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important; /* چیدمان از سمت راست (به خاطر RTL) */
    gap: 10px !important; /* فاصله بین آیکون و متن */
    background-color: var(--n-800) !important; /* رنگ پس‌زمینه ملایم */
    border: 1px solid var(--n-600) !important; /* حاشیه ملایم */
    color: var(--n-100) !important;
}

/* استایل هاور (وقتی موس روی دکمه می‌رود) */
div[class*="st-key-nav_profile"] button:hover {
    border-color: var(--g-400) !important;
    color: var(--g-200) !important;
}

/* تنظیم فاصله متن داخل دکمه */
div[class*="st-key-nav_profile"] button p {
    margin: 0 !important;
    font-weight: 500 !important;
    font-size: 0.95rem !important;
}

/* اگر دکمه در حالت فعال (Primary) بود */
div[class*="st-key-nav_profile"] button[kind="primary"] {
    background-color: var(--g-400) !important;
    color: var(--n-950) !important;
    border-color: var(--g-400) !important;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def html(s: str) -> str:
    """HTML چندخطی را فشرده می‌کند تا Markdown آن را کد تلقی نکند."""
    return "".join(line.strip() for line in s.strip().splitlines())


# ============================================================
# 3) RUNNER + REPOSITORIES + BACKEND
# ============================================================
# - AsyncRunner (async_runner.py): پل async + graph (checkpointer / store) + حافظه‌ی یادگیرنده
# - Crud (db/crud.py): کاربران (ورود، ثبت‌نام، پروفایل)
# - ChatSessionsRepository (db/chat_sessions.py): فهرست گفتگوهای هر کاربر
# - AdaptaBackend: لایه‌ی نازکی که رابط کاربری با آن صحبت می‌کند

logger = logging.getLogger("adapta")


class AdaptaBackend:
    def __init__(self, runner: AsyncRunner, chat_sessions: ChatSessionsRepository):
        self.runner = runner
        self.chat_sessions = chat_sessions

    # ---------------- گفتگوها ----------------
    async def list_chats(self, user_id: str) -> list:
        return await self.chat_sessions.list_chats(user_id)

    async def create_chat(self, user_id: str, thread_id: str, title: str):
        return await self.chat_sessions.create_chat(user_id, thread_id, title)

    async def rename_chat(self, user_id: str, thread_id: str, title: str):
        return await self.chat_sessions.rename_chat(user_id, thread_id, title)

    async def update_chat_activity(self, user_id: str, thread_id: str):
        await self.chat_sessions.update_chat_activity(user_id, thread_id)

    async def delete_chat(self, user_id: str, thread_id: str):
        # حذف نرم از chat_sessions؛ فقط اگر گفتگو مال همین کاربر بود checkpointها هم پاک می‌شوند
        deleted = await self.chat_sessions.delete_chat(user_id, thread_id)
        if deleted:
            await self.runner.delete_thread(thread_id)

    # ---------------- پیام‌ها و Agent ----------------
    async def get_chat_messages(self, thread_id: str) -> list:
        return await self.runner.get_chat_messages(thread_id)

    async def generate_title(self, user_input: str) -> str:
        return await self.runner.generate_title(user_input)

    async def run_agent(self, user: dict, thread_id: str, user_input: str,
                        has_files: bool = False) -> str:
        return await self.runner.run_graph(user["id"], thread_id, user_input, has_files=has_files)

    # ---------------- حافظه‌ی یادگیرنده ----------------
    async def get_learner_memory(self, user_id: str) -> list:
        return await self.runner.get_learner_memory(user_id)

    async def reset_learner_memory(self, user_id: str, subject: str):
        await self.runner.reset_learner_memory(user_id, subject)
    # ---------------- آزمون‌ها ----------------

    async def save_assessment(self, assessment):
        await self.runner.save_assessment(assessment)

    async def get_assessment(self, assessment_id: str):
        return await self.runner.get_assessment(assessment_id)

    async def create_assessment_attempt(self, attempt):
        await self.runner.create_assessment_attempt(attempt)

    async def get_assessment_attempt(self, attempt_id: str, user_id: str):
        return await self.runner.get_assessment_attempt(attempt_id, user_id)

    async def save_assessment_attempt(self, attempt):
        return await self.runner.save_assessment_attempt(attempt)

    async def get_assessment_history(
        self,
        user_id: str,
        assessment_id: str | None = None,
        limit: int = 50,
    ):
        return await self.runner.get_assessment_history(
            user_id=user_id,
            assessment_id=assessment_id,
            limit=limit,
        )

# @st.cache_resource
# def get_file_manager():
#     return File_Manager()

# file_manager = get_file_manager()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

@st.cache_resource
def get_async_runner() -> AsyncRunner:
    return AsyncRunner()


runner = get_async_runner()


def run(coro):
    return runner.run(coro)


@st.cache_resource
def get_chat_sessions() -> ChatSessionsRepository:
    repo = ChatSessionsRepository()
    runner.run(repo.open())  # pool روی loop پس‌زمینه باز می‌شود
    return repo


@st.cache_resource
def get_crud() -> Crud:
    async def _make():
        c = Crud()
        await c.open()  # pool روی loop پس‌زمینه باز می‌شود
        return c

    return runner.run(_make())


@st.cache_resource
def get_backend() -> AdaptaBackend:
    return AdaptaBackend(runner, get_chat_sessions())


crud = get_crud()
backend = get_backend()


def show_db_error():
    """پیام ساده به کاربر؛ خطای واقعی (traceback) در ترمینال چاپ می‌شود.
    باید داخل بلاک except صدا زده شود."""
    logger.exception("خطای دیتابیس / Crud")
    st.error("مشکلی در انجام عملیات پیش آمد. کمی بعد دوباره امتحان کن.")


def to_app_user(row: dict) -> dict:
    """ستون‌های جدول users را به قالبی که رابط انتظار دارد تبدیل می‌کند."""
    return {
        "id": str(row.get("id", row["user_name"])),
        "username": row["user_name"],
        "created_at": row.get("created_at"),
    }


# ============================================================
# 4) STATE + HELPERS
# ============================================================
# user          : کاربر واردشده (None = وارد نشده)
# chats         : {thread_id: {title, created_at, updated_at}} به ترتیب جدیدترین
# messages      : کش پیام‌ها {thread_id: [...]}
# *_dirty       : فقط وقتی True است از دیتابیس دوباره می‌خوانیم
#                 (در نمونه‌ی قبلی هر rerun دو بار به دیتابیس می‌رفتیم)
# توجه: با refresh مرورگر نشست پاک می‌شود. cookie بعداً اضافه می‌شود.

DEFAULTS = {
    "user": None,
    "chats": {},
    "chats_dirty": True,
    "active_chat_id": None,
    "messages": {},
    "learner": [],
    "learner_dirty": True,
    "view": "chat",
    "pending_prompt": None,
    "uploaded_files": {},
}
for _k, _v in DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = copy.deepcopy(_v)


def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


def refresh_chats(user):
    rows = run(backend.list_chats(user["id"]))
    st.session_state.chats = {
        str(r["thread_id"]): {"title": r["title"], "created_at": r["created_at"],
                              "updated_at": r["updated_at"]}
        for r in rows
    }
    st.session_state.chats_dirty = False


def create_new_chat(user, force: bool = False):
    """یک گفتگوی خالی کافی است؛ اگر همین الان یکی باز است، دومی نمی‌سازیم."""
    chats = st.session_state.chats
    active = st.session_state.active_chat_id
    if (not force and active in chats
            and chats[active]["title"] == DEFAULT_CHAT_TITLE):
        st.session_state.view = "chat"
        return
    chat_id = str(uuid.uuid4())
    run(backend.create_chat(user["id"], chat_id, DEFAULT_CHAT_TITLE))
    st.session_state.messages[chat_id] = []
    st.session_state.active_chat_id = chat_id
    st.session_state.chats_dirty = True
    st.session_state.view = "chat"


def ensure_active_chat(user):
    """چت‌ها را (در صورت نیاز) تازه می‌کند و چت فعالِ معتبر تضمین می‌کند."""
    if st.session_state.chats_dirty:
        refresh_chats(user)
    if not st.session_state.chats:
        create_new_chat(user, force=True)
        refresh_chats(user)
    if st.session_state.active_chat_id not in st.session_state.chats:
        st.session_state.active_chat_id = next(iter(st.session_state.chats))


def get_messages(chat_id: str) -> list:
    cache = st.session_state.messages
    if chat_id not in cache:
        cache[chat_id] = run(backend.get_chat_messages(chat_id))
    return cache[chat_id]


def get_learner(user) -> list:
    if st.session_state.learner_dirty:
        try:
            st.session_state.learner = run(backend.get_learner_memory(user["id"]))
        except Exception:
            # خرابی حافظه نباید کل صفحه را از کار بیندازد
            logger.exception("loading learner memory failed")
            st.session_state.learner = []
        st.session_state.learner_dirty = False
    return st.session_state.learner


# ============================================================
# 5) AUTH PAGE
# ============================================================


def render_assessment_setup(user):
    purpose = st.session_state.pending_assessment_purpose

    if purpose not in {"placement", "learning"}:
        return False

    learner = get_learner(user) or []

    st.markdown("## Start an Assessment")

    subjects = list(dict.fromkeys(
        item["subject"]
        for item in learner
        if item.get("subject")
    ))

    # Placement Assessment
    if purpose == "placement":
        st.write(
            "Choose a subject to assess your current knowledge. "
            "The assessment will start with easier questions "
            "and gradually progress to harder questions."
        )

        subject_options = ["Other subject"] + subjects

        selected_subject = st.selectbox(
            "Subject",
            subject_options,
            key="placement_subject",
        )

        if selected_subject == "Other subject":
            subject = st.text_input(
                "Enter a subject",
                key="placement_custom_subject",
            )
        else:
            subject = selected_subject

        st.caption(
            "No prior level selection is required. "
            "The assessment will cover the subject broadly."
        )

        topics = []
        topic = ""
        level = "Adaptive"

    # Learning Assessment
    else:
        st.write("Assess what you have learned with Adapta.")

        if not subjects:
            st.info(
                "No learning history is available yet. "
                "Start learning a subject before taking this assessment."
            )

            if st.button("Cancel", key="cancel_assessment_setup"):
                st.session_state.pending_assessment_purpose = None
                st.session_state.assessment_setup = None
                st.rerun()

            return True

        assessment_mode = st.radio(
            "How would you like to select assessment topics?",
            [
                "Use my learning history",
                "Choose topics manually",
            ],
            key="learning_assessment_mode",
        )

        subject = st.selectbox(
            "Subject",
            subjects,
            key="learning_assessment_subject",
        )

        subject_data = next(
            item for item in learner
            if item.get("subject") == subject
        )

        mastery = subject_data.get("mastery") or {}
        roadmap = subject_data.get("roadmap") or []

        demonstrated_topics = [
            topic_name
            for topic_name, data in mastery.items()
            if isinstance(data, dict)
            and data.get("attempts", 0) > 0
        ]

        if assessment_mode == "Use my learning history":
            st.caption(
                "Select topics with a recorded history of actual practice."
            )

            if not demonstrated_topics:
                st.info(
                    "No topics with demonstrated practice "
                    "are available for this subject yet."
                )
                topics = []
            else:
                topics = st.multiselect(
                    "Topics",
                    options=demonstrated_topics,
                    default=demonstrated_topics,
                    key="learning_history_topics",
                )

        else:
            st.caption(
                "Choose topics from your learning roadmap "
                "or enter additional topics."
            )

            manual_topic_options = list(dict.fromkeys(
                [
                    item["topic"]
                    for item in roadmap
                    if item.get("topic")
                ] + list(mastery.keys())
            ))

            topics = st.multiselect(
                "Topics",
                options=manual_topic_options,
                key="learning_manual_topics",
            )

            custom_topics = st.text_input(
                "Additional topics (comma-separated)",
                key="learning_custom_topics",
            )

            if custom_topics.strip():
                additional_topics = [
                    item.strip()
                    for item in custom_topics.split(",")
                    if item.strip()
                ]

                existing_topics = {
                    existing.casefold() for existing in topics
                }

                for item in additional_topics:
                    if item.casefold() not in existing_topics:
                        topics.append(item)
                        existing_topics.add(item.casefold())

        topic = ", ".join(topics)
        level = "Learned content"

    # Assessment Preferences
    st.divider()
    st.markdown("### Assessment Preferences")

    approach_labels = {
        "Balanced": "balanced",
        "Conceptual and deep understanding": "conceptual",
        "Practical and problem-oriented": "practical",
        "Challenging and advanced": "challenging",
        "Custom approach": "custom",
    }

    selected_approach_label = st.selectbox(
        "Assessment approach",
        options=list(approach_labels.keys()),
        index=0,
        key="assessment_approach",
    )

    approach = approach_labels[selected_approach_label]

    question_type_labels = {
        "Multiple choice": "multiple_choice",
        "Short answer": "short_answer",
        "Essay": "essay",
        "Practical": "practical",
        "Coding": "coding",
    }

    selected_question_type_labels = st.multiselect(
        "Question types",
        options=list(question_type_labels.keys()),
        default=["Multiple choice"],
        key="assessment_question_types",
    )

    question_types = [
        question_type_labels[label]
        for label in selected_question_type_labels
    ]

    question_count = st.slider(
        "Number of questions",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        key="assessment_question_count",
    )

    custom_instructions = st.text_area(
        "Additional instructions (optional)",
        placeholder=(
            "For example: Focus on analyzing SQL queries, "
            "finding errors, and solving real-world problems."
        ),
        key="assessment_custom_instructions",
    )

    if approach == "custom":
        st.caption(
            "Describe your preferred assessment approach "
            "in the additional instructions field."
        )

    # Start / Cancel
    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "Start Assessment",
            type="primary",
            use_container_width=True,
            key="start_assessment",
        ):
            if not subject.strip():
                st.error("Please enter or select a subject.")
                return True

            if purpose == "learning" and not topics:
                st.error("Please select at least one topic.")
                return True

            if not question_types:
                st.error("Please select at least one question type.")
                return True

            if approach == "custom" and not custom_instructions.strip():
                st.error(
                    "Please describe your preferred assessment approach."
                )
                return True

            st.session_state.assessment_setup = {
                "purpose": purpose,
                "subject": subject.strip(),
                "topics": topics,
                "topic": topic,
                "level": level,
                "approach": approach,
                "question_types": question_types,
                "question_count": question_count,
                "custom_instructions": custom_instructions.strip(),
            }

            st.session_state.pending_assessment_purpose = None
            st.rerun()

    with col2:
        if st.button(
            "Cancel",
            use_container_width=True,
            key="cancel_assessment",
        ):
            st.session_state.pending_assessment_purpose = None
            st.session_state.assessment_setup = None
            st.rerun()

    return True


def render_assessment_start(user, chat_id):
    setup = st.session_state.assessment_setup

    if not setup:
        return

    try:
        assessment_id = st.session_state.get(
            "assessment_start_assessment_id"
        )

        if assessment_id:
            assessment = run(
                backend.get_assessment(assessment_id)
            )
        else:
            with st.spinner("Generating your assessment..."):
                assessment = run(
                    create_and_save_assessment(
                        backend=backend,
                        purpose=setup["purpose"],
                        subject=setup["subject"],
                        topic=setup.get("topic", ""),
                        level=setup.get("level", "Beginner"),
                        question_count=setup.get("question_count", 5),
                        approach=setup.get("approach", "balanced"),
                        question_types=setup.get(
                            "question_types",
                            ["multiple_choice"],
                        ),
                        custom_instructions=setup.get(
                            "custom_instructions",
                            "",
                        ),
                    )
                )

            st.session_state.assessment_start_assessment_id = (
                assessment.id
            )

        if assessment is None:
            raise ValueError("The assessment could not be loaded.")

        attempt_id = st.session_state.get(
            "assessment_start_attempt_id"
        )

        attempt = None

        if attempt_id:
            attempt = run(
                backend.get_assessment_attempt(
                    attempt_id,
                    user["id"],
                )
            )

        if attempt is None:
            attempt = AssessmentAttempt(
                id=str(uuid.uuid4()),
                assessment_id=assessment.id,
                user_id=user["id"],
                thread_id=chat_id,
                status="in_progress",
            )

            st.session_state.assessment_start_attempt_id = (
                attempt.id
            )

            run(
                backend.create_assessment_attempt(attempt)
            )

        st.session_state.active_assessment_id = assessment.id
        st.session_state.active_assessment_attempt_id = attempt.id

        st.session_state.assessment_setup = None
        st.session_state.pop("assessment_start_assessment_id", None)
        st.session_state.pop("assessment_start_attempt_id", None)

        st.rerun()

    except Exception as exc:
        logger.exception("Failed to start assessment.")
        st.error("The assessment could not be started.")

        with st.expander("Error details"):
            st.code(repr(exc))
            
            
def render_brand(tagline: bool = True):
    tag = '<p class="brand-tag">مربی تطبیقی؛ هر چیزی که می‌خواهی یاد بگیری</p>' if tagline else ""
    st.markdown(
        html(f'<div class="brand"><span class="brand-dot"></span>'
             f'<span class="brand-name">{APP_NAME}</span></div>{tag}'),
        unsafe_allow_html=True,
    )


def validate_registration(username: str, password: str, confirm: str) -> list:
    errors = []
    if not USERNAME_RE.match(username.strip()):
        errors.append("نام کاربری باید ۳ تا ۲۰ کاراکتر و فقط شامل حرف انگلیسی، عدد و _ باشد.")
    if len(password) < 8:
        errors.append("رمز عبور باید حداقل ۸ کاراکتر باشد.")
    if password != confirm:
        errors.append("تکرار رمز عبور با رمز عبور یکسان نیست.")
    return errors


def sign_in(user: dict):
    for k in ("chats", "messages", "learner"):
        st.session_state[k] = copy.deepcopy(DEFAULTS[k])
    st.session_state.chats_dirty = True
    st.session_state.learner_dirty = True
    st.session_state.active_chat_id = None
    st.session_state.view = "chat"
    st.session_state.user = user
    st.rerun()


def render_auth():
    # عمداً چیزی داخل st.sidebar نمی‌گذاریم؛ Streamlit خودش sidebar خالی را نشان نمی‌دهد.
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        render_brand()
        st.write("")
        tab_login, tab_register = st.tabs(["ورود", "ثبت‌نام"])

        with tab_login, st.form("login_form"):
                username = st.text_input("نام کاربری", key="login_username")
                password = st.text_input("رمز عبور", type="password", key="login_password")
                submitted = st.form_submit_button("ورود", type="primary", use_container_width=True)
                if submitted:
                    if not username.strip() or not password:
                        st.error("نام کاربری و رمز عبور را وارد کن.")
                    else:
                        with st.spinner("در حال بررسی اطلاعات..."):
                            try:
                                row = run(crud.authenticate(username, password))
                            except Exception:
                                show_db_error()
                            else:
                                if row:
                                    sign_in(to_app_user(row))
                                else:
                                    st.error("نام کاربری یا رمز عبور درست نیست. اگر حساب نداری از تب ثبت‌نام بساز.")
        with tab_register:
            with st.form("register_form"):
                username = st.text_input(
                    "نام کاربری", key="reg_username",
                    help="۳ تا ۲۰ کاراکتر: حرف انگلیسی، عدد و _",
                )
                password = st.text_input("رمز عبور", type="password", key="reg_password",
                                         help="حداقل ۸ کاراکتر")
                confirm = st.text_input("تکرار رمز عبور", type="password", key="reg_confirm")
                submitted = st.form_submit_button("ساخت حساب", type="primary",
                                                  use_container_width=True)
            if submitted:
                errors = validate_registration(username, password, confirm)
                for e in errors:
                    st.error(e)
                if not errors:
                    with st.spinner("در حال ساخت حساب..."):
                        try:
                            row = run(crud.register(username, password))
                        except ValueError:
                            st.error("این نام کاربری قبلاً گرفته شده؛ نام دیگری انتخاب کن.")
                        except Exception:
                            show_db_error()
                        else:
                            sign_in(to_app_user(row))

# ============================================================
# 6) SIDEBAR
# ============================================================


def render_sidebar(user):
    with st.sidebar:
        render_brand(tagline=False)
        st.write("")

        if st.button("گفتگوی جدید", icon=":material/add:", type="primary",
                     use_container_width=True, key="new_chat"):
            create_new_chat(user)
            st.rerun()

        if st.button("داشبورد", icon=":material/monitoring:",
                     use_container_width=True, key="nav_dashboard"):
            st.session_state.view = "dashboard"
            st.rerun()
        
        if st.button(
        "آزمون‌ها",
        icon=":material/quiz:",
        use_container_width=True,
        key="nav_assessment",
        type="primary" if st.session_state.view == "assessment" else "secondary",
        ):
            # st.session_state.view = "assessment"
            st.rerun()

        st.divider()
        st.caption("تاریخچه‌ی گفتگوها")

        in_chat_view = st.session_state.view == "chat"
        for chat_id, chat in st.session_state.chats.items():
            title = chat["title"].strip() or DEFAULT_CHAT_TITLE
            if len(title) > 28:
                title = title[:28] + "…"
            is_active = in_chat_view and chat_id == st.session_state.active_chat_id

            c_open, c_menu = st.columns([5, 1], vertical_alignment="center")
            with c_open:
                if st.button(title, key=f"chat_{chat_id}", use_container_width=True,
                             icon=":material/chat_bubble:",
                             type="primary" if is_active else "secondary"):
                    st.session_state.active_chat_id = chat_id
                    st.session_state.view = "chat"
                    st.rerun()
            with c_menu, st.popover("⋮", use_container_width=True):
                st.caption("این گفتگو برای همیشه حذف می‌شود.")
                if st.button("حذف گفتگو", key=f"del_{chat_id}", type="primary",
                             icon=":material/delete:", use_container_width=True):
                    run(backend.delete_chat(user["id"], chat_id))
                    st.session_state.messages.pop(chat_id, None)
                    st.session_state.chats_dirty = True
                    if chat_id == st.session_state.active_chat_id:
                        st.session_state.active_chat_id = None
                    st.rerun()

        st.divider()
        if st.button(user["username"], icon=":material/person:", use_container_width=True,
                     key="nav_profile",
                     type="primary" if st.session_state.view == "profile" else "secondary"):
            st.session_state.view = "profile"
            st.rerun()


# ============================================================
# 7) VIEWS
# ============================================================
def render_assessment_result(assessment, attempt):
    result = attempt.result

    if result is None:
        st.error("The assessment result is not available.")
        return

    st.markdown(f"## {assessment.title}")
    st.caption(f"Subject: {assessment.subject}")

    st.success("Assessment completed.")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Score",
        f"{result.score_percent:.1f}%",
    )

    col2.metric(
        "Earned Points",
        f"{result.earned_points:g}",
    )

    col3.metric(
        "Total Points",
        f"{result.total_points:g}",
    )

    st.progress(result.score_percent / 100)

    if result.summary:
        st.markdown("### Overall Feedback")
        st.write(result.summary)

    if result.strengths:
        st.markdown("### Strengths")
        for item in result.strengths:
            st.markdown(f"- {item}")

    if result.weaknesses:
        st.markdown("### Areas to Improve")
        for item in result.weaknesses:
            st.markdown(f"- {item}")

    if result.recommendations:
        st.markdown("### Learning Recommendations")
        for item in result.recommendations:
            st.markdown(f"- {item}")

    st.divider()
    st.markdown("### Question Review")

    question_map = {
        question.id: question
        for question in assessment.questions
    }

    answer_map = {
        answer.question_id: answer
        for answer in attempt.answers
    }

    result_map = {
        item.question_id: item
        for item in result.question_results
    }

    for index, question in enumerate(
        assessment.questions,
        start=1,
    ):
        question_result = result_map.get(question.id)
        answer = answer_map.get(question.id)

        with st.expander(
            f"Question {index} — "
            f"{question_result.earned_points:g}/"
            f"{question.points:g} points"
            if question_result
            else f"Question {index}"
        ):
            st.write(question.prompt)

            if question.type == "multiple_choice":
                selected_id = (
                    answer.selected_option_id
                    if answer
                    else None
                )

                selected_option = next(
                    (
                        option
                        for option in question.options
                        if option.id == selected_id
                    ),
                    None,
                )

                correct_option = next(
                    (
                        option
                        for option in question.options
                        if option.id == question.correct_option_id
                    ),
                    None,
                )

                st.markdown("**Your answer:**")
                st.write(
                    selected_option.text
                    if selected_option
                    else "Not answered"
                )

                st.markdown("**Correct answer:**")
                st.write(
                    correct_option.text
                    if correct_option
                    else "Not available"
                )

            elif question.type == "coding":
                st.markdown("**Your code:**")
                st.code(
                    answer.code or ""
                    if answer
                    else "",
                    language="python",
                )

            else:
                st.markdown("**Your answer:**")
                st.write(
                    answer.answer_text or ""
                    if answer
                    else "Not answered"
                )

            if question_result:
                st.markdown("**Points earned:**")
                st.write(
                    f"{question_result.earned_points:g} / "
                    f"{question_result.max_points:g}"
                )

                if question_result.feedback:
                    st.markdown("**Feedback:**")
                    st.write(question_result.feedback)

                if question_result.criterion_scores:
                    st.markdown("**Rubric evaluation:**")

                    criterion_map = {
                        criterion.id: criterion
                        for criterion in question.rubric
                    }

                    for score in question_result.criterion_scores:
                        criterion = criterion_map.get(
                            score.criterion_id
                        )

                        criterion_name = (
                            criterion.description
                            if criterion
                            else score.criterion_id
                        )

                        st.write(
                            f"- {criterion_name}: "
                            f"{score.earned_points:g} / "
                            f"{criterion.max_points:g}"
                            if criterion
                            else f"- {criterion_name}: "
                            f"{score.earned_points:g}"
                        )

            if question.explanation:
                st.markdown("**Explanation:**")
                st.write(question.explanation)

    st.divider()

    if st.button(
        "Back to Chat",
        key=f"assessment_back_{attempt.id}",
        use_container_width=True,
    ):
        st.session_state.active_assessment_id = None
        st.session_state.active_assessment_attempt_id = None
        st.rerun()
        
def render_active_assessment(user):
    assessment_id = st.session_state.get(
        "active_assessment_id"
    )
    attempt_id = st.session_state.get(
        "active_assessment_attempt_id"
    )

    if not assessment_id or not attempt_id:
        return

    try:
        assessment = run(
            backend.get_assessment(assessment_id)
        )

        attempt = run(
            backend.get_assessment_attempt(
                attempt_id,
                user["id"],
            )
        )

        if assessment is None or attempt is None:
            st.error("The assessment could not be loaded.")
            return

        if attempt.status == "completed":
            render_assessment_result(assessment, attempt)
            return

        if attempt.status != "in_progress":
            st.warning("This assessment attempt is no longer active.")
            return

        st.markdown(f"## {assessment.title}")
        st.caption(f"Subject: {assessment.subject}")

        if assessment.topic:
            st.caption(f"Topics: {assessment.topic}")

        if assessment.instructions:
            st.write(assessment.instructions)

        st.divider()

        existing_answers = {
            answer.question_id: answer
            for answer in attempt.answers
        }

        answer_updates = {}

        for index, question in enumerate(
            assessment.questions,
            start=1,
        ):
            st.markdown(f"### Question {index}")
            st.write(question.prompt)
            st.caption(f"Points: {question.points}")

            previous_answer = existing_answers.get(question.id)

            if question.type == "multiple_choice":
                options = question.options

                option_labels = {
                    option.text: option.id
                    for option in options
                }

                option_texts = [
                    option.text
                    for option in options
                ]

                previous_text = None

                if (
                    previous_answer
                    and previous_answer.selected_option_id
                ):
                    previous_option = next(
                        (
                            option
                            for option in options
                            if option.id
                            == previous_answer.selected_option_id
                        ),
                        None,
                    )

                    if previous_option:
                        previous_text = previous_option.text

                selected_text = st.radio(
                    "Select your answer",
                    option_texts,
                    index=(
                        option_texts.index(previous_text)
                        if previous_text in option_texts
                        else None
                    ),
                    key=f"assessment_{attempt_id}_{question.id}",
                )

                answer_updates[question.id] = {
                    "selected_option_id": (
                        option_labels.get(selected_text)
                        if selected_text is not None
                        else None
                    ),
                    "answer_text": None,
                    "code": None,
                }

            elif question.type == "short_answer":
                answer_text = st.text_input(
                    "Your answer",
                    value=(
                        previous_answer.answer_text or ""
                        if previous_answer
                        else ""
                    ),
                    key=f"assessment_{attempt_id}_{question.id}",
                )

                answer_updates[question.id] = {
                    "selected_option_id": None,
                    "answer_text": answer_text,
                    "code": None,
                }

            elif question.type in {"essay", "practical"}:
                answer_text = st.text_area(
                    "Your answer",
                    value=(
                        previous_answer.answer_text or ""
                        if previous_answer
                        else ""
                    ),
                    height=180,
                    key=f"assessment_{attempt_id}_{question.id}",
                )

                answer_updates[question.id] = {
                    "selected_option_id": None,
                    "answer_text": answer_text,
                    "code": None,
                }

            elif question.type == "coding":
                code = st.text_area(
                    "Write your code here",
                    value=(
                        previous_answer.code or ""
                        if previous_answer
                        else ""
                    ),
                    height=220,
                    key=f"assessment_{attempt_id}_{question.id}",
                )

                answer_updates[question.id] = {
                    "selected_option_id": None,
                    "answer_text": None,
                    "code": code,
                }

            st.divider()

        def build_updated_answers():
            updated_answers = []

            for question in assessment.questions:
                answer_data = answer_updates[question.id]

                has_answer = any(
                    value.strip()
                    if isinstance(value, str)
                    else bool(value)
                    for value in answer_data.values()
                )

                if not has_answer:
                    continue

                updated_answers.append(
                    AssessmentAnswer(
                        question_id=question.id,
                        selected_option_id=answer_data[
                            "selected_option_id"
                        ],
                        answer_text=answer_data["answer_text"],
                        code=answer_data["code"],
                    )
                )

            return updated_answers

        submit_clicked = st.button(
            "Submit Assessment",
            key=f"submit_assessment_{attempt_id}",
            type="primary",
            use_container_width=True,
        )

        if submit_clicked:
            updated_answers = build_updated_answers()

            attempt.answers = updated_answers

            run(
                backend.save_assessment_attempt(attempt)
            )

            if submit_clicked:
                updated_answers = build_updated_answers()
            
                attempt.answers = updated_answers
            
                run(
                    backend.save_assessment_attempt(attempt)
                )
            
                with st.spinner(
                    "Evaluating your assessment..."
                ):
                    completed_attempt = run(
                        submit_assessment_attempt(
                            backend=backend,
                            attempt_id=attempt_id,
                            user_id=user["id"],
                        )
                    )
            
                if completed_attempt.status == "completed":
                    st.success("Your assessment has been completed.")
                    st.rerun()

    except Exception as exc:
        logger.exception(
            "Failed to render or submit active assessment."
        )

        st.error(
            "An error occurred while processing the assessment."
        )

        with st.expander("Error details"):
            st.code(repr(exc))

def render_empty_state(user):
    learner = get_learner(user)
    st.markdown(f"## سلام {html_lib.escape(user['username'])}")

    if learner:
        last = learner[0]
        subject = last["subject"]
        step = last.get("next_step")
        st.caption(
            f"آخرین بار روی «{subject}» کار می‌کردیم. "
            "ادامه بدهیم یا سراغ موضوع تازه‌ای برویم؟"
        )
        suggestions = [
            {
                "text": f"ادامه‌ی «{subject}»" + (f": {step}" if step else ""),
                "icon": ":material/play_arrow:",
            },
            {
                "text": "I want to learn new subject",
                "icon": ":material/explore:",
            },
        ]
    else:
        st.caption(
            "بگو چه چیزی می‌خواهی یاد بگیری. "
            "بخش‌هایی را که از قبل بلدی بگو تا از آن‌ها رد شویم."
        )
        suggestions = [
            {
                "text": "می‌خواهم یک موضوع جدید یاد بگیرم",
                "icon": ":material/explore:",
            },
            {
                "text": "می‌خواهم بگویم چه چیزهایی را از قبل بلدم",
                "icon": ":material/fact_check:",
            },
        ]

    # گزینه‌های آزمون در هر دو حالت نمایش داده می‌شوند.
    suggestions.extend([
        {
            "text": "Placement Test",
            "icon": ":material/quiz:",
        },
        {
            "text": "Assessing the Level of Learning",
            "icon": ":material/assignment_turned_in:",
        },
    ])

    for i, item in enumerate(suggestions):
        if st.button(
            item["text"],
            icon=item["icon"],
            key=f"suggest_{i}",
            use_container_width=True,
        ):
            if item["text"] == "Placement Test":
                st.session_state.pending_assessment_purpose = "placement"
                st.rerun()

            elif item["text"] == "Assessing the Level of Learning":
                st.session_state.pending_assessment_purpose = "learning"
                st.rerun()

            else:
                st.session_state.pending_prompt = item["text"]
                st.rerun()

def render_chat(user):
    if "pending_assessment_purpose" not in st.session_state:
            st.session_state.pending_assessment_purpose = None
    
    if "assessment_setup" not in st.session_state:
        st.session_state.assessment_setup = None
        
    chat_id = st.session_state.active_chat_id
    
    # محافظ: اگر چت فعال وجود نداشت، یکی بساز
    if chat_id not in st.session_state.chats:
        ensure_active_chat(user)
        chat_id = st.session_state.active_chat_id
        
    chat = st.session_state.chats[chat_id]
    messages = get_messages(chat_id)
    
        
    st.markdown(f"### {html_lib.escape(chat['title'])}")
    if st.session_state.pending_assessment_purpose:
        render_assessment_setup(user)
        return

    if st.session_state.assessment_setup:
        render_assessment_start(user, chat_id)
        return
    
    if st.session_state.get("active_assessment_attempt_id"):
        render_active_assessment(user)
        return

    chip_prompt = st.session_state.pop("pending_prompt", None)
    if not messages and not chip_prompt:
        render_empty_state(user)

    for m in messages:
        # تعیین آواتار برای کاربر و هوش مصنوعی
        avatar = "👤" if m["role"] == "user" else "🎓"
        with st.chat_message(m["role"], avatar=avatar):
            st.markdown(m["content"])

    typed = st.chat_input("بنویس چه چیزی می‌خواهی یاد بگیری…", key=f"input_{chat_id}")
    prompt = typed or chip_prompt
    if not prompt:
        return

    first_message = chat["title"] == DEFAULT_CHAT_TITLE
    
    # نمایش پیام کاربر با آواتار
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
    messages.append({"role": "user", "content": prompt})

    answer = None
    # نمایش پاسخ هوش مصنوعی با آواتار
    with st.chat_message("assistant", avatar="🎓"):
        try:
            with st.spinner("Adapta در حال فکر کردن است…"):
                if first_message:
                    # بلوک جداگانه برای تولید عنوان تا در صورت خطا، پاسخ اصلی از بین نرود
                    try:
                        new_title = run(backend.generate_title(prompt))
                        run(backend.rename_chat(user["id"], chat_id, new_title))
                    except Exception:
                        logger.warning("تولید عنوان خودکار با خطا مواجه شد.")
                        fallback_title = prompt[:30] + "..."
                        run(backend.rename_chat(user["id"], chat_id, fallback_title))
                
                answer = run(backend.run_agent(user, chat_id, prompt)).strip()
            if not answer:
                answer = "پاسخی دریافت نشد. پیامت را دوباره بفرست."
            st.markdown(answer)
        except Exception as exc:
            messages.pop()  # پیام ناموفق را از نمایش حذف کن
            answer = None
            st.error("هنگام اجرای Adapta خطایی رخ داد. پیامت را دوباره بفرست.")
            with st.expander("جزئیات خطا"):
                st.code(repr(exc))

    if answer is None:
        return

    messages.append({"role": "assistant", "content": answer})
    run(backend.update_chat_activity(user["id"], chat_id))
    st.session_state.learner_dirty = True

    if first_message:
        st.session_state.chats_dirty = True
        st.rerun()

def flash(kind: str, message: str):
    """پیام موقت که بعد از st.rerun() یک بار نمایش داده می‌شود (success / error / info)."""
    st.session_state.flash = (kind, message)


def render_account_settings(user):
    # nonce: بعد از موفقیت عوض می‌شود تا فرم‌ها (به‌خصوص رمزها) خالی دوباره ساخته شوند.
    n = st.session_state.get("settings_nonce", 0)
    st.markdown("#### تنظیمات حساب")
    tab_name, tab_pass = st.tabs(["تغییر نام کاربری", "تغییر رمز عبور"])

    with tab_name:
        with st.form(f"rename_form_{n}"):
            new_name = st.text_input(
                "نام کاربری جدید", key=f"new_username_{n}",
                help="۳ تا ۲۰ کاراکتر: حرف انگلیسی، عدد و _",
            )
            submitted = st.form_submit_button("ذخیره نام کاربری", type="primary")
        if submitted:
            new_name = new_name.strip()
            if not USERNAME_RE.match(new_name):
                st.error("نام کاربری باید ۳ تا ۲۰ کاراکتر و فقط شامل حرف انگلیسی، عدد و _ باشد.")
            elif new_name.lower() == user["username"].lower():
                st.info("این همان نام کاربری فعلی توست.")
            else:
                try:
                    current = run(crud.update_profile(user["username"], "user_name", new_name))
                except ValueError:
                    st.error("این نام کاربری قبلاً گرفته شده؛ نام دیگری انتخاب کن.")
                except LookupError:
                    st.error("حساب پیدا نشد. دوباره وارد شو.")
                except Exception:
                    show_db_error()
                else:
                    # id عوض نمی‌شود؛ فقط نام نمایشی/ورود
                    st.session_state.user = {**user, "username": current}
                    st.session_state.settings_nonce = n + 1
                    flash("success", f"نام کاربری به «{current}» تغییر کرد.")
                    st.rerun()

    with tab_pass:
        with st.form(f"password_form_{n}"):
            cur_pw = st.text_input("رمز عبور فعلی", type="password", key=f"pw_cur_{n}")
            new_pw = st.text_input("رمز عبور جدید", type="password", key=f"pw_new_{n}",
                                   help="حداقل ۸ کاراکتر")
            conf_pw = st.text_input("تکرار رمز عبور جدید", type="password", key=f"pw_conf_{n}")
            submitted = st.form_submit_button("تغییر رمز عبور", type="primary")
        if submitted:
            if not cur_pw or not new_pw or not conf_pw:
                st.error("هر سه فیلد را پر کن.")
            elif len(new_pw) < 8:
                st.error("رمز عبور جدید باید حداقل ۸ کاراکتر باشد.")
            elif new_pw != conf_pw:
                st.error("تکرار رمز عبور جدید با آن یکسان نیست.")
            elif new_pw == cur_pw:
                st.error("رمز جدید باید با رمز فعلی فرق داشته باشد.")
            else:
                try:
                    valid = run(crud.verify_password(user["username"], cur_pw))
                    if valid:
                        run(crud.update_profile(user["username"], "user_pass", new_pw))
                except LookupError:
                    st.error("حساب پیدا نشد. دوباره وارد شو.")
                except Exception:
                    show_db_error()
                else:
                    if not valid:
                        st.error("رمز عبور فعلی درست نیست.")
                    else:
                        st.session_state.settings_nonce = n + 1
                        flash("success", "رمز عبور تغییر کرد.")
                        st.rerun()


def render_profile(user):
    st.markdown("### پروفایل")
    flash_msg = st.session_state.pop("flash", None)
    if flash_msg:
        getattr(st, flash_msg[0])(flash_msg[1])
    c_av, c_info = st.columns([1, 5], vertical_alignment="center")
    c_av.markdown(
        html(f'<div class="avatar">{html_lib.escape(user["username"][:1].upper())}</div>'),
        unsafe_allow_html=True,
    )
    with c_info:
        st.markdown(f"**{html_lib.escape(user['username'])}**")
        created = user.get("created_at")
        if created:
            if hasattr(created, "strftime"):
                st.caption(f"عضو از {created.strftime('%Y-%m-%d')}")
            else:
                st.caption(f"عضو از {created}")
    st.write("")
    st.markdown("#### آنچه Adapta درباره‌ی یادگیری تو می‌داند")
    learner = get_learner(user)
    if not learner:
        st.info("هنوز چیزی ثبت نشده. در گفتگو بگو چه چیزی می‌خواهی یاد بگیری و Adapta سطحت را یادداشت می‌کند.")
    for item in learner:
        with st.container(border=True):
            st.markdown(f"**{html_lib.escape(item['subject'])}** · سطح: {html_lib.escape(str(item.get('level', '—')))}")
            if item.get("known"):
                st.markdown("بلدی: " + "، ".join(item["known"]))
            if item.get("weak"):
                st.markdown("نیاز به تمرین: " + "، ".join(item["weak"]))
            if item.get("next_step"):
                st.markdown("قدم بعدی: " + item["next_step"])
            with st.popover("پاک‌کردن این موضوع", icon=":material/delete:"):
                st.caption("Adapta دیگر سطح و مباحث این موضوع را به یاد نخواهد داشت.")
                if st.button("پاک شود", key=f"reset_{item['subject']}", type="primary"):
                    run(backend.reset_learner_memory(user["id"], item["subject"]))
                    st.session_state.learner_dirty = True
                    st.rerun()

    st.divider()
    render_account_settings(user)

    st.divider()
    if st.button("خروج از حساب", icon=":material/logout:", key="profile_logout"):
        logout()


def render_dashboard():
    st.markdown("### داشبورد")
    st.info("نمودار پیشرفت و تسلط هر موضوع به‌زودی اینجا اضافه می‌شود.")
    if st.button("بازگشت به گفتگو", icon=":material/arrow_back:", key="dash_back"):
        st.session_state.view = "chat"
        st.rerun()


def render_app(user):
    # ۱. ایجاد یک فضای خالی در بالای صفحه برای نمایش پیام لودینگ
    loading_placeholder = st.empty()
    
    # ۲. نمایش پیام لودینگ (این کار باعث می‌شود فرم ورود فوراً از صفحه پاک شود)
    with loading_placeholder.container():
        st.info("⏳ در حال آماده‌سازی محیط یادگیری... لطفاً صبر کنید.")
        st.spinner() # اگر می‌خواهید اسپینر هم داشته باشید
    
    # ۳. انجام کارهای سنگین (اتصال به دیتابیس و دریافت چت‌ها)
    ensure_active_chat(user)
    
    # ۴. پاک کردن پیام لودینگ
    loading_placeholder.empty()
    
    # ۵. رندر کردن محیط اصلی
    render_sidebar(user)

    view = st.session_state.view

    if view == "profile":
        render_profile(user)
    
    elif view == "dashboard":
        render_dashboard()
    
    else:
        render_chat(user)

# ============================================================
# 8) ROUTER
# ============================================================

if st.session_state.user is None:
    render_auth()
else:
    render_app(st.session_state.user)