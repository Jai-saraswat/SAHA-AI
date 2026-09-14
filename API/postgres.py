import os
import uuid
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / "Database" / ".env"

load_dotenv(ENV_FILE)


# ---------------------------------------------------------------------
# PostgreSQL connection
# ---------------------------------------------------------------------

def get_connection():
    """Create and return a PostgreSQL connection."""

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


# ---------------------------------------------------------------------
# Read-only query
# ---------------------------------------------------------------------

def execute_read_only(query: str):
    """
    Execute PostgreSQL code in a READ-ONLY transaction.

    PostgreSQL itself enforces the read-only transaction, so commands
    that modify database state will be rejected.
    """

    connection = get_connection()

    try:
        connection.set_session(
            readonly=True,
            autocommit=False,
        )

        with connection.cursor() as cursor:
            cursor.execute(query)

            if cursor.description:
                columns = [
                    column.name
                    for column in cursor.description
                ]

                rows = cursor.fetchall()

                result = [
                    dict(zip(columns, row))
                    for row in rows
                ]

            else:
                result = []

        connection.rollback()

        return result

    finally:
        connection.close()


# ---------------------------------------------------------------------
# Read / write query
# ---------------------------------------------------------------------

def execute_read_write(query: str):
    """
    Execute PostgreSQL code in a READ-WRITE transaction.

    Changes are committed only if the query executes successfully.
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)

            if cursor.description:
                columns = [
                    column.name
                    for column in cursor.description
                ]

                rows = cursor.fetchall()

                result = [
                    dict(zip(columns, row))
                    for row in rows
                ]

            else:
                result = []

        connection.commit()

        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def generate_user_id(username: str):
    """
    Create a new user with a unique user ID and username.
    """

    if not username:
        raise ValueError("Username cannot be empty.")

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT user_id
                FROM users
                WHERE username = %s;
                """,
                (username,),
            )

            existing_user = cursor.fetchone()

            if existing_user:
                return {
                    "created": False,
                    "user_id": str(existing_user[0]),
                    "username": username,
                    "message": "User already exists.",
                }

            user_id = str(uuid.uuid4())

            cursor.execute(
                """
                INSERT INTO users (
                    user_id,
                    username
                )
                VALUES (%s, %s)
                RETURNING user_id;
                """,
                (
                    user_id,
                    username,
                ),
            )

            result = cursor.fetchone()

        connection.commit()

        return {
            "created": True,
            "user_id": str(result[0]),
            "username": username,
            "message": "User created successfully.",
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()