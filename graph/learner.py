"""
Adapta - مدل یادگیرنده (منطق خالص؛ بدون LLM و بدون دیتابیس)

هم nodes.py (حافظه‌ی Agent) و هم async_runner.py (پروفایل/داشبورد) از همین‌جا
استفاده می‌کنند. ایمپورت سبک است، پس رابط کاربری چیزی از LLM بار نمی‌کند.

ساختار JSON (کلید: ("adapta", user_id, "learner") / "profile"):
{
  "version": 2,
  "name": "", "occupation": "", "language": "", "response_style": "",
  "interests": [], "notes": [],
  "goals": [{"text": "...", "due": "YYYY-MM-DD" | ""}],
  "last_session": {"subject": "", "summary": "", "date": "YYYY-MM-DD"},
  "subjects": {
    "SQL": {
      "level": "beginner|intermediate|advanced",
      "roadmap": ["SELECT", "WHERE", ...],
      "mastery": {"SELECT": {"score": 0.74, "source": "demonstrated|stated",
                             "attempts": 3, "last_practiced": "YYYY-MM-DD"}},
      "misconceptions": ["confuses WHERE and HAVING"],
      "next_step": ""
    }
  }
}
مدل فقط «مشاهده» پیشنهاد می‌دهد؛ عدد تسلط را کد این فایل حساب می‌کند.
"""

import logging
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("adapta.learner")

NAMESPACE_ROOT = "adapta"
PROFILE_KEY = "profile"
SCHEMA_VERSION = 2

MAX_ITEMS = 40
MAX_NOTES = 20
MAX_ROADMAP = 15
VALID_LEVELS = {"beginner", "intermediate", "advanced"}
SCALARS = {"name", "occupation", "language", "response_style"}

KNOWN_MIN = 0.7          # تسلط ≥ این مقدار = «بلد»
WEAK_MAX = 0.45          # تسلط < این مقدار = «ضعیف»
BASE_SCORE = 0.4         # شروع تسلط وقتی اولین بار در تمرین دیده می‌شود
STATED_KNOWN_SCORE = 0.7
STATED_WEAK_SCORE = 0.3
REVIEW_AFTER_DAYS = 7    # مبحث بلد، ولی چند روز تمرین نشده ← پیشنهاد مرور
ALPHA_UP = {"easy": 0.15, "medium": 0.25, "hard": 0.35}
ALPHA_DOWN = {"easy": 0.35, "medium": 0.25, "hard": 0.15}


# ============================================================
# مدل‌های خروجی LLM
# ============================================================


class ProfileChange(BaseModel):
    action: Literal["set", "add", "remove"] = Field(description="The type of change")
    field: Literal[
        "name", "occupation", "language", "response_style",
        "interests", "notes", "goals",
        "level", "next_step", "misconception",
    ] = Field(description="The profile field to change")
    subject: str = Field(default="", description="Required for level, next_step, misconception")
    value: str = Field(description="The value to set, add, or remove")
    due: str = Field(default="", description="Goal deadline as YYYY-MM-DD, only if the user gave a date")


class Observation(BaseModel):
    subject: str
    topic: str
    kind: Literal[
        "stated_known",
        "stated_weak",
        "answered_correct",
        "answered_wrong",
    ]
    difficulty: Literal["easy", "medium", "hard"] | None = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def normalize_difficulty(cls, value):
        if value == "":
            return None
        return value
    
class MemoryUpdate(BaseModel):
    changes: list[ProfileChange] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    roadmap_subject: str = ""
    roadmap: list[str] = Field(default_factory=list)
    session_subject: str = ""
    session_note: str = ""


# ============================================================
# ساخت و مهاجرت پروفایل
# ============================================================


def namespace(user_id: str) -> tuple:
    return (NAMESPACE_ROOT, user_id, "learner")


def today() -> date:
    return datetime.now(UTC).date()


def new_subject() -> dict:
    return {"level": "", "roadmap": [], "mastery": {}, "misconceptions": [], "next_step": ""}


def empty_profile() -> dict:
    return {
        "version": SCHEMA_VERSION, "name": "", "occupation": "", "language": "",
        "response_style": "", "interests": [], "notes": [], "goals": [],
        "last_session": {}, "subjects": {},
    }


