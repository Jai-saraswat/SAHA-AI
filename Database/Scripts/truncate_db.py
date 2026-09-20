import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "Database" / ".env"

load_dotenv(ENV_FILE)


def truncate_database():
    connection = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    try:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT string_agg(
                    format('%I.%I', schemaname, tablename),
                    ', '
                )
                FROM pg_tables
                WHERE schemaname = 'public';
                """
            )

            truncate_statement = cursor.fetchone()[0]

            if truncate_statement:
                cursor.execute(
                    f"""
                    TRUNCATE TABLE
                        {truncate_statement}
                    CASCADE;
                    """
                )

        connection.commit()
        print("Database truncated successfully.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    truncate_database()