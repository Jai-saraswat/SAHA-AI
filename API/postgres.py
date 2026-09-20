import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from dotenv import load_dotenv


# =====================================================================
# PROJECT / ENVIRONMENT
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / "Database" / ".env"

load_dotenv(ENV_FILE)


# =====================================================================
# CONSTANTS
# =====================================================================

VALID_USER_ROLES = {
    "client",
    "therapist",
    "admin",
}

VALID_RELATIONSHIP_STATUSES = {
    "active",
    "paused",
    "ended",
}

VALID_CONVERSATION_STATUSES = {
    "active",
    "paused",
    "ended",
}

VALID_SENDER_TYPES = {
    "client",
    "therapist",
}


# =====================================================================
# INTERNAL HELPERS
# =====================================================================

def _now():
    """
    Return the current UTC timestamp.
    """
    return datetime.now(timezone.utc)


def _json(value: Any):
    """
    Convert a Python value into a psycopg2 JSON adapter.
    """
    return psycopg2.extras.Json(value)


def _stringify_uuid_fields(
    row: dict[str, Any],
    fields: tuple[str, ...],
):
    """
    Convert UUID fields returned by PostgreSQL into strings.
    """

    for field in fields:

        if row.get(field) is not None:
            row[field] = str(row[field])

    return row


def _stringify_rows(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
):
    """
    Convert UUID fields in multiple rows.
    """

    for row in rows:
        _stringify_uuid_fields(
            row,
            fields,
        )

    return rows


def _validate_non_empty(
    value: str,
    field_name: str,
):
    """
    Validate a required string identifier/value.
    """

    if value is None or not str(value).strip():
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    return str(value).strip()


# =====================================================================
# POSTGRESQL CONNECTION
# =====================================================================

def get_connection():
    """
    Create and return a PostgreSQL connection.
    """

    return psycopg2.connect(
        host=os.getenv(
            "POSTGRES_HOST",
            "localhost",
        ),
        port=os.getenv(
            "POSTGRES_PORT",
            "5432",
        ),
        database=os.getenv(
            "POSTGRES_DB",
        ),
        user=os.getenv(
            "POSTGRES_USER",
        ),
        password=os.getenv(
            "POSTGRES_PASSWORD",
        ),
    )


# =====================================================================
# GENERIC DATABASE EXECUTION
# =====================================================================

def execute_read_only(
    query: str,
    parameters: tuple | None = None,
):
    """
    Execute a PostgreSQL query inside a read-only transaction.

    Parameters are passed directly to psycopg2.

    This function MUST be used with parameterized SQL:

        execute_read_only(
            "SELECT ... WHERE user_id = %s",
            (user_id,),
        )
    """

    connection = get_connection()

    try:

        connection.set_session(
            readonly=True,
            autocommit=False,
        )

        with connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cursor:

            cursor.execute(
                query,
                parameters,
            )

            if cursor.description:
                result = [
                    dict(row)
                    for row in cursor.fetchall()
                ]
            else:
                result = []

        connection.rollback()

        return result

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


