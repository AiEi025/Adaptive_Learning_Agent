import asyncio
import os
from typing import Literal

from dotenv import load_dotenv
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from login.login_pass import PasswordHasher

load_dotenv()


class Crud:
    """
    یک نمونه‌ی مشترک برای کل برنامه (نه یکی به ازای هر کاربر).
    user_name به‌عنوان آرگومان به هر متد داده می‌شود.
    """

    def __init__(self):
        # تنظیمات اتصال دقیقاً مثل قبل
        self.__connection = AsyncConnectionPool(
            conninfo=os.environ["DATABASE_URL"],
            min_size=1,
            max_size=3,
            open=False,
            kwargs={"row_factory": dict_row},
        )

        self._pass_hash = PasswordHasher()

    async def open(self):
        await self.__connection.open()
        await self.__connection.wait()

    async def close(self):
        await self.__connection.close()

    # ------------------------------------------------------------
    # توابع کمکی
    # ------------------------------------------------------------

    @staticmethod
    def _norm(user_name: str) -> str:
        """نام کاربری را یکدست می‌کند تا Ali و ali دو کاربر جدا نشوند."""
        return user_name.strip().lower()

    @staticmethod
    def _public(user: dict | None) -> dict | None:
        """هش رمز هرگز از Crud بیرون نمی‌رود."""
        if user is None:
            return None
        return {k: v for k, v in user.items() if k != "user_pass"}

    async def _hash(self, password: str) -> str:
        # هش کردن CPU-bound است؛ در thread جدا اجرا می‌شود تا
        # event loop (و بقیه‌ی کاربران) بلاک نشوند.
        return await asyncio.to_thread(self._pass_hash.hash_password, password)

    async def _verify(self, password: str, hashed: str) -> bool:
        def check() -> bool:
            try:
                # TODO: اسم متد و ترتیب آرگومان‌ها را مطابق PasswordHasher خودت بگذار
                return bool(self._pass_hash.verify_password(password, hashed))
            except ValueError:
                # هش خراب/نامعتبر؛ خطاهای برنامه‌نویسی (مثل TypeError) عمداً پنهان نمی‌شوند
                return False

        return await asyncio.to_thread(check)

    # ------------------------------------------------------------
    # خواندن
    # ------------------------------------------------------------

    async def is_exist(self, user_name: str) -> bool:
        async with self.__connection.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1 FROM public.users
                WHERE user_name = %s
                LIMIT 1
                """,
                (self._norm(user_name),),
            )
            return await cur.fetchone() is not None

    async def get_user(self, user_name: str) -> dict | None:
        """ردیف کامل کاربر (شامل هش رمز). فقط داخل Crud استفاده شود."""
        async with self.__connection.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM public.users WHERE user_name = %s",
                (self._norm(user_name),),
            )
            return await cur.fetchone()

    # ------------------------------------------------------------
    # ثبت‌نام و ورود
    # ------------------------------------------------------------

    async def register(self, user_name: str, password: str) -> dict:
        """
        کاربر جدید می‌سازد و ردیف او را (بدون هش رمز) برمی‌گرداند.
        اگر نام کاربری تکراری بود ValueError("username_taken") می‌دهد.
        این کار به قید UNIQUE روی ستون user_name تکیه دارد (پایین توضیح داده شده).
        """
        user_name = self._norm(user_name)
        password_hash = await self._hash(password)  # بیرون از اتصال؛ اتصال زود آزاد می‌شود

        async with self.__connection.connection() as conn, conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO public.users (user_name, user_pass)
                    VALUES (%s, %s)
                    RETURNING *
                    """,
                    (user_name, password_hash),
                )
            except UniqueViolation:
                raise ValueError("username_taken") from None
            user = await cur.fetchone()

        return self._public(user)

    async def verify_password(self, user_name: str, password: str) -> bool:
        """فقط درستی رمز را چک می‌کند (بدون به‌روزرسانی last_login).
        برای تأیید رمز فعلی قبل از تغییر رمز استفاده می‌شود."""
        user = await self.get_user(user_name)
        if user is None:
            return False
        return await self._verify(password, user["user_pass"])

    async def authenticate(self, user_name: str, password: str) -> dict | None:
        """
        اگر نام کاربری و رمز درست بود، ردیف کاربر (بدون هش رمز) و در غیر
        این صورت None برمی‌گرداند. last_login هم به‌روز می‌شود.
        """
        user = await self.get_user(user_name)
        if user is None:
            return None
        if not await self._verify(password, user["user_pass"]):
            return None

        await self.update_profile(user["user_name"], "last_login")
        return self._public(user)

    # ------------------------------------------------------------
    # به‌روزرسانی پروفایل
    # ------------------------------------------------------------

    async def update_profile(
        self,
        user_name: str,
        update_col: Literal["user_name", "user_pass", "last_login"],
        param_change: str | None = None,
    ) -> str:
        """
        یکی از ستون‌های پروفایل را عوض می‌کند و user_name فعلی کاربر را
        برمی‌گرداند (بعد از تغییر نام، همان نام جدید است).
        """
        user_name = self._norm(user_name)

        if update_col in ("user_name", "user_pass") and not param_change:
            raise ValueError(f"param_change برای {update_col} الزامی است")

        if update_col == "user_name":
            new_value = self._norm(param_change)
            query = """
                UPDATE public.users
                SET user_name = %s, updated_at = now()
                WHERE user_name = %s
            """
            params = (new_value, user_name)

        elif update_col == "user_pass":
            hashed = await self._hash(param_change)
            query = """
                UPDATE public.users
                SET user_pass = %s, updated_at = now()
                WHERE user_name = %s
            """
            params = (hashed, user_name)

        elif update_col == "last_login":
            query = """
                UPDATE public.users
                SET last_login = now()
                WHERE user_name = %s
            """
            params = (user_name,)

        else:
            raise ValueError(f"update_col نامعتبر: {update_col!r}")

        async with self.__connection.connection() as conn, conn.cursor() as cur:
            try:
                await cur.execute(query, params)
            except UniqueViolation:
                raise ValueError("username_taken") from None

            if cur.rowcount == 0:
                raise LookupError(f"کاربر {user_name!r} پیدا نشد")

        return new_value if update_col == "user_name" else user_name