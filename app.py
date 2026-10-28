"""
Adapta - مربی تطبیقی (هر موضوعی)
================================
رابط کاربری Streamlit. منطق Agent و دیتابیس را خودت می‌نویسی؛
هر جا باید به PostgreSQL / LangGraph / DeepSeek وصل شوی با TODO مشخص شده.

ساختار فایل:
  1) تنظیمات صفحه
  2) تم و CSS
  3) AsyncRunner + HOOKS (جایگزین runner واقعی خودت)
  4) State و توابع کمکی
  5) صفحه ورود / ثبت‌نام
  6) Sidebar
  7) صفحه چت، پروفایل، داشبورد
  8) مسیریابی
"""

import copy
import html as html_lib
import logging
import re
import uuid
from datetime import datetime

import streamlit as st

from async_runner import AsyncRunner
from db.crud import Crud

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

/* ---------- راست‌به‌چپ (فقط محتوا؛ نه کانتینر sidebar) ---------- */
[data-testid="stMain"], [data-testid="stBottom"], [data-testid="stSidebarUserContent"] {
    direction: rtl;
}
pre, code, pre * { direction: ltr; text-align: left; }

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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def html(s: str) -> str:
    """HTML چندخطی را فشرده می‌کند تا Markdown آن را کد تلقی نکند."""
    return "".join(line.strip() for line in s.strip().splitlines())


# ============================================================
# 3) RUNNER + CRUD + DEMO BACKEND
# ============================================================
# - AsyncRunner (async_runner.py): فقط پل بین Streamlit و کدهای async.
# - Crud (crud.py): ورود و ثبت‌نام واقعی با PostgreSQL.
# - DemoBackend: چت، Agent و حافظه فعلاً نمایشی و در حافظه‌اند؛
#   روی هر متد نوشته‌ام چه چیزی باید جایگزینش شود (TODO).
#
# معماری حافظه (پیشنهاد):
#   - پیام‌های هر گفتگو  : LangGraph checkpointer (thread_id)  ← مثل نمونه‌ات
#   - حافظه‌ی بلندمدت    : LangGraph Store (مثلاً AsyncPostgresStore) با
#                          namespace = (user_id, "learner") و key = موضوع
#     هر آیتم: {level, known, weak, next_step, updated_at}
#   - Agent دو tool دارد: خواندن و به‌روزرسانی همین حافظه. موضوع آزاد است
#     (SQL، Python، هر چیز دیگر) و مدل خودش تشخیص می‌دهد.


class DemoBackend:
    def __init__(self):
        # TODO: حذف و وصل به PostgreSQL / checkpointer / store
        self.chats, self.messages, self.memory = {}, {}, {}

    # ---------------- گفتگوها ----------------
    async def list_chats(self, user_id: str) -> list:
        """TODO(db): چت‌های کاربر، جدیدترین اول (ORDER BY updated_at DESC).
        هر ردیف: thread_id, title, created_at, updated_at."""
        rows = [c for c in self.chats.values() if c["user_id"] == user_id]
        return sorted(rows, key=lambda c: c["updated_at"], reverse=True)

    async def create_chat(self, user_id: str, thread_id: str, title: str):
        """TODO(db): INSERT INTO chats(thread_id, user_id, title, ...)."""
        now = datetime.now()
        self.chats[thread_id] = {"thread_id": thread_id, "user_id": user_id,
                                 "title": title, "created_at": now, "updated_at": now}
        self.messages[thread_id] = []

    async def rename_chat(self, thread_id: str, title: str):
        """TODO(db): UPDATE chats SET title = $2 WHERE thread_id = $1."""
        if thread_id in self.chats:
            self.chats[thread_id]["title"] = title

    async def delete_chat(self, user_id: str, thread_id: str):
        """TODO(db): حذف چت (و در صورت نیاز checkpointهای thread)."""
        self.chats.pop(thread_id, None)
        self.messages.pop(thread_id, None)

    async def update_chat_activity(self, thread_id: str):
        """TODO(db): UPDATE chats SET updated_at = now()."""
        if thread_id in self.chats:
            self.chats[thread_id]["updated_at"] = datetime.now()

    async def get_chat_messages(self, thread_id: str) -> list:
        """TODO(checkpointer): پیام‌های thread را بخوان و به
        [{'role': 'user'|'assistant', 'content': str}] تبدیل کن.
        همان تبدیل HumanMessage/AIMessage و رد کردن پیام‌های tool_calls
        که در load_chat_messages نمونه‌ات داشتی اینجا بیاید."""
        return list(self.messages.get(thread_id, []))

    # ---------------- Agent ----------------
    async def generate_title(self, user_input: str) -> str:
        """TODO(llm): عنوان کوتاه با DeepSeek (prompt عنوان‌سازی نمونه‌ات)."""
        return user_input.strip().replace("\n", " ")[:40] or DEFAULT_CHAT_TITLE

    async def run_agent(self, user: dict, thread_id: str, user_input: str) -> str:
        """TODO(llm): اجرای graph با thread_id (و user_id در config).
        مثل نمونه‌ات: result = await run_graph(user_input=..., thread_id=..., graph=...)
        و آخرین AIMessage بدون tool_calls را برگردان.
        پیام‌ها را checkpointer ذخیره می‌کند؛ این‌جا فقط برای نمایش دستی ذخیره می‌شود."""
        answer = (
            "(پاسخ نمایشی) Agent واقعی هنوز وصل نیست.\n\n"
            f"پیام تو: {user_input}"
        )
        self.messages.setdefault(thread_id, []).extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": answer},
        ])
        return answer

    # ---------------- حافظه‌ی بلندمدت یادگیرنده ----------------
    async def get_learner_memory(self, user_id: str) -> list:
        """TODO(store): همه‌ی آیتم‌های namespace (user_id, 'learner'),
        جدیدترین اول. هر آیتم:
        {'subject','level','known':[...],'weak':[...],'next_step','updated_at'}"""
        items = list(self.memory.get(user_id, {}).values())
        return sorted(items, key=lambda m: m["updated_at"], reverse=True)

    async def reset_learner_memory(self, user_id: str, subject: str):
        """TODO(store): حذف آیتم موضوع از store."""
        self.memory.get(user_id, {}).pop(subject, None)


