from typing import Any

from API.postgres import (
    execute_read_only,
    execute_read_write,
    get_user,
)


# =====================================================================
# CONSTANTS
# =====================================================================

EMPTY_TRAITS = {
    "facts": []
}

EMPTY_PREFERENCES = {
    "items": []
}


# =====================================================================
# INTERNAL VALIDATION HELPERS
# =====================================================================

def _validate_user_id(
    user_id: str,
):
    """
    Validate user ID.
    """

    if user_id is None:
        raise ValueError(
            "user_id cannot be empty."
        )

    user_id = str(
        user_id
    ).strip()

    if not user_id:
        raise ValueError(
            "user_id cannot be empty."
        )

    return user_id


def _validate_list(
    value: Any,
    field_name: str,
):
    """
    Validate that a value is a list.
    """

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{field_name} must be a list."
        )


def _validate_limit(
    limit: int | None,
):
    """
    Validate optional result limit.
    """

    if limit is None:
        return

    if not isinstance(
        limit,
        int,
    ):
        raise ValueError(
            "limit must be an integer."
        )

    if limit < 1:
        raise ValueError(
            "limit must be greater than zero."
        )


def _validate_items(
    items: list,
    field_name: str,
):
    """
    Validate an array of trait/preference strings.

    The storage model intentionally remains:

        list[str]

    """

    _validate_list(
        items,
        field_name,
    )

    normalized = []

    for index, item in enumerate(items):

        if not isinstance(
            item,
            str,
        ):
            raise ValueError(
                f"{field_name}[{index}] must be a string."
            )

        item = item.strip()

        if not item:
            raise ValueError(
                f"{field_name}[{index}] cannot be empty."
            )

        normalized.append(
            item
        )

    return normalized


def _apply_limit(
    items: list,
    limit: int | None,
):
    """
    Apply an optional list limit.
    """

    _validate_limit(
        limit
    )

    if limit is None:
        return items

    return items[:limit]


def _normalize_traits(
    value: Any,
):
    """
    Normalize the psychological_traits JSONB object.

    Expected structure:

        {
            "facts": [...]
        }
    """

    if value is None:
        return {
            "facts": []
        }

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "psychological_traits must be an object."
        )

    facts = value.get(
        "facts",
        [],
    )

    if not isinstance(
        facts,
        list,
    ):
        raise ValueError(
            "psychological_traits.facts must be a list."
        )

    normalized_facts = []

    for fact in facts:

        if not isinstance(
            fact,
            str,
        ):
            raise ValueError(
                "Every psychological trait must be a string."
            )

        fact = fact.strip()

        if fact:
            normalized_facts.append(
                fact
            )

    return {
        "facts": normalized_facts
    }


def _normalize_preferences(
    value: Any,
):
    """
    Normalize the preferences JSONB object.

    Expected structure:

        {
            "items": [...]
        }
    """

    if value is None:
        return {
            "items": []
        }

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "preferences must be an object."
        )

    items = value.get(
        "items",
        [],
    )

    if not isinstance(
        items,
        list,
    ):
        raise ValueError(
            "preferences.items must be a list."
        )

    normalized_items = []

    for item in items:

        if not isinstance(
            item,
            str,
        ):
            raise ValueError(
                "Every preference must be a string."
            )

        item = item.strip()

        if item:
            normalized_items.append(
                item
            )

    return {
        "items": normalized_items
    }


def _validate_user_exists(
    user_id: str,
):
    """
    Ensure the user exists and has not been soft-deleted.
    """

    user_id = _validate_user_id(
        user_id
    )

    user = get_user(
        user_id
    )

    if user is None:
        raise ValueError(
            "User not found."
        )

    return user


# =====================================================================
# READ — TRAITS + PREFERENCES
# =====================================================================

