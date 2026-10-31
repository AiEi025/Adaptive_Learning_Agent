import sys
from pathlib import Path
from typing import Annotated, Literal, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from counting.counting import RetryContext
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Router_state(TypedDict):
    state: Literal["tools", "general"]


class ToolValidationState(BaseModel):
    status: bool
    feedback: str = ""


class Graph_state(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages]

    # ورودی هر نوبت (run_graph مقدار می‌دهد)
    question: str = ""
    thread_id: str = ""
    user_id: str = ""          # فقط از نشست واردشده، نه از مدل
    has_files: bool = False    # کاربر در این گفتگو فایل بارگذاری کرده؟

    # مسیر
    status: Literal["tools", "general"] = "general"

    # حلقه‌ی validation
    validation: bool = True
    validation_feedback: str = ""
    retry: RetryContext = Field(default_factory=RetryContext)
    draft: str = ""            # پیش‌نویس جواب tools (تا قبل از finalize)
    tool_trace: str = ""       # خلاصه‌ی فراخوانی و نتیجه‌ی ابزارها

    # حافظه‌ی یادگیرنده (JSON فشرده) که به prompt داده می‌شود
    memory_context: str = ""