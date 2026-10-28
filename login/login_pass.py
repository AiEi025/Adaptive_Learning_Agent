
import bcrypt


class PasswordHasher:
    @staticmethod
    def hash_password(password: str) -> str:
        password_bytes = password.encode("utf-8")

        hashed = bcrypt.hashpw(
            password_bytes,
            bcrypt.gensalt(),
        )

        return hashed.decode("ascii")

    @staticmethod
    def verify_password(
        password: str,
        stored_hash: str,
    ) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("ascii"),
        )