@st.cache_resource
def get_async_runner() -> AsyncRunner:
    return AsyncRunner()


runner = get_async_runner()


def run(coro):
    return runner.run(coro)


@st.cache_resource
def get_crud() -> Crud:
    async def _make():
        c = Crud()
        await c.open()  # pool روی loop پس‌زمینه باز می‌شود
        return c

    return runner.run(_make())


@st.cache_resource
def get_backend() -> DemoBackend:
    return DemoBackend()


crud = get_crud()
backend = get_backend()


logger = logging.getLogger("adapta")


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
        st.session_state.learner = run(backend.get_learner_memory(user["id"]))
        st.session_state.learner_dirty = False
    return st.session_state.learner


# ============================================================
# 5) AUTH PAGE
# ============================================================


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

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("نام کاربری", key="login_username")
                password = st.text_input("رمز عبور", type="password", key="login_password")
                submitted = st.form_submit_button("ورود", type="primary", use_container_width=True)
            if submitted:
                if not username.strip() or not password:
                    st.error("نام کاربری و رمز عبور را وارد کن.")
                else:
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
                    try:
                        row = run(crud.register(username, password))
                    except ValueError:
                        st.error("این نام کاربری قبلاً گرفته شده؛ نام دیگری انتخاب کن.")
                    except Exception:
                        show_db_error()
                    else:
                        sign_in(to_app_user(row))  # ثبت‌نام موفق ← مستقیم وارد چت


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
            with c_menu:
                with st.popover("⋮", use_container_width=True):
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


def render_empty_state(user):
    learner = get_learner(user)
    st.markdown(f"## سلام {html_lib.escape(user['username'])}")

    if learner:
        last = learner[0]
        subject = last["subject"]
        step = last.get("next_step")
        st.caption(f"آخرین بار روی «{subject}» کار می‌کردیم. ادامه بدهیم یا سراغ موضوع تازه‌ای برویم؟")
        suggestions = [
            f"ادامه‌ی «{subject}»" + (f": {step}" if step else ""),
            "می‌خواهم یک موضوع جدید یاد بگیرم",
        ]
    else:
        st.caption("بگو چه چیزی می‌خواهی یاد بگیری. بخش‌هایی را که از قبل بلدی بگو تا از آن‌ها رد شویم، یا بگذار با چند سؤال سطحت را بسنجم.")
        suggestions = [
            "می‌خواهم یک موضوع جدید یاد بگیرم",
            "از من آزمون بگیر تا سطحم را بسنجی",
            "می‌خواهم بگویم چه چیزهایی را از قبل بلدم",
        ]

    for i, text in enumerate(suggestions):
        if st.button(text, key=f"suggest_{i}", use_container_width=True):
            st.session_state.pending_prompt = text
            st.rerun()


def render_chat(user):
    chat_id = st.session_state.active_chat_id
    chat = st.session_state.chats[chat_id]
    messages = get_messages(chat_id)

    st.markdown(f"### {html_lib.escape(chat['title'])}")

    chip_prompt = st.session_state.pop("pending_prompt", None)
    if not messages and not chip_prompt:
        render_empty_state(user)

    for m in messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    typed = st.chat_input("بنویس چه چیزی می‌خواهی یاد بگیری…", key=f"input_{chat_id}")
    prompt = typed or chip_prompt
    if not prompt:
        return

    first_message = chat["title"] == DEFAULT_CHAT_TITLE
    with st.chat_message("user"):
        st.markdown(prompt)
    messages.append({"role": "user", "content": prompt})

    answer = None
    with st.chat_message("assistant"):
        try:
            with st.spinner("Adapta در حال فکر کردن است…"):
                if first_message:
                    new_title = run(backend.generate_title(prompt))
                    run(backend.rename_chat(chat_id, new_title))
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
    run(backend.update_chat_activity(chat_id))
    st.session_state.learner_dirty = True  # Agent ممکن است حافظه را به‌روز کرده باشد

    if first_message:
        # فقط بار اول rerun می‌کنیم تا عنوان جدید در sidebar دیده شود.
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
            st.caption(f"عضو از {created.strftime('%Y-%m-%d')}")

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
    ensure_active_chat(user)
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