def execute_read_write(
    query: str,
    parameters: tuple | None = None,
):
    """
    Execute a PostgreSQL read/write query.

    The transaction is committed only after successful execution.

    Parameters are passed directly to psycopg2.
    """

    connection = get_connection()

    try:

        with connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cursor:

            cursor.execute(
                query,
                parameters,
            )

            if cursor.description:
                result = [
                    dict(row)
                    for row in cursor.fetchall()
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


# =====================================================================
# USERS
# =====================================================================

def generate_user_id(
    username: str,
    role: str | None = None,
    display_name: str | None = None,
    email: str | None = None,
):
    """
    Create a NEW user.

    IMPORTANT:
    This function no longer has the old "create-or-retrieve" API
    behavior.

    The public API layer should use:

        POST /api/v1/users

    If the username already exists, PostgreSQL raises a uniqueness
    error rather than silently returning the existing user.

    The name generate_user_id is retained for compatibility with
    existing internal imports.
    """

    username = _validate_non_empty(
        username,
        "Username",
    )

    if role is not None:

        role = role.strip().lower()

        if role not in VALID_USER_ROLES:
            raise ValueError(
                "role must be 'client', 'therapist', or 'admin'."
            )

    connection = get_connection()

    try:

        with connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cursor:

            cursor.execute(
                """
                INSERT INTO users (
                    username,
                    display_name,
                    email
                )
                VALUES (
                    %s,
                    %s,
                    %s
                )
                RETURNING
                    user_id,
                    username,
                    display_name,
                    email,
                    psychological_traits,
                    preferences,
                    metadata,
                    created_at,
                    updated_at,
                    deleted_at;
                """,
                (
                    username,
                    display_name,
                    email,
                ),
            )

            user = dict(
                cursor.fetchone()
            )

            user_id = user["user_id"]

            if role is not None:

                cursor.execute(
                    """
                    INSERT INTO user_roles (
                        user_id,
                        role
                    )
                    VALUES (
                        %s,
                        %s
                    )
                    RETURNING
                        user_id,
                        role,
                        created_at;
                    """,
                    (
                        user_id,
                        role,
                    ),
                )

                user_role = dict(
                    cursor.fetchone()
                )

            else:

                user_role = None

        connection.commit()

        user["user_id"] = str(
            user["user_id"]
        )

        return {
            "created": True,
            "user": user,
            "role": user_role,
        }

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


def get_user(
    user_id: str,
    include_deleted: bool = False,
):
    """
    Retrieve one user and their roles.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND u.deleted_at IS NULL"
    )

    query = f"""
    SELECT
        u.user_id,
        u.username,
        u.display_name,
        u.email,
        u.psychological_traits,
        u.preferences,
        u.metadata,
        u.created_at,
        u.updated_at,
        u.deleted_at,

        COALESCE(
            ARRAY_AGG(
                ur.role
                ORDER BY ur.role
            )
            FILTER (
                WHERE ur.role IS NOT NULL
            ),
            ARRAY[]::varchar[]
        ) AS roles

    FROM users u

    LEFT JOIN user_roles ur
        ON ur.user_id = u.user_id

    WHERE
        u.user_id = %s
        {deleted_condition}

    GROUP BY
        u.user_id,
        u.username,
        u.display_name,
        u.email,
        u.psychological_traits,
        u.preferences,
        u.metadata,
        u.created_at,
        u.updated_at,
        u.deleted_at;
    """

    result = execute_read_only(
        query,
        (user_id,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        ("user_id",),
    )


def get_user_by_username(
    username: str,
    include_deleted: bool = False,
):
    """
    Retrieve one user by username.
    """

    username = _validate_non_empty(
        username,
        "Username",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND u.deleted_at IS NULL"
    )

    query = f"""
    SELECT
        u.user_id,
        u.username,
        u.display_name,
        u.email,
        u.psychological_traits,
        u.preferences,
        u.metadata,
        u.created_at,
        u.updated_at,
        u.deleted_at,

        COALESCE(
            ARRAY_AGG(
                ur.role
                ORDER BY ur.role
            )
            FILTER (
                WHERE ur.role IS NOT NULL
            ),
            ARRAY[]::varchar[]
        ) AS roles

    FROM users u

    LEFT JOIN user_roles ur
        ON ur.user_id = u.user_id

    WHERE
        u.username = %s
        {deleted_condition}

    GROUP BY
        u.user_id,
        u.username,
        u.display_name,
        u.email,
        u.psychological_traits,
        u.preferences,
        u.metadata,
        u.created_at,
        u.updated_at,
        u.deleted_at;
    """

    result = execute_read_only(
        query,
        (username,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        ("user_id",),
    )


def update_user(
    user_id: str,
    username: str | None = None,
    display_name: str | None = None,
    email: str | None = None,
    metadata: dict | None = None,
):
    """
    Update editable user fields.

    user_id is immutable.

    psychological_traits and preferences are intentionally NOT
    modified here. They have their own dedicated memory/state API.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    fields = []
    parameters = []

    if username is not None:

        username = _validate_non_empty(
            username,
            "Username",
        )

        fields.append(
            "username = %s"
        )
        parameters.append(
            username
        )

    if display_name is not None:

        fields.append(
            "display_name = %s"
        )
        parameters.append(
            display_name
        )

    if email is not None:

        fields.append(
            "email = %s"
        )
        parameters.append(
            email
        )

    if metadata is not None:

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "metadata must be an object."
            )

        fields.append(
            "metadata = %s"
        )
        parameters.append(
            _json(metadata)
        )

    if not fields:
        raise ValueError(
            "No fields supplied for update."
        )

    fields.append(
        "updated_at = %s"
    )

    parameters.append(
        _now()
    )

    parameters.append(
        user_id
    )

    query = f"""
    UPDATE users
    SET
        {", ".join(fields)}

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        username,
        display_name,
        email,
        psychological_traits,
        preferences,
        metadata,
        created_at,
        updated_at,
        deleted_at;
    """

    result = execute_read_write(
        query,
        tuple(parameters),
    )

    return _stringify_rows(
        result,
        ("user_id",),
    )


def delete_user(
    user_id: str,
):
    """
    Soft-delete a user.

    Historical rows remain intact.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    deleted_at = _now()

    query = """
    UPDATE users
    SET
        deleted_at = %s,
        updated_at = %s

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        username,
        deleted_at;
    """

    result = execute_read_write(
        query,
        (
            deleted_at,
            deleted_at,
            user_id,
        ),
    )

    return _stringify_rows(
        result,
        ("user_id",),
    )


# =====================================================================
# USER ROLES
# =====================================================================

def add_user_role(
    user_id: str,
    role: str,
):
    """
    Add a role to an existing user.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    role = _validate_non_empty(
        role,
        "Role",
    ).lower()

    if role not in VALID_USER_ROLES:
        raise ValueError(
            "role must be 'client', 'therapist', or 'admin'."
        )

    user = get_user(
        user_id
    )

    if user is None:
        raise ValueError(
            "User not found."
        )

    query = """
    INSERT INTO user_roles (
        user_id,
        role
    )
    VALUES (
        %s,
        %s
    )
    ON CONFLICT (
        user_id,
        role
    )
    DO NOTHING

    RETURNING
        user_id,
        role,
        created_at;
    """

    result = execute_read_write(
        query,
        (
            user_id,
            role,
        ),
    )

    return _stringify_rows(
        result,
        ("user_id",),
    )