def migrate(profile) -> dict:
    """هر ورودی (v1 یا v2 یا None) را به یک ساختار v2 تازه تبدیل می‌کند (کپی؛ ورودی تغییر نمی‌کند)."""
    p = empty_profile()
    if not isinstance(profile, dict):
        return p

    for k in SCALARS:
        if isinstance(profile.get(k), str):
            p[k] = profile[k]
    for k in ("interests", "notes"):
        if isinstance(profile.get(k), list):
            p[k] = [str(x) for x in profile[k]][:MAX_ITEMS]
    for g in profile.get("goals") or []:
        if isinstance(g, str) and g.strip():
            p["goals"].append({"text": g.strip(), "due": ""})
        elif isinstance(g, dict) and str(g.get("text", "")).strip():
            p["goals"].append({"text": str(g["text"]).strip(), "due": str(g.get("due") or "")})
    if isinstance(profile.get("last_session"), dict):
        p["last_session"] = dict(profile["last_session"])

    for name, e in (profile.get("subjects") or {}).items():
        if not isinstance(e, dict):
            continue
        ne = new_subject()
        ne["level"] = str(e.get("level") or "")
        ne["next_step"] = str(e.get("next_step") or "")
        ne["roadmap"] = [str(t) for t in (e.get("roadmap") or [])]
        ne["misconceptions"] = [str(t) for t in (e.get("misconceptions") or [])]
        ne["mastery"] = {t: dict(m) for t, m in (e.get("mastery") or {}).items() if isinstance(m, dict)}
        # v1: known / weak → تسلط
        for t in e.get("known") or []:
            ne["mastery"].setdefault(t, {"score": STATED_KNOWN_SCORE, "source": "stated",
                                         "attempts": 0, "last_practiced": ""})
        for t in e.get("weak") or []:
            ne["mastery"].setdefault(t, {"score": STATED_WEAK_SCORE, "source": "stated",
                                         "attempts": 0, "last_practiced": ""})
        p["subjects"][str(name)] = ne
    return p


# ============================================================
# ابزارهای داخلی
# ============================================================


def _days_since(iso: str | None, now: date) -> int | None:
    try:
        return (now - date.fromisoformat(iso)).days if iso else None
    except ValueError:
        return None


def _valid_date(s: str) -> str:
    try:
        return date.fromisoformat((s or "").strip()).isoformat()
    except ValueError:
        return ""


def _apply_list(items: list, action: str, value: str, cap: int) -> None:
    folded = value.casefold()
    if action == "add":
        if folded not in {i.casefold() for i in items}:
            if len(items) >= cap:
                items.pop(0)          # قدیمی‌ترین کنار می‌رود
            items.append(value)
    elif action == "remove":
        items[:] = [i for i in items if i.casefold() != folded]


def _apply_goal(goals: list, action: str, text: str, due: str) -> None:
    folded = text.casefold()
    existing = next((g for g in goals if g["text"].casefold() == folded), None)
    if action == "add":
        if existing:
            if _valid_date(due):
                existing["due"] = _valid_date(due)
            return
        if len(goals) >= MAX_ITEMS:
            goals.pop(0)
        goals.append({"text": text, "due": _valid_date(due)})
    elif action == "remove" and existing:
        goals.remove(existing)


def _score_map(mastery: dict) -> dict:
    return {k.casefold(): m for k, m in mastery.items()}


def _match_topic(entry: dict, topic: str) -> str:
    """نام مبحث را با roadmap/تسلط‌های موجود یکی می‌کند (بدون حساسیت به حروف)."""
    topic = topic.strip()[:60]
    folded = topic.casefold()
    for t in [*entry["roadmap"], *entry["mastery"].keys()]:
        if t.casefold() == folded:
            return t
    return topic


