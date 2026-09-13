"""
SAHA - Database Initialization

Creates the SAHA PostgreSQL database if it does not already exist,
then initializes it using Database/schema.sql.

If the database already exists, its details are displayed and the
script exits without modifying the existing database.

Configuration is loaded from Database/.env.
"""

from pathlib import Path
import os
import sys

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


def find_project_root() -> Path:
    """
    Locate the SAHA project root.

    Expected structure:

    SAHA-AI/
    └── Database/
        ├── .env
        ├── schema.sql
        └── Scripts/
            └── start_schema.py
    """
    return Path(__file__).resolve().parents[2]


def load_configuration(project_root: Path) -> None:
    """Load PostgreSQL configuration from Database/.env."""
    env_file = project_root / "Database" / ".env"

    if not env_file.exists():
        raise FileNotFoundError(
            f"Environment file not found: {env_file}"
        )

    load_dotenv(env_file)


def get_configuration() -> dict:
    """Read and validate PostgreSQL configuration."""

    configuration = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

    required = (
        "database",
        "user",
        "password",
    )

    missing = [
        key
        for key in required
        if not configuration[key]
    ]

    if missing:
        raise RuntimeError(
            "Missing required PostgreSQL configuration: "
            + ", ".join(
                f"POSTGRES_{key.upper()}"
                for key in missing
            )
        )

    return configuration


def connect_to_server(configuration: dict):
    """
    Connect to the PostgreSQL server through the default
    'postgres' maintenance database.
    """
    return psycopg2.connect(
        host=configuration["host"],
        port=configuration["port"],
        dbname="postgres",
        user=configuration["user"],
        password=configuration["password"],
    )


def get_database_details(connection, database_name: str):
    """Return details for an existing PostgreSQL database."""

    query = """
        SELECT
            datname,
            pg_get_userbyid(datdba) AS owner,
            pg_encoding_to_char(encoding) AS encoding,
            datcollate,
            datctype,
            pg_size_pretty(pg_database_size(datname)) AS size,
            spcname AS tablespace
        FROM pg_database
        JOIN pg_tablespace
            ON pg_database.dattablespace = pg_tablespace.oid
        WHERE datname = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (database_name,))
        return cursor.fetchone()


def create_database(connection, database_name: str) -> None:
    """
    Create a PostgreSQL database.

    CREATE DATABASE cannot run inside a transaction, so autocommit
    is enabled for this operation.
    """

    connection.autocommit = True

    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(database_name)
            )
        )


def initialize_schema(configuration: dict, schema_file: Path) -> None:
    """Execute schema.sql against the newly created database."""

    schema_sql = schema_file.read_text(encoding="utf-8")

    if not schema_sql.strip():
        raise RuntimeError(
            f"Schema file is empty: {schema_file}"
        )

    connection = None

    try:
        connection = psycopg2.connect(
            host=configuration["host"],
            port=configuration["port"],
            dbname=configuration["database"],
            user=configuration["user"],
            password=configuration["password"],
        )

        with connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)

        print("Schema initialized successfully.")

    finally:
        if connection is not None:
            connection.close()


def main() -> None:
    project_root = find_project_root()

    load_configuration(project_root)

    configuration = get_configuration()

    database_name = configuration["database"]

    schema_file = project_root / "Database" / "schema.sql"

    if not schema_file.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_file}"
        )

    connection = None

    try:
        print(
            f"Checking PostgreSQL database '{database_name}'..."
        )

        connection = connect_to_server(configuration)

        database_details = get_database_details(
            connection,
            database_name,
        )

        # --------------------------------------------------------
        # Database already exists
        # --------------------------------------------------------

        if database_details:
            (
                name,
                owner,
                encoding,
                collation,
                ctype,
                size,
                tablespace,
            ) = database_details

            print("\nDatabase already exists.")
            print("----------------------------------------")
            print(f"Name       : {name}")
            print(f"Owner      : {owner}")
            print(f"Encoding   : {encoding}")
            print(f"Collation  : {collation}")
            print(f"CTYPE      : {ctype}")
            print(f"Size       : {size}")
            print(f"Tablespace : {tablespace}")
            print("----------------------------------------")
            print("No changes were made.")

            return

        # --------------------------------------------------------
        # Database does not exist
        # --------------------------------------------------------

        print(
            f"Database '{database_name}' does not exist."
        )

        print(
            f"Creating database '{database_name}'..."
        )

        create_database(
            connection,
            database_name,
        )

        print("Database created successfully.")

    except psycopg2.Error as exc:
        print(
            f"\nPostgreSQL error: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    finally:
        if connection is not None:
            connection.close()

    # ------------------------------------------------------------
    # Initialize newly created database
    # ------------------------------------------------------------

    try:
        print(
            f"Initializing schema from '{schema_file}'..."
        )

        initialize_schema(
            configuration,
            schema_file,
        )

        print(
            f"\nSAHA database '{database_name}' "
            "is ready."
        )

    except psycopg2.Error as exc:
        print(
            f"\nPostgreSQL error while initializing schema: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()