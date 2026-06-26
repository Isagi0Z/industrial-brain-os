from typing import Optional
from app.domain.auth.interfaces import IUserRepository
from app.domain.auth.models import User
import psycopg2
import logging

logger = logging.getLogger(__name__)


class PostgresUserRepository(IUserRepository):
    def __init__(self, get_connection_fn):
        self.get_connection_fn = get_connection_fn
        self._ensure_tables()

    def _ensure_tables(self):
        """Creates simple tables for users if they don't exist, for initial development."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(50) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE
        );
        """
        conn = self.get_connection_fn()
        try:
            with conn.cursor() as cur:
                cur.execute(create_table_query)
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Failed to create users table: {e}")

    def _map_row_to_user(self, row: dict) -> User:
        user = User(
            id=row["id"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            full_name=row["full_name"],
            is_active=row["is_active"],
        )
        # TODO: Hydrate roles and permissions when RBAC schema is finalized
        return user

    def get_by_email(self, email: str) -> Optional[User]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, hashed_password, full_name, is_active FROM users WHERE email = %s;",
                (email,),
            )
            row = cur.fetchone()
            if not row:
                return None

            row_dict = {
                "id": str(row[0]),
                "email": row[1],
                "hashed_password": row[2],
                "full_name": row[3],
                "is_active": row[4],
            }
            return self._map_row_to_user(row_dict)

    def get_by_id(self, user_id: str) -> Optional[User]:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, hashed_password, full_name, is_active FROM users WHERE id = %s;",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            row_dict = {
                "id": str(row[0]),
                "email": row[1],
                "hashed_password": row[2],
                "full_name": row[3],
                "is_active": row[4],
            }
            return self._map_row_to_user(row_dict)

    def create(self, user: User) -> User:
        conn = self.get_connection_fn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, hashed_password, full_name, is_active) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
                (
                    user.id,
                    user.email,
                    user.hashed_password,
                    user.full_name,
                    user.is_active,
                ),
            )
            conn.commit()
            return user