def _record(entry: dict, topic: str, kind: str, difficulty: str, iso: str) -> tuple[str, float]:
    topic = _match_topic(entry, topic)
    m = entry["mastery"].get(topic)

    if kind == "stated_known":
        if m is None:
            m = {"score": STATED_KNOWN_SCORE, "source": "stated", "attempts": 0}
        elif m.get("source") != "demonstrated" and m["score"] < STATED_KNOWN_SCORE:
            m["score"] = STATED_KNOWN_SCORE      # ادعای کاربر، تسلط اثبات‌شده را بالا/پایین نمی‌برد
    elif kind == "stated_weak":
        if m is None:
            m = {"score": STATED_WEAK_SCORE, "source": "stated", "attempts": 0}
        else:
            m["score"] = min(m["score"], STATED_WEAK_SCORE)
    else:
        m = m or {"score": BASE_SCORE, "source": "demonstrated", "attempts": 0}
        if kind == "answered_correct":
            m["score"] += ALPHA_UP[difficulty] * (1 - m["score"])
        else:
            m["score"] -= ALPHA_DOWN[difficulty] * m["score"]
        m["source"] = "demonstrated"
        m["attempts"] = int(m.get("attempts", 0)) + 1

    m["score"] = round(max(0.0, min(1.0, m["score"])), 3)
    m["last_practiced"] = iso
    entry["mastery"][topic] = m
    return topic, m["score"]


def _event(subject, topic, kind, correct, difficulty, mastery_after) -> dict:
    return {"subject": subject or "", "topic": topic, "kind": kind,
            "correct": correct, "difficulty": difficulty, "mastery_after": mastery_after}


def _progress(entry: dict) -> float | None:
    roadmap = entry["roadmap"]
    if not roadmap:
        return None
    scores = _score_map(entry["mastery"])
    done = sum(1 for t in roadmap if scores.get(t.casefold(), {}).get("score", 0) >= KNOWN_MIN)
    return done / len(roadmap)


def _recalc_level(entry: dict, key: str, events: list) -> None:
    """سطح را از پیشرفت نقشه‌ی راه به‌روز می‌کند؛ فقط با شواهد کافی (≥۳ مبحث اثبات‌شده)."""
    demonstrated = [m for m in entry["mastery"].values() if m.get("source") == "demonstrated"]
    progress = _progress(entry)
    if len(demonstrated) < 3 or progress is None:
        return
    level = "beginner" if progress < 0.35 else "intermediate" if progress < 0.7 else "advanced"
    if level != entry["level"]:
        entry["level"] = level
        events.append(_event(key, None, "level_assessed", None, None, round(progress, 3)))


# ============================================================
# اعمال خروجی مدل
# ============================================================


def apply_update(profile, update: MemoryUpdate, now: date) -> tuple[dict, list]:
    """(پروفایل جدید، رویدادها). ورودی تغییر نمی‌کند."""
    p = migrate(profile)
    iso = now.isoformat()
    subjects = p["subjects"]
    events: list[dict] = []

    def get_entry(subject: str):
        subject = (subject or "").strip()[:60]
        if not subject:
            return None, ""
        key = next((k for k in subjects if k.casefold() == subject.casefold()), subject)
        return subjects.setdefault(key, new_subject()), key

    for ch in update.changes:
        value = (ch.value or "").strip()
        if not value:
            continue
        f, act = ch.field, ch.action

        if f in SCALARS:
            if act == "set":
                p[f] = value[:80]
        elif f in ("interests", "notes"):
            _apply_list(p[f], act, value[:120], MAX_NOTES if f == "notes" else MAX_ITEMS)
        elif f == "goals":
            _apply_goal(p["goals"], act, value[:120], ch.due)
        else:
            entry, key = get_entry(ch.subject)
            if entry is None:
                continue
            if f == "level":
                level = value.lower()
                if act == "set" and level in VALID_LEVELS and entry["level"] != level:
                    entry["level"] = level
                    events.append(_event(key, None, "level_set", None, None, None))
            elif f == "next_step":
                entry["next_step"] = value[:120] if act == "set" else ""
            elif f == "misconception":
                _apply_list(entry["misconceptions"], act, value[:120], 10)

    touched = set()
    if update.roadmap and (update.roadmap_subject or "").strip():
        entry, key = get_entry(update.roadmap_subject)
        if entry is not None and not entry["roadmap"]:       # فقط یک بار
            topics, seen = [], set()
            for t in update.roadmap:
                t = (t or "").strip()[:60]
                if t and t.casefold() not in seen:
                    seen.add(t.casefold())
                    topics.append(t)
            if topics:
                entry["roadmap"] = topics[:MAX_ROADMAP]
                events.append(_event(key, None, "roadmap_created", None, None, None))
                touched.add(key)

    for ob in update.observations:
        entry, key = get_entry(ob.subject)
        if entry is None or not (ob.topic or "").strip():
            continue
        topic, score = _record(entry, ob.topic, ob.kind, ob.difficulty, iso)
        correct = True if ob.kind == "answered_correct" else False if ob.kind == "answered_wrong" else None
        events.append(_event(key, topic, ob.kind, correct, ob.difficulty, score))
        touched.add(key)

    for key in touched:
        _recalc_level(subjects[key], key, events)

    note = (update.session_note or "").strip()
    if note:
        subject = (update.session_subject or "").strip()[:60]
        if (p.get("last_session") or {}).get("date") != iso:
            events.append(_event(subject, None, "session_start", None, None, None))
        p["last_session"] = {"subject": subject, "summary": note[:200], "date": iso}

    return p, events