def read_traits_preferences(
    user_id: str,
    traits_limit: int | None = None,
    preferences_limit: int | None = None,
):
    """
    Read both psychological traits and preferences.

    Returns:

        {
            "psychological_traits": {
                "facts": [...]
            },
            "preferences": {
                "items": [...]
            }
        }
    """

    user_id = _validate_user_id(
        user_id
    )

    _validate_limit(
        traits_limit
    )

    _validate_limit(
        preferences_limit
    )

    query = """
    SELECT
        psychological_traits,
        preferences

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL;
    """

    result = execute_read_only(
        query,
        (
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    traits = _normalize_traits(
        row.get(
            "psychological_traits"
        )
    )

    preferences = _normalize_preferences(
        row.get(
            "preferences"
        )
    )

    traits["facts"] = _apply_limit(
        traits["facts"],
        traits_limit,
    )

    preferences["items"] = _apply_limit(
        preferences["items"],
        preferences_limit,
    )

    return {
        "psychological_traits": traits,
        "preferences": preferences,
    }


# =====================================================================
# READ — PSYCHOLOGICAL TRAITS
# =====================================================================

def read_psychological_traits(
    user_id: str,
    limit: int | None = None,
):
    """
    Read psychological traits for one user.
    """

    user_id = _validate_user_id(
        user_id
    )

    _validate_limit(
        limit
    )

    query = """
    SELECT
        psychological_traits

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL;
    """

    result = execute_read_only(
        query,
        (
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    traits = _normalize_traits(
        result[0].get(
            "psychological_traits"
        )
    )

    traits["facts"] = _apply_limit(
        traits["facts"],
        limit,
    )

    return traits


# =====================================================================
# READ — PREFERENCES
# =====================================================================

def read_preferences(
    user_id: str,
    limit: int | None = None,
):
    """
    Read preferences for one user.
    """

    user_id = _validate_user_id(
        user_id
    )

    _validate_limit(
        limit
    )

    query = """
    SELECT
        preferences

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL;
    """

    result = execute_read_only(
        query,
        (
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    preferences = _normalize_preferences(
        result[0].get(
            "preferences"
        )
    )

    preferences["items"] = _apply_limit(
        preferences["items"],
        limit,
    )

    return preferences


# =====================================================================
# WRITE — TRAITS + PREFERENCES
# =====================================================================

def write_traits_preferences(
    user_id: str,
    psychological_traits: dict | None = None,
    preferences: dict | None = None,
):
    """
    Replace psychological traits and/or preferences.

    Example:

        write_traits_preferences(
            user_id,
            psychological_traits={
                "facts": [
                    "Prefers structured conversations"
                ]
            },
            preferences={
                "items": [
                    "Prefers concise explanations"
                ]
            }
        )

    If one argument is None, that field remains unchanged.
    """

    user_id = _validate_user_id(
        user_id
    )

    _validate_user_exists(
        user_id
    )

    fields = []
    parameters = []

    if psychological_traits is not None:

        normalized_traits = _normalize_traits(
            psychological_traits
        )

        import psycopg2.extras

        fields.append(
            "psychological_traits = %s"
        )

        parameters.append(
            psycopg2.extras.Json(
                normalized_traits
            )
        )

    if preferences is not None:

        normalized_preferences = _normalize_preferences(
            preferences
        )

        import psycopg2.extras

        fields.append(
            "preferences = %s"
        )

        parameters.append(
            psycopg2.extras.Json(
                normalized_preferences
            )
        )

    if not fields:
        raise ValueError(
            "At least one of psychological_traits "
            "or preferences must be supplied."
        )

    fields.append(
        "updated_at = NOW()"
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
        psychological_traits,
        preferences,
        updated_at;
    """

    result = execute_read_write(
        query,
        tuple(parameters),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    return {
        "user_id": str(
            row["user_id"]
        ),
        "psychological_traits":
            _normalize_traits(
                row["psychological_traits"]
            ),
        "preferences":
            _normalize_preferences(
                row["preferences"]
            ),
        "updated_at":
            row["updated_at"],
    }


# =====================================================================
# WRITE — PSYCHOLOGICAL TRAITS
# =====================================================================

def write_psychological_traits(
    user_id: str,
    facts: list[str],
):
    """
    Replace all psychological traits for a user.
    """

    user_id = _validate_user_id(
        user_id
    )

    facts = _validate_items(
        facts,
        "facts",
    )

    _validate_user_exists(
        user_id
    )

    import psycopg2.extras

    traits = {
        "facts": facts
    }

    query = """
    UPDATE users

    SET
        psychological_traits = %s,
        updated_at = NOW()

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        psychological_traits,
        updated_at;
    """

    result = execute_read_write(
        query,
        (
            psycopg2.extras.Json(
                traits
            ),
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    return {
        "user_id": str(
            row["user_id"]
        ),
        "psychological_traits":
            _normalize_traits(
                row["psychological_traits"]
            ),
        "updated_at":
            row["updated_at"],
    }


# =====================================================================
# WRITE — PREFERENCES
# =====================================================================

def write_preferences(
    user_id: str,
    items: list[str],
):
    """
    Replace all preferences for a user.
    """

    user_id = _validate_user_id(
        user_id
    )

    items = _validate_items(
        items,
        "items",
    )

    _validate_user_exists(
        user_id
    )

    import psycopg2.extras

    preferences = {
        "items": items
    }

    query = """
    UPDATE users

    SET
        preferences = %s,
        updated_at = NOW()

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        preferences,
        updated_at;
    """

    result = execute_read_write(
        query,
        (
            psycopg2.extras.Json(
                preferences
            ),
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    return {
        "user_id": str(
            row["user_id"]
        ),
        "preferences":
            _normalize_preferences(
                row["preferences"]
            ),
        "updated_at":
            row["updated_at"],
    }


# =====================================================================
# APPEND — PSYCHOLOGICAL TRAITS
# =====================================================================

def append_psychological_traits(
    user_id: str,
    facts: list[str],
):
    """
    Append psychological traits to the existing list.

    Existing entries are preserved.

    Exact duplicate strings are not added again.
    """

    user_id = _validate_user_id(
        user_id
    )

    facts = _validate_items(
        facts,
        "facts",
    )

    _validate_user_exists(
        user_id
    )

    import psycopg2.extras

    query = """
    SELECT
        psychological_traits

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL
    FOR UPDATE;
    """

    # -------------------------------------------------------------
    # Read current value.
    #
    # The actual update is performed atomically below using JSONB
    # expressions. The SELECT is used to normalize the current data.
    # -------------------------------------------------------------

    current = execute_read_only(
        query.replace(
            "FOR UPDATE;",
            ";",
        ),
        (
            user_id,
        ),
    )

    if not current:
        raise ValueError(
            "User not found."
        )

    existing = _normalize_traits(
        current[0]["psychological_traits"]
    )

    combined = list(
        existing["facts"]
    )

    for fact in facts:

        if fact not in combined:
            combined.append(
                fact
            )

    updated = {
        "facts": combined
    }

    update_query = """
    UPDATE users

    SET
        psychological_traits = %s,
        updated_at = NOW()

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        psychological_traits,
        updated_at;
    """

    result = execute_read_write(
        update_query,
        (
            psycopg2.extras.Json(
                updated
            ),
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    return {
        "user_id": str(
            row["user_id"]
        ),
        "psychological_traits":
            _normalize_traits(
                row["psychological_traits"]
            ),
        "updated_at":
            row["updated_at"],
    }


# =====================================================================
# APPEND — PREFERENCES
# =====================================================================

def append_preferences(
    user_id: str,
    items: list[str],
):
    """
    Append preferences to the existing list.

    Existing entries are preserved.

    Exact duplicate strings are not added again.
    """

    user_id = _validate_user_id(
        user_id
    )

    items = _validate_items(
        items,
        "items",
    )

    _validate_user_exists(
        user_id
    )

    import psycopg2.extras

    query = """
    SELECT
        preferences

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL;
    """

    current = execute_read_only(
        query,
        (
            user_id,
        ),
    )

    if not current:
        raise ValueError(
            "User not found."
        )

    existing = _normalize_preferences(
        current[0]["preferences"]
    )

    combined = list(
        existing["items"]
    )

    for item in items:

        if item not in combined:
            combined.append(
                item
            )

    updated = {
        "items": combined
    }

    update_query = """
    UPDATE users

    SET
        preferences = %s,
        updated_at = NOW()

    WHERE
        user_id = %s
        AND deleted_at IS NULL

    RETURNING
        user_id,
        preferences,
        updated_at;
    """

    result = execute_read_write(
        update_query,
        (
            psycopg2.extras.Json(
                updated
            ),
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    row = result[0]

    return {
        "user_id": str(
            row["user_id"]
        ),
        "preferences":
            _normalize_preferences(
                row["preferences"]
            ),
        "updated_at":
            row["updated_at"],
    }


# =====================================================================
# DELETE — ONE PSYCHOLOGICAL TRAIT
# =====================================================================

def delete_psychological_trait(
    user_id: str,
    fact: str,
):
    """
    Delete all exact matches of one psychological trait.
    """

    user_id = _validate_user_id(
        user_id
    )

    fact = str(
        fact
    ).strip()

    if not fact:
        raise ValueError(
            "fact cannot be empty."
        )

    current = read_psychological_traits(
        user_id
    )

    old_facts = current[
        "facts"
    ]

    new_facts = [
        item
        for item in old_facts
        if item != fact
    ]

    removed_count = (
        len(old_facts)
        - len(new_facts)
    )

    result = write_psychological_traits(
        user_id,
        new_facts,
    )

    result[
        "removed_count"
    ] = removed_count

    return result


# =====================================================================
# DELETE — ONE PREFERENCE
# =====================================================================

def delete_preference(
    user_id: str,
    preference: str,
):
    """
    Delete all exact matches of one preference.
    """

    user_id = _validate_user_id(
        user_id
    )

    preference = str(
        preference
    ).strip()

    if not preference:
        raise ValueError(
            "preference cannot be empty."
        )

    current = read_preferences(
        user_id
    )

    old_items = current[
        "items"
    ]

    new_items = [
        item
        for item in old_items
        if item != preference
    ]

    removed_count = (
        len(old_items)
        - len(new_items)
    )

    result = write_preferences(
        user_id,
        new_items,
    )

    result[
        "removed_count"
    ] = removed_count

    return result


# =====================================================================
# CLEAR — PSYCHOLOGICAL TRAITS
# =====================================================================

def clear_psychological_traits(
    user_id: str,
):
    """
    Remove all psychological traits.
    """

    return write_psychological_traits(
        user_id,
        [],
    )


# =====================================================================
# CLEAR — PREFERENCES
# =====================================================================

def clear_preferences(
    user_id: str,
):
    """
    Remove all preferences.
    """

    return write_preferences(
        user_id,
        [],
    )


# =====================================================================
# COUNTS
# =====================================================================

def get_traits_preferences_counts(
    user_id: str,
):
    """
    Return counts for traits and preferences.
    """

    user_id = _validate_user_id(
        user_id
    )

    query = """
    SELECT
        psychological_traits,
        preferences

    FROM users

    WHERE
        user_id = %s
        AND deleted_at IS NULL;
    """

    result = execute_read_only(
        query,
        (
            user_id,
        ),
    )

    if not result:
        raise ValueError(
            "User not found."
        )

    traits = _normalize_traits(
        result[0][
            "psychological_traits"
        ]
    )

    preferences = _normalize_preferences(
        result[0][
            "preferences"
        ]
    )

    return {
        "user_id": user_id,

        "psychological_traits_count":
            len(
                traits["facts"]
            ),

        "preferences_count":
            len(
                preferences["items"]
            ),
    }