def remove_user_role(
    user_id: str,
    role: str,
):
    """
    Remove a role from a user.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    role = _validate_non_empty(
        role,
        "Role",
    ).lower()

    if role not in VALID_USER_ROLES:
        raise ValueError(
            "Invalid user role."
        )

    query = """
    DELETE FROM user_roles

    WHERE
        user_id = %s
        AND role = %s

    RETURNING
        user_id,
        role;
    """

    result = execute_read_write(
        query,
        (
            user_id,
            role,
        ),
    )

    return _stringify_rows(
        result,
        ("user_id",),
    )


# =====================================================================
# CLIENT / THERAPIST RELATIONSHIPS
# =====================================================================

def link_users(
    client_user_id: str,
    therapist_user_id: str,
):
    """
    Create a client-therapist relationship.

    If the same non-deleted relationship already exists, the existing
    relationship is returned rather than creating a duplicate.

    This function is retained under the internal name link_users;
    the public API resource is /api/v1/relationships.
    """

    client_user_id = _validate_non_empty(
        client_user_id,
        "Client user ID",
    )

    therapist_user_id = _validate_non_empty(
        therapist_user_id,
        "Therapist user ID",
    )

    if client_user_id == therapist_user_id:
        raise ValueError(
            "Client and therapist must be different users."
        )

    connection = get_connection()

    try:

        with connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cursor:

            # ---------------------------------------------------------
            # Verify users
            # ---------------------------------------------------------

            cursor.execute(
                """
                SELECT
                    user_id,
                    deleted_at
                FROM users
                WHERE user_id IN (%s, %s);
                """,
                (
                    client_user_id,
                    therapist_user_id,
                ),
            )

            users = cursor.fetchall()

            if len(users) != 2:
                raise ValueError(
                    "Both client and therapist users must exist."
                )

            for user in users:

                if user["deleted_at"] is not None:
                    raise ValueError(
                        "Deleted users cannot be linked."
                    )

            # ---------------------------------------------------------
            # Verify roles
            # ---------------------------------------------------------

            cursor.execute(
                """
                SELECT
                    user_id,
                    role
                FROM user_roles
                WHERE
                    user_id IN (%s, %s)
                    AND role IN ('client', 'therapist');
                """,
                (
                    client_user_id,
                    therapist_user_id,
                ),
            )

            roles = cursor.fetchall()

            role_map = {}

            for row in roles:

                role_map.setdefault(
                    str(row["user_id"]),
                    set(),
                ).add(
                    row["role"]
                )

            if "client" not in role_map.get(
                client_user_id,
                set(),
            ):
                raise ValueError(
                    "Client user does not have the 'client' role."
                )

            if "therapist" not in role_map.get(
                therapist_user_id,
                set(),
            ):
                raise ValueError(
                    "Therapist user does not have the 'therapist' role."
                )

            # ---------------------------------------------------------
            # Existing relationship
            # ---------------------------------------------------------

            cursor.execute(
                """
                SELECT
                    relationship_id,
                    client_user_id,
                    therapist_user_id,
                    status,
                    started_at,
                    ended_at,
                    metadata,
                    created_at,
                    updated_at,
                    deleted_at
                FROM user_relationships
                WHERE
                    client_user_id = %s
                    AND therapist_user_id = %s
                    AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (
                    client_user_id,
                    therapist_user_id,
                ),
            )

            existing = cursor.fetchone()

            if existing:

                relationship = dict(
                    existing
                )

                connection.commit()

                _stringify_uuid_fields(
                    relationship,
                    (
                        "relationship_id",
                        "client_user_id",
                        "therapist_user_id",
                    ),
                )

                relationship["created"] = False

                return relationship

            # ---------------------------------------------------------
            # Create relationship
            # ---------------------------------------------------------

            cursor.execute(
                """
                INSERT INTO user_relationships (
                    client_user_id,
                    therapist_user_id,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    'active'
                )

                RETURNING
                    relationship_id,
                    client_user_id,
                    therapist_user_id,
                    status,
                    started_at,
                    ended_at,
                    metadata,
                    created_at,
                    updated_at,
                    deleted_at;
                """,
                (
                    client_user_id,
                    therapist_user_id,
                ),
            )

            relationship = dict(
                cursor.fetchone()
            )

        connection.commit()

        _stringify_uuid_fields(
            relationship,
            (
                "relationship_id",
                "client_user_id",
                "therapist_user_id",
            ),
        )

        relationship["created"] = True

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()

    # -------------------------------------------------------------
    # Create default AI settings
    # -------------------------------------------------------------

    initialize_relationship_ai_settings(
        relationship["relationship_id"]
    )

    return relationship