# ============================================================
# نمایش‌ها
# ============================================================


def subject_summary(entry: dict, now: date) -> dict:
    mastery = entry["mastery"]
    known = [t for t, m in mastery.items() if m["score"] >= KNOWN_MIN]
    weak = [t for t, m in mastery.items() if m["score"] < WEAK_MAX]
    review = [
        t for t in known
        if mastery[t].get("source") == "demonstrated"
        and (_days_since(mastery[t].get("last_practiced"), now) or 0) >= REVIEW_AFTER_DAYS
    ]
    scores = _score_map(mastery)
    todo = [t for t in entry["roadmap"] if scores.get(t.casefold(), {}).get("score", 0) < KNOWN_MIN]
    progress = _progress(entry)
    return {
        "level": entry["level"], "known": known, "weak": weak, "review_due": review,
        "misconceptions": entry["misconceptions"], "next_step": entry["next_step"],
        "roadmap_next": todo[:3],
        "progress_pct": None if progress is None else round(progress * 100),
    }


def prompt_view(profile: dict, now: date, include_roadmap: bool = False) -> str:
    """نمای فشرده برای prompt (فیلدهای خالی حذف می‌شوند). profile باید migrate شده باشد."""
    import json

    view: dict = {"today": now.isoformat()}
    for k in ("name", "occupation", "language", "response_style"):
        if profile.get(k):
            view[k] = profile[k]
    for k in ("interests", "notes"):
        if profile.get(k):
            view[k] = profile[k]
    goals = [g["text"] + (f" (due {g['due']})" if g.get("due") else "") for g in profile["goals"]]
    if goals:
        view["goals"] = goals
    ls = profile.get("last_session") or {}
    if ls.get("summary"):
        view["last_session"] = f"{ls.get('date', '')} {ls.get('subject', '')}: {ls['summary']}".strip()

    subjects = {}
    for name, entry in profile["subjects"].items():
        s = {k: v for k, v in subject_summary(entry, now).items() if v not in ("", [], None)}
        if include_roadmap and entry["roadmap"]:
            s["roadmap"] = entry["roadmap"]
        subjects[name] = s
    if subjects:
        view["subjects"] = subjects
    return json.dumps(view, ensure_ascii=False, separators=(",", ":"))


def dashboard_view(profile, now: date) -> list:
    """لیست موضوع‌ها برای پروفایل/داشبورد."""
    p = migrate(profile)
    out = []
    for name, entry in p["subjects"].items():
        scores = _score_map(entry["mastery"])
        roadmap = []
        for t in entry["roadmap"]:
            m = scores.get(t.casefold())
            status = "todo" if not m else "mastered" if m["score"] >= KNOWN_MIN else "learning"
            roadmap.append({"topic": t, "status": status, "score": (m or {}).get("score")})
        out.append({"subject": name, **subject_summary(entry, now),
                    "level": entry["level"] or "—", "roadmap": roadmap,
                    "mastery": entry["mastery"]})
    return out


def about_view(profile) -> dict:
    p = migrate(profile)
    return {k: p[k] for k in ("name", "occupation", "language", "response_style",
                              "interests", "notes", "goals", "last_session")}


# ============================================================
# ثبت رویداد (sink توسط runner تنظیم می‌شود)
# ============================================================

_event_sink = None


def set_event_sink(fn) -> None:
    global _event_sink
    _event_sink = fn


async def emit_events(user_id: str, thread_id: str, events: list) -> None:
    if not events or _event_sink is None:
        return
    try:
        await _event_sink(user_id, thread_id, events)
    except Exception:
        logger.exception("event sink failed")