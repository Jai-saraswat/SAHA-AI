"""
SAHA - Database Schema Initialization

schema.sql is the single source of truth.

Behavior:

- If the database does not exist:
    Create it and apply schema.sql.

- If the database exists:
    Compare its schema with schema.sql.

    If identical:
        Leave the database untouched.

    If different:
        Clear existing data and rebuild the schema from schema.sql.
"""

from pathlib import Path
import os
import re
import subprocess
import sys
import uuid

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "Database" / ".env"
SCHEMA_FILE = PROJECT_ROOT / "Database" / "schema.sql"


def load_configuration():
    if not ENV_FILE.exists():
        raise FileNotFoundError(
            f"Environment file not found: {ENV_FILE}"
        )

    load_dotenv(ENV_FILE)

    configuration = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

    required = ("database", "user", "password")

    missing = [
        key
        for key in required
        if not configuration[key]
    ]

    if missing:
        raise RuntimeError(
            "Missing PostgreSQL configuration: "
            + ", ".join(
                f"POSTGRES_{key.upper()}"
                for key in missing
            )
        )

    return configuration


# ---------------------------------------------------------------------
# PostgreSQL connections
# ---------------------------------------------------------------------

def connect(database, configuration):
    return psycopg2.connect(
        host=configuration["host"],
        port=configuration["port"],
        dbname=database,
        user=configuration["user"],
        password=configuration["password"],
    )


def database_exists(configuration):
    connection = connect("postgres", configuration)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_database
                    WHERE datname = %s
                );
                """,
                (configuration["database"],),
            )

            return cursor.fetchone()[0]

    finally:
        connection.close()


def create_database(configuration, database_name):
    connection = connect("postgres", configuration)

    try:
        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(database_name)
                )
            )

    finally:
        connection.close()


def drop_database(configuration, database_name):
    connection = connect("postgres", configuration)

    try:
        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(database_name)
                )
            )

    finally:
        connection.close()


# ---------------------------------------------------------------------
# Schema application
# ---------------------------------------------------------------------

def apply_schema(database, configuration):
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_FILE}"
        )

    schema_sql = SCHEMA_FILE.read_text(
        encoding="utf-8"
    )

    if not schema_sql.strip():
        raise RuntimeError(
            f"Schema file is empty: {SCHEMA_FILE}"
        )

    connection = connect(database, configuration)

    try:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ---------------------------------------------------------------------
# Schema dump
# ---------------------------------------------------------------------

def find_docker():
    """
    Find Docker executable.
    """

    candidates = [
        "docker",
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    ]

    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return candidate

        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    raise RuntimeError(
        "Docker executable could not be found."
    )


def dump_schema(database, configuration):
    """
    Dump the database schema using pg_dump from the
    running PostgreSQL Docker container.
    """

    docker = find_docker()

    command = [
        docker,
        "exec",
        "saha-postgres",
        "pg_dump",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "-U",
        configuration["user"],
        "-d",
        database,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "pg_dump failed:\n"
            + result.stderr
        )

    return normalize_schema_dump(result.stdout)


def normalize_schema_dump(schema):
    """
    Remove pg_dump-generated information that should not affect
    schema comparison.

    The actual database objects remain part of the comparison.
    """

    lines = []

    for line in schema.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("--"):
            continue

        if stripped.startswith("SET "):
            continue

        if stripped.startswith("SELECT pg_catalog.set_config"):
            continue

        if stripped.startswith("CREATE SCHEMA"):
            continue

        if stripped.startswith("COMMENT ON SCHEMA"):
            continue

        lines.append(
            re.sub(r"\s+", " ", stripped)
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------
# Database reset
# ---------------------------------------------------------------------

def reset_database(configuration):
    """
    Remove all existing public database objects and rebuild
    them from schema.sql.
    """

    database = configuration["database"]

    connection = connect(database, configuration)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP SCHEMA IF EXISTS public CASCADE;"
            )

            cursor.execute(
                "CREATE SCHEMA public;"
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    apply_schema(
        database,
        configuration,
    )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    configuration = load_configuration()

    database = configuration["database"]

    print("=" * 60)
    print("SAHA DATABASE SCHEMA CHECK")
    print("=" * 60)

    # -------------------------------------------------------------
    # Database existence
    # -------------------------------------------------------------

    if not database_exists(configuration):

        print(
            f"\nDatabase '{database}' does not exist."
        )

        print(
            f"Creating database '{database}'..."
        )

        create_database(
            configuration,
            database,
        )

        print("Database created.")

        print("Applying schema.sql...")

        apply_schema(
            database,
            configuration,
        )

        print("Schema applied successfully.")
        print("\nDatabase is ready.")

        return

    print(
        f"\nDatabase '{database}' already exists."
    )

    # -------------------------------------------------------------
    # Create temporary database
    # -------------------------------------------------------------

    temporary_database = (
        f"saha_schema_check_{uuid.uuid4().hex[:12]}"
    )

    print(
        "\nCreating temporary database for schema comparison..."
    )

    create_database(
        configuration,
        temporary_database,
    )

    try:

        # ---------------------------------------------------------
        # Apply schema.sql to temporary database
        # ---------------------------------------------------------

        print(
            "Applying schema.sql to temporary database..."
        )

        apply_schema(
            temporary_database,
            configuration,
        )

        # ---------------------------------------------------------
        # Dump both schemas
        # ---------------------------------------------------------

        print(
            "Comparing database schema with schema.sql..."
        )

        current_schema = dump_schema(
            database,
            configuration,
        )

        expected_schema = dump_schema(
            temporary_database,
            configuration,
        )

        # ---------------------------------------------------------
        # Compare
        # ---------------------------------------------------------

        if current_schema == expected_schema:

            print(
                "\nSchema is already up to date."
            )

            print(
                "No changes were made to the database."
            )

            return

        # ---------------------------------------------------------
        # Schema changed
        # ---------------------------------------------------------

        print(
            "\nSchema changes detected."
        )

        print(
            "Resetting database schema..."
        )

        reset_database(
            configuration,
        )

        print(
            "Updated schema applied successfully."
        )

    finally:

        # ---------------------------------------------------------
        # Remove temporary database
        # ---------------------------------------------------------

        print(
            "\nRemoving temporary comparison database..."
        )

        drop_database(
            configuration,
            temporary_database,
        )

    print(
        "\nSAHA database is ready."
    )


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)