def get_relationship(
    relationship_id: str,
    include_deleted: bool = False,
):
    """
    Retrieve one client-therapist relationship.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND r.deleted_at IS NULL"
    )

    query = f"""
    SELECT
        r.relationship_id,

        r.client_user_id,
        client.username AS client_username,
        client.display_name AS client_display_name,

        r.therapist_user_id,
        therapist.username AS therapist_username,
        therapist.display_name AS therapist_display_name,

        r.status,
        r.started_at,
        r.ended_at,
        r.metadata,
        r.created_at,
        r.updated_at,
        r.deleted_at

    FROM user_relationships r

    INNER JOIN users client
        ON client.user_id = r.client_user_id

    INNER JOIN users therapist
        ON therapist.user_id = r.therapist_user_id

    WHERE
        r.relationship_id = %s
        {deleted_condition};
    """

    result = execute_read_only(
        query,
        (relationship_id,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        (
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )


def get_user_relationships(
    user_id: str,
):
    """
    Retrieve all relationships involving a user.
    """

    user_id = _validate_non_empty(
        user_id,
        "User ID",
    )

    query = """
    SELECT
        r.relationship_id,

        r.client_user_id,
        client.username AS client_username,
        client.display_name AS client_display_name,

        r.therapist_user_id,
        therapist.username AS therapist_username,
        therapist.display_name AS therapist_display_name,

        r.status,
        r.started_at,
        r.ended_at,
        r.metadata,
        r.created_at,
        r.updated_at,
        r.deleted_at

    FROM user_relationships r

    INNER JOIN users client
        ON client.user_id = r.client_user_id

    INNER JOIN users therapist
        ON therapist.user_id = r.therapist_user_id

    WHERE
        (
            r.client_user_id = %s
            OR r.therapist_user_id = %s
        )
        AND r.deleted_at IS NULL

    ORDER BY
        r.updated_at DESC;
    """

    result = execute_read_only(
        query,
        (
            user_id,
            user_id,
        ),
    )

    return _stringify_rows(
        result,
        (
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )


def update_relationship(
    relationship_id: str,
    status: str | None = None,
    metadata: dict | None = None,
):
    """
    Update relationship-level fields.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    fields = []
    parameters = []

    if status is not None:

        status = _validate_non_empty(
            status,
            "Status",
        ).lower()

        if status not in VALID_RELATIONSHIP_STATUSES:
            raise ValueError(
                "Invalid relationship status."
            )

        fields.append(
            "status = %s"
        )

        parameters.append(
            status
        )

    if metadata is not None:

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "metadata must be an object."
            )

        fields.append(
            "metadata = %s"
        )

        parameters.append(
            _json(metadata)
        )

    if not fields:
        raise ValueError(
            "No fields supplied for update."
        )

    fields.append(
        "updated_at = %s"
    )

    parameters.append(
        _now()
    )

    parameters.append(
        relationship_id
    )

    query = f"""
    UPDATE user_relationships
    SET
        {", ".join(fields)}

    WHERE
        relationship_id = %s
        AND deleted_at IS NULL

    RETURNING
        relationship_id,
        client_user_id,
        therapist_user_id,
        status,
        started_at,
        ended_at,
        metadata,
        created_at,
        updated_at,
        deleted_at;
    """

    result = execute_read_write(
        query,
        tuple(parameters),
    )

    return _stringify_rows(
        result,
        (
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )


def end_relationship(
    relationship_id: str,
):
    """
    End an active relationship.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    now = _now()

    query = """
    UPDATE user_relationships

    SET
        status = 'ended',
        ended_at = %s,
        updated_at = %s

    WHERE
        relationship_id = %s
        AND deleted_at IS NULL
        AND status <> 'ended'

    RETURNING
        relationship_id,
        client_user_id,
        therapist_user_id,
        status,
        started_at,
        ended_at,
        metadata,
        created_at,
        updated_at,
        deleted_at;
    """

    result = execute_read_write(
        query,
        (
            now,
            now,
            relationship_id,
        ),
    )

    return _stringify_rows(
        result,
        (
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )


def delete_relationship(
    relationship_id: str,
):
    """
    Soft-delete a relationship.

    Historical conversations remain intact.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    now = _now()

    query = """
    UPDATE user_relationships

    SET
        deleted_at = %s,
        updated_at = %s

    WHERE
        relationship_id = %s
        AND deleted_at IS NULL

    RETURNING
        relationship_id,
        deleted_at;
    """

    result = execute_read_write(
        query,
        (
            now,
            now,
            relationship_id,
        ),
    )

    return _stringify_rows(
        result,
        ("relationship_id",),
    )


# =====================================================================
# RELATIONSHIP AI SETTINGS
# =====================================================================

def initialize_relationship_ai_settings(
    relationship_id: str,
):
    """
    Create the default AI configuration for a relationship.

    Existing configuration is preserved.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    query = """
    INSERT INTO relationship_ai_settings (
        relationship_id
    )
    VALUES (
        %s
    )

    ON CONFLICT (
        relationship_id
    )
    DO NOTHING

    RETURNING
        relationship_id,
        ai_enabled,
        analysis_enabled,
        memory_enabled,
        strategy_planner_enabled,
        therapist_assistance_enabled,
        client_response_generation_enabled,
        real_time_analysis_enabled,
        post_conversation_analysis_enabled,
        allowed_data_sources,
        restricted_data_sources,
        allowed_capabilities,
        restricted_capabilities,
        strategy_constraints,
        custom_instructions,
        configuration,
        created_at,
        updated_at;
    """

    result = execute_read_write(
        query,
        (relationship_id,),
    )

    if result:
        return _stringify_rows(
            result,
            ("relationship_id",),
        )[0]

    return get_relationship_ai_settings(
        relationship_id
    )


def get_relationship_ai_settings(
    relationship_id: str,
):
    """
    Retrieve relationship-level AI settings.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    query = """
    SELECT
        relationship_id,
        ai_enabled,
        analysis_enabled,
        memory_enabled,
        strategy_planner_enabled,
        therapist_assistance_enabled,
        client_response_generation_enabled,
        real_time_analysis_enabled,
        post_conversation_analysis_enabled,
        allowed_data_sources,
        restricted_data_sources,
        allowed_capabilities,
        restricted_capabilities,
        strategy_constraints,
        custom_instructions,
        configuration,
        created_at,
        updated_at

    FROM relationship_ai_settings

    WHERE relationship_id = %s;
    """

    result = execute_read_only(
        query,
        (relationship_id,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        ("relationship_id",),
    )


def update_relationship_ai_settings(
    relationship_id: str,
    ai_enabled: bool | None = None,
    analysis_enabled: bool | None = None,
    memory_enabled: bool | None = None,
    strategy_planner_enabled: bool | None = None,
    therapist_assistance_enabled: bool | None = None,
    client_response_generation_enabled: bool | None = None,
    real_time_analysis_enabled: bool | None = None,
    post_conversation_analysis_enabled: bool | None = None,
    allowed_data_sources: list | None = None,
    restricted_data_sources: list | None = None,
    allowed_capabilities: list | None = None,
    restricted_capabilities: list | None = None,
    strategy_constraints: dict | None = None,
    custom_instructions: str | None = None,
    configuration: dict | None = None,
):
    """
    Update relationship-level AI settings.

    Only supplied fields are changed.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    # -------------------------------------------------------------
    # Ensure the settings row exists.
    # -------------------------------------------------------------

    initialize_relationship_ai_settings(
        relationship_id
    )

    fields = []
    parameters = []

    boolean_fields = {
        "ai_enabled": ai_enabled,
        "analysis_enabled": analysis_enabled,
        "memory_enabled": memory_enabled,
        "strategy_planner_enabled": strategy_planner_enabled,
        "therapist_assistance_enabled": therapist_assistance_enabled,
        "client_response_generation_enabled": (
            client_response_generation_enabled
        ),
        "real_time_analysis_enabled": (
            real_time_analysis_enabled
        ),
        "post_conversation_analysis_enabled": (
            post_conversation_analysis_enabled
        ),
    }

    for field_name, value in boolean_fields.items():

        if value is not None:

            fields.append(
                f"{field_name} = %s"
            )

            parameters.append(
                value
            )

    json_array_fields = {
        "allowed_data_sources": allowed_data_sources,
        "restricted_data_sources": restricted_data_sources,
        "allowed_capabilities": allowed_capabilities,
        "restricted_capabilities": restricted_capabilities,
    }

    for field_name, value in json_array_fields.items():

        if value is not None:

            if not isinstance(
                value,
                list,
            ):
                raise ValueError(
                    f"{field_name} must be an array."
                )

            fields.append(
                f"{field_name} = %s"
            )

            parameters.append(
                _json(value)
            )

    json_object_fields = {
        "strategy_constraints": strategy_constraints,
        "configuration": configuration,
    }

    for field_name, value in json_object_fields.items():

        if value is not None:

            if not isinstance(
                value,
                dict,
            ):
                raise ValueError(
                    f"{field_name} must be an object."
                )

            fields.append(
                f"{field_name} = %s"
            )

            parameters.append(
                _json(value)
            )

    if custom_instructions is not None:

        fields.append(
            "custom_instructions = %s"
        )

        parameters.append(
            custom_instructions
        )

    if not fields:
        raise ValueError(
            "No fields supplied for AI settings update."
        )

    fields.append(
        "updated_at = %s"
    )

    parameters.append(
        _now()
    )

    parameters.append(
        relationship_id
    )

    query = f"""
    UPDATE relationship_ai_settings

    SET
        {", ".join(fields)}

    WHERE
        relationship_id = %s

    RETURNING
        relationship_id,
        ai_enabled,
        analysis_enabled,
        memory_enabled,
        strategy_planner_enabled,
        therapist_assistance_enabled,
        client_response_generation_enabled,
        real_time_analysis_enabled,
        post_conversation_analysis_enabled,
        allowed_data_sources,
        restricted_data_sources,
        allowed_capabilities,
        restricted_capabilities,
        strategy_constraints,
        custom_instructions,
        configuration,
        created_at,
        updated_at;
    """

    result = execute_read_write(
        query,
        tuple(parameters),
    )

    return _stringify_rows(
        result,
        ("relationship_id",),
    )


# =====================================================================
# CONVERSATIONS
# =====================================================================

def get_conversation(
    conversation_id: str,
    include_deleted: bool = False,
):
    """
    Retrieve a conversation and its relationship participants.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND c.deleted_at IS NULL"
    )

    query = f"""
    SELECT
        c.conversation_id,
        c.relationship_id,

        r.client_user_id,
        client.username AS client_username,
        client.display_name AS client_display_name,

        r.therapist_user_id,
        therapist.username AS therapist_username,
        therapist.display_name AS therapist_display_name,

        c.topic,
        c.status,
        c.started_at,
        c.ended_at,
        c.metadata,
        c.created_at,
        c.updated_at,
        c.deleted_at

    FROM conversations c

    INNER JOIN user_relationships r
        ON r.relationship_id = c.relationship_id

    INNER JOIN users client
        ON client.user_id = r.client_user_id

    INNER JOIN users therapist
        ON therapist.user_id = r.therapist_user_id

    WHERE
        c.conversation_id = %s
        {deleted_condition};
    """

    result = execute_read_only(
        query,
        (conversation_id,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        (
            "conversation_id",
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )


def update_conversation(
    conversation_id: str,
    topic: str | None = None,
    status: str | None = None,
    metadata: dict | None = None,
):
    """
    Update conversation fields.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    fields = []
    parameters = []

    if topic is not None:

        fields.append(
            "topic = %s"
        )

        parameters.append(
            topic
        )

    if status is not None:

        status = _validate_non_empty(
            status,
            "Status",
        ).lower()

        if status not in VALID_CONVERSATION_STATUSES:
            raise ValueError(
                "Invalid conversation status."
            )

        fields.append(
            "status = %s"
        )

        parameters.append(
            status
        )

        if status == "ended":

            fields.append(
                "ended_at = %s"
            )

            parameters.append(
                _now()
            )

    if metadata is not None:

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "metadata must be an object."
            )

        fields.append(
            "metadata = %s"
        )

        parameters.append(
            _json(metadata)
        )

    if not fields:
        raise ValueError(
            "No fields supplied for conversation update."
        )

    fields.append(
        "updated_at = %s"
    )

    parameters.append(
        _now()
    )

    parameters.append(
        conversation_id
    )

    query = f"""
    UPDATE conversations

    SET
        {", ".join(fields)}

    WHERE
        conversation_id = %s
        AND deleted_at IS NULL

    RETURNING
        conversation_id,
        relationship_id,
        topic,
        status,
        started_at,
        ended_at,
        metadata,
        created_at,
        updated_at,
        deleted_at;
    """

    result = execute_read_write(
        query,
        tuple(parameters),
    )

    return _stringify_rows(
        result,
        (
            "conversation_id",
            "relationship_id",
        ),
    )


def delete_conversation(
    conversation_id: str,
):
    """
    Soft-delete a conversation.

    Messages are retained for historical integrity.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    now = _now()

    query = """
    UPDATE conversations

    SET
        deleted_at = %s,
        updated_at = %s

    WHERE
        conversation_id = %s
        AND deleted_at IS NULL

    RETURNING
        conversation_id,
        deleted_at;
    """

    result = execute_read_write(
        query,
        (
            now,
            now,
            conversation_id,
        ),
    )

    return _stringify_rows(
        result,
        ("conversation_id",),
    )


def get_relationship_conversations(
    relationship_id: str,
    include_deleted: bool = False,
):
    """
    Retrieve conversations belonging to a therapeutic relationship.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND deleted_at IS NULL"
    )

    query = f"""
    SELECT
        conversation_id,
        relationship_id,
        topic,
        status,
        started_at,
        ended_at,
        metadata,
        created_at,
        updated_at,
        deleted_at

    FROM conversations

    WHERE
        relationship_id = %s
        {deleted_condition}

    ORDER BY
        updated_at DESC;
    """

    result = execute_read_only(
        query,
        (relationship_id,),
    )

    return _stringify_rows(
        result,
        (
            "conversation_id",
            "relationship_id",
        ),
    )


# =====================================================================
# CONVERSATION MESSAGES
# =====================================================================

def get_message(
    message_id: str,
    include_deleted: bool = False,
):
    """
    Retrieve one conversation message.
    """

    message_id = _validate_non_empty(
        message_id,
        "Message ID",
    )

    deleted_condition = (
        ""
        if include_deleted
        else "AND deleted_at IS NULL"
    )

    query = f"""
    SELECT
        message_id,
        conversation_id,
        sender_user_id,
        sender_type,
        content,
        sequence_number,
        occurred_at,
        created_at,
        edited_at,
        deleted_at,
        metadata

    FROM conversation_messages

    WHERE
        message_id = %s
        {deleted_condition};
    """

    result = execute_read_only(
        query,
        (message_id,),
    )

    if not result:
        return None

    return _stringify_uuid_fields(
        result[0],
        (
            "message_id",
            "conversation_id",
            "sender_user_id",
        ),
    )


def edit_message(
    message_id: str,
    content: str,
):
    """
    Edit message content.

    Sender identity, sender type, conversation and sequence number
    remain immutable.
    """

    message_id = _validate_non_empty(
        message_id,
        "Message ID",
    )

    content = _validate_non_empty(
        content,
        "Message content",
    )

    edited_at = _now()

    query = """
    UPDATE conversation_messages

    SET
        content = %s,
        edited_at = %s

    WHERE
        message_id = %s
        AND deleted_at IS NULL

    RETURNING
        message_id,
        conversation_id,
        sender_user_id,
        sender_type,
        content,
        sequence_number,
        occurred_at,
        created_at,
        edited_at,
        deleted_at,
        metadata;
    """

    result = execute_read_write(
        query,
        (
            content,
            edited_at,
            message_id,
        ),
    )

    return _stringify_rows(
        result,
        (
            "message_id",
            "conversation_id",
            "sender_user_id",
        ),
    )


def delete_message(
    message_id: str,
):
    """
    Soft-delete a conversation message.
    """

    message_id = _validate_non_empty(
        message_id,
        "Message ID",
    )

    deleted_at = _now()

    query = """
    UPDATE conversation_messages

    SET
        deleted_at = %s

    WHERE
        message_id = %s
        AND deleted_at IS NULL

    RETURNING
        message_id,
        conversation_id,
        deleted_at;
    """

    result = execute_read_write(
        query,
        (
            deleted_at,
            message_id,
        ),
    )

    return _stringify_rows(
        result,
        (
            "message_id",
            "conversation_id",
        ),
    )


# =====================================================================
# GRAPHITI MESSAGE BUFFER
# =====================================================================

def initialize_graphiti_buffer(
    conversation_id: str,
):
    """
    Create an empty Graphiti message buffer for a conversation.

    There is exactly one buffer per conversation.

    IMPORTANT:
    The new schema intentionally does NOT store user_id here.
    The conversation already identifies the therapeutic relationship.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    query = """
    INSERT INTO graphiti_message_buffer (
        conversation_id,
        messages,
        updated_at
    )

    VALUES (
        %s,
        '[]'::jsonb,
        NOW()
    )

    ON CONFLICT (
        conversation_id
    )
    DO NOTHING

    RETURNING
        conversation_id,
        messages,
        updated_at;
    """

    result = execute_read_write(
        query,
        (conversation_id,),
    )

    if not result:

        query = """
        SELECT
            conversation_id,
            messages,
            updated_at

        FROM graphiti_message_buffer

        WHERE conversation_id = %s;
        """

        result = execute_read_only(
            query,
            (conversation_id,),
        )

    if not result:

        raise RuntimeError(
            "Failed to initialize Graphiti message buffer."
        )

    buffer = result[0]

    buffer["conversation_id"] = str(
        buffer["conversation_id"]
    )

    buffer["message_count"] = len(
        buffer["messages"]
    )

    return buffer


def get_graphiti_buffer(
    conversation_id: str,
):
    """
    Retrieve the current Graphiti message buffer.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    query = """
    SELECT
        conversation_id,
        messages,
        updated_at

    FROM graphiti_message_buffer

    WHERE conversation_id = %s;
    """

    result = execute_read_only(
        query,
        (conversation_id,),
    )

    if not result:
        return None

    buffer = result[0]

    buffer["conversation_id"] = str(
        buffer["conversation_id"]
    )

    buffer["message_count"] = len(
        buffer["messages"]
    )

    return buffer


def add_graphiti_buffer_message(
    conversation_id: str,
    message: dict[str, Any],
):
    """
    Append one message to the conversation's Graphiti buffer.

    This function only manages the PostgreSQL buffer.
    It does NOT call Graphiti.

    Graphiti ingestion remains a separate workflow.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    if not isinstance(
        message,
        dict,
    ):
        raise ValueError(
            "message must be an object."
        )

    content = message.get(
        "content"
    )

    if content is None or not str(
        content
    ).strip():

        raise ValueError(
            "Buffered message content cannot be empty."
        )

    query = """
    INSERT INTO graphiti_message_buffer (
        conversation_id,
        messages,
        updated_at
    )

    VALUES (
        %s,
        %s,
        NOW()
    )

    ON CONFLICT (
        conversation_id
    )

    DO UPDATE SET
        messages = (
            graphiti_message_buffer.messages
            || EXCLUDED.messages
        ),
        updated_at = NOW()

    RETURNING
        conversation_id,
        messages,
        updated_at;
    """

    result = execute_read_write(
        query,
        (
            conversation_id,
            _json([message]),
        ),
    )

    if not result:
        raise RuntimeError(
            "Failed to append message to Graphiti buffer."
        )

    buffer = result[0]

    buffer["conversation_id"] = str(
        buffer["conversation_id"]
    )

    buffer["message_count"] = len(
        buffer["messages"]
    )

    return buffer


def clear_graphiti_buffer(
    conversation_id: str,
):
    """
    Clear all messages from a conversation's Graphiti buffer.

    The buffer row itself is retained.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    query = """
    UPDATE graphiti_message_buffer

    SET
        messages = '[]'::jsonb,
        updated_at = NOW()

    WHERE
        conversation_id = %s

    RETURNING
        conversation_id,
        messages,
        updated_at;
    """

    result = execute_read_write(
        query,
        (conversation_id,),
    )

    if not result:

        return {
            "conversation_id": conversation_id,
            "messages": [],
            "message_count": 0,
            "cleared": False,
        }

    buffer = result[0]

    buffer["conversation_id"] = str(
        buffer["conversation_id"]
    )

    buffer["message_count"] = 0
    buffer["cleared"] = True

    return buffer


def delete_graphiti_buffer(
    conversation_id: str,
):
    """
    Delete the Graphiti buffer row for a conversation.

    Normally clearing the buffer is preferable because the row is
    infrastructure associated with the conversation.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    query = """
    DELETE FROM graphiti_message_buffer

    WHERE conversation_id = %s

    RETURNING
        conversation_id;
    """

    result = execute_read_write(
        query,
        (conversation_id,),
    )

    return _stringify_rows(
        result,
        ("conversation_id",),
    )


# =====================================================================
# EVALUATION / ADMIN OVERVIEW
# =====================================================================

def get_users_overview(
    include_deleted: bool = False,
):
    """
    Return a structured overview of users.

    Includes:

        - identity
        - roles
        - relationship count
        - conversation count
        - message count
        - first conversation
        - last activity
        - latest conversation

    This function is intended for evaluation/admin inspection.
    """

    deleted_condition = (
        ""
        if include_deleted
        else "WHERE u.deleted_at IS NULL"
    )

    query = f"""
    WITH relationship_counts AS (

        SELECT
            user_id,
            COUNT(*) AS relationship_count

        FROM (

            SELECT client_user_id AS user_id
            FROM user_relationships
            WHERE deleted_at IS NULL

            UNION ALL

            SELECT therapist_user_id AS user_id
            FROM user_relationships
            WHERE deleted_at IS NULL

        ) relationship_users

        GROUP BY user_id
    ),

    conversation_stats AS (

        SELECT
            r.client_user_id AS user_id,

            COUNT(DISTINCT c.conversation_id)
                AS conversation_count,

            MIN(c.started_at)
                AS first_conversation_at,

            MAX(
                GREATEST(
                    COALESCE(
                        c.updated_at,
                        c.created_at
                    ),
                    COALESCE(
                        c.ended_at,
                        c.updated_at,
                        c.created_at
                    )
                )
            ) AS last_conversation_activity

        FROM user_relationships r

        INNER JOIN conversations c
            ON c.relationship_id = r.relationship_id

        WHERE
            r.deleted_at IS NULL
            AND c.deleted_at IS NULL

        GROUP BY
            r.client_user_id

        UNION ALL

        SELECT
            r.therapist_user_id AS user_id,

            COUNT(DISTINCT c.conversation_id)
                AS conversation_count,

            MIN(c.started_at)
                AS first_conversation_at,

            MAX(
                GREATEST(
                    COALESCE(
                        c.updated_at,
                        c.created_at
                    ),
                    COALESCE(
                        c.ended_at,
                        c.updated_at,
                        c.created_at
                    )
                )
            ) AS last_conversation_activity

        FROM user_relationships r

        INNER JOIN conversations c
            ON c.relationship_id = r.relationship_id

        WHERE
            r.deleted_at IS NULL
            AND c.deleted_at IS NULL

        GROUP BY
            r.therapist_user_id
    ),

    conversation_aggregate AS (

        SELECT
            user_id,
            SUM(conversation_count)
                AS conversation_count,

            MIN(first_conversation_at)
                AS first_conversation_at,

            MAX(last_conversation_activity)
                AS last_conversation_activity

        FROM conversation_stats

        GROUP BY user_id
    ),

    message_counts AS (

        SELECT
            r_user.user_id,
            COUNT(cm.message_id)
                AS message_count

        FROM (

            SELECT
                r.client_user_id AS user_id,
                c.conversation_id

            FROM user_relationships r

            INNER JOIN conversations c
                ON c.relationship_id = r.relationship_id

            WHERE
                r.deleted_at IS NULL
                AND c.deleted_at IS NULL

            UNION

            SELECT
                r.therapist_user_id AS user_id,
                c.conversation_id

            FROM user_relationships r

            INNER JOIN conversations c
                ON c.relationship_id = r.relationship_id

            WHERE
                r.deleted_at IS NULL
                AND c.deleted_at IS NULL

        ) r_user

        INNER JOIN conversation_messages cm
            ON cm.conversation_id =
               r_user.conversation_id

        WHERE
            cm.deleted_at IS NULL

        GROUP BY
            r_user.user_id
    ),

    latest_conversation AS (

        SELECT DISTINCT ON (
            r_user.user_id
        )

            r_user.user_id,

            c.conversation_id,
            c.topic,
            c.started_at,
            c.updated_at

        FROM (

            SELECT
                r.client_user_id AS user_id,
                c.conversation_id

            FROM user_relationships r

            INNER JOIN conversations c
                ON c.relationship_id = r.relationship_id

            WHERE
                r.deleted_at IS NULL
                AND c.deleted_at IS NULL

            UNION

            SELECT
                r.therapist_user_id AS user_id,
                c.conversation_id

            FROM user_relationships r

            INNER JOIN conversations c
                ON c.relationship_id = r.relationship_id

            WHERE
                r.deleted_at IS NULL
                AND c.deleted_at IS NULL

        ) r_user

        INNER JOIN conversations c
            ON c.conversation_id =
               r_user.conversation_id

        ORDER BY
            r_user.user_id,
            c.updated_at DESC
    )

    SELECT
        u.user_id,
        u.username,
        u.display_name,
        u.email,

        COALESCE(
            ARRAY_AGG(
                DISTINCT ur.role
            )
            FILTER (
                WHERE ur.role IS NOT NULL
            ),
            ARRAY[]::varchar[]
        ) AS roles,

        COALESCE(
            rc.relationship_count,
            0
        ) AS relationship_count,

        COALESCE(
            ca.conversation_count,
            0
        ) AS conversation_count,

        COALESCE(
            mc.message_count,
            0
        ) AS message_count,

        ca.first_conversation_at,

        ca.last_conversation_activity
            AS last_activity_at,

        lc.conversation_id
            AS latest_conversation_id,

        lc.topic
            AS latest_conversation_topic,

        lc.started_at
            AS latest_conversation_started_at,

        lc.updated_at
            AS latest_conversation_updated_at,

        u.created_at,
        u.updated_at,
        u.deleted_at

    FROM users u

    LEFT JOIN user_roles ur
        ON ur.user_id = u.user_id

    LEFT JOIN relationship_counts rc
        ON rc.user_id = u.user_id

    LEFT JOIN conversation_aggregate ca
        ON ca.user_id = u.user_id

    LEFT JOIN message_counts mc
        ON mc.user_id = u.user_id

    LEFT JOIN latest_conversation lc
        ON lc.user_id = u.user_id

    {deleted_condition}

    GROUP BY
        u.user_id,
        u.username,
        u.display_name,
        u.email,
        u.created_at,
        u.updated_at,
        u.deleted_at,
        rc.relationship_count,
        ca.conversation_count,
        ca.first_conversation_at,
        ca.last_conversation_activity,
        mc.message_count,
        lc.conversation_id,
        lc.topic,
        lc.started_at,
        lc.updated_at

    ORDER BY
        ca.last_conversation_activity DESC NULLS LAST,
        u.created_at DESC;
    """

    result = execute_read_only(
        query
    )

    return _stringify_rows(
        result,
        ("user_id", "latest_conversation_id"),
    )


# =====================================================================
# EVALUATION: RELATIONSHIP
# =====================================================================

def get_relationship_overview(
    relationship_id: str,
):
    """
    Return relationship details plus conversation/message counts.
    """

    relationship_id = _validate_non_empty(
        relationship_id,
        "Relationship ID",
    )

    query = """
    SELECT
        r.relationship_id,

        r.client_user_id,
        client.username AS client_username,
        client.display_name AS client_display_name,

        r.therapist_user_id,
        therapist.username AS therapist_username,
        therapist.display_name AS therapist_display_name,

        r.status,
        r.started_at,
        r.ended_at,
        r.metadata,
        r.created_at,
        r.updated_at,
        r.deleted_at,

        COUNT(
            DISTINCT c.conversation_id
        ) AS conversation_count,

        COUNT(
            DISTINCT cm.message_id
        ) AS message_count

    FROM user_relationships r

    INNER JOIN users client
        ON client.user_id =
           r.client_user_id

    INNER JOIN users therapist
        ON therapist.user_id =
           r.therapist_user_id

    LEFT JOIN conversations c
        ON c.relationship_id =
           r.relationship_id
        AND c.deleted_at IS NULL

    LEFT JOIN conversation_messages cm
        ON cm.conversation_id =
           c.conversation_id
        AND cm.deleted_at IS NULL

    WHERE
        r.relationship_id = %s

    GROUP BY
        r.relationship_id,
        r.client_user_id,
        client.username,
        client.display_name,
        r.therapist_user_id,
        therapist.username,
        therapist.display_name,
        r.status,
        r.started_at,
        r.ended_at,
        r.metadata,
        r.created_at,
        r.updated_at,
        r.deleted_at;
    """

    result = execute_read_only(
        query,
        (relationship_id,),
    )

    if not result:
        return None

    result = _stringify_rows(
        result,
        (
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )

    result[0]["conversation_count"] = int(
        result[0]["conversation_count"]
        or 0
    )

    result[0]["message_count"] = int(
        result[0]["message_count"]
        or 0
    )

    return result[0]


# =====================================================================
# EVALUATION: CONVERSATION
# =====================================================================

def get_conversation_overview(
    conversation_id: str,
):
    """
    Return conversation details and message statistics.
    """

    conversation_id = _validate_non_empty(
        conversation_id,
        "Conversation ID",
    )

    query = """
    SELECT
        c.conversation_id,
        c.relationship_id,

        r.client_user_id,
        r.therapist_user_id,

        c.topic,
        c.status,
        c.started_at,
        c.ended_at,
        c.metadata,
        c.created_at,
        c.updated_at,
        c.deleted_at,

        COUNT(
            cm.message_id
        ) FILTER (
            WHERE cm.deleted_at IS NULL
        ) AS message_count,

        COUNT(
            cm.message_id
        ) FILTER (
            WHERE
                cm.sender_type = 'client'
                AND cm.deleted_at IS NULL
        ) AS client_message_count,

        COUNT(
            cm.message_id
        ) FILTER (
            WHERE
                cm.sender_type = 'therapist'
                AND cm.deleted_at IS NULL
        ) AS therapist_message_count

    FROM conversations c

    INNER JOIN user_relationships r
        ON r.relationship_id =
           c.relationship_id

    LEFT JOIN conversation_messages cm
        ON cm.conversation_id =
           c.conversation_id

    WHERE
        c.conversation_id = %s

    GROUP BY
        c.conversation_id,
        c.relationship_id,
        r.client_user_id,
        r.therapist_user_id,
        c.topic,
        c.status,
        c.started_at,
        c.ended_at,
        c.metadata,
        c.created_at,
        c.updated_at,
        c.deleted_at;
    """

    result = execute_read_only(
        query,
        (conversation_id,),
    )

    if not result:
        return None

    result = _stringify_rows(
        result,
        (
            "conversation_id",
            "relationship_id",
            "client_user_id",
            "therapist_user_id",
        ),
    )

    result[0]["message_count"] = int(
        result[0]["message_count"]
        or 0
    )

    result[0]["client_message_count"] = int(
        result[0]["client_message_count"]
        or 0
    )

    result[0]["therapist_message_count"] = int(
        result[0]["therapist_message_count"]
        or 0
    )

    return result[0]