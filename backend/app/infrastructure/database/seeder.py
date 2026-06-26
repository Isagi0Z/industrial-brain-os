import logging
import uuid
from app.infrastructure.config.settings import settings
from app.infrastructure.di.container import container
from app.domain.auth.constants import SystemRole

logger = logging.getLogger(__name__)


def seed_database():
    if settings.APP_ENV != "development":
        logger.info("Skipping seeder: Not in development environment")
        return

    logger.info("Running development seeder...")

    # Ensure tables are created (instantiating the repository does this in development)
    container.get_user_repository()

    conn = container.get_postgres()
    password_hasher = container.get_password_hasher()

    admin_email = "admin@industrialbrain.local"
    admin_password = "ChangeMe123!"
    hashed_password = password_hasher.get_password_hash(admin_password)
    admin_id = str(uuid.uuid4())
    full_name = "System Administrator"

    try:
        with conn.cursor() as cur:
            # Check if admin already exists
            cur.execute("SELECT id FROM users WHERE email = %s;", (admin_email,))
            if cur.fetchone():
                logger.info(
                    f"Seeder: Default admin {admin_email} already exists. Skipping."
                )
                return

            # Insert admin user
            cur.execute(
                """
                INSERT INTO users (id, email, hashed_password, full_name, is_active)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (admin_id, admin_email, hashed_password, full_name, True),
            )

            # We note the role for audit/verification purposes. In later phases, a proper
            # RBAC relational schema will persist this relationship explicitly.
            logger.info(
                f"Seeder: Successfully created default admin {admin_email} with role {SystemRole.SUPER_ADMIN.value}"
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Seeder failed: {e}")


if __name__ == "__main__":
    seed_database()
