import asyncio
import selectors
import sys
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError


class AsyncRunner:
    """
    پل بین Streamlit (sync) و کدهای async (psycopg، LangGraph، ...).

    یک event loop در یک thread پس‌زمینه تا پایان عمر سرور زنده می‌ماند،
    پس pool دیتابیس و اتصال‌های آن بین rerunها از بین نمی‌روند.
    فقط یک بار (با st.cache_resource) ساخته شود.
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

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout: float | None = 180):
        """کوروتین را روی loop پس‌زمینه اجرا می‌کند و تا آماده شدن نتیجه منتظر می‌ماند."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout)
        except FutureTimeoutError:
            future.cancel()
            raise TimeoutError(f"اجرای عملیات بیش از {timeout} ثانیه طول کشید") from None

    def close(self):
        """توقف loop (معمولاً لازم نیست؛ thread از نوع daemon است)."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
