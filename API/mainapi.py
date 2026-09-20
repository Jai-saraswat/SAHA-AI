import sys
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# DATABASE
# ============================================================

from API.postgres import (
    execute_read_only,
    execute_read_write,

    # Users
    generate_user_id,
    get_user,
    get_user_by_username,
    update_user,
    delete_user,
    get_users_overview,

    # Roles
    add_user_role,
    remove_user_role,

    # Relationships
    link_users,
    get_relationship,
    get_user_relationships,
    update_relationship,
    end_relationship,
    delete_relationship,

    # Relationship AI settings
    initialize_relationship_ai_settings,
    get_relationship_ai_settings,
    update_relationship_ai_settings,

    # Conversations
    get_conversation,
    update_conversation,
    delete_conversation,
    initialize_graphiti_buffer,
    get_graphiti_buffer,

    # Messages
    get_message,
    edit_message,
    delete_message,
)


# ============================================================
# CONVERSATION
# ============================================================

from API.conversation_class import ConversationSession


# ============================================================
# TRAITS + PREFERENCES
# ============================================================

from Database.Memory.traits_preferences import (
    read_traits_preferences,
    write_traits_preferences,

    read_psychological_traits,
    write_psychological_traits,

    read_preferences,
    write_preferences,

    append_psychological_traits,
    append_preferences,

    delete_psychological_trait,
    delete_preference,

    clear_psychological_traits,
    clear_preferences,

    get_traits_preferences_counts,
)


# ============================================================
# GRAPHITI TEMPORAL MEMORY
#
# IMPORTANT:
# The public Graphiti workflow contract remains unchanged:
#
# write(
#     user_id,
#     conversation_id,
#     messages
# )
#
# retrieve_related(
#     query,
#     user_id,
#     num_results
# )
# ============================================================

from Database.Memory.graphiti.graphiti import (
    write as write_temporal_memory,
    retrieve_related as retrieve_temporal_memory,
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="SAHA API",
    version="2.0.0",
    description=(
        "SAHA API for users, client-therapist relationships, "
        "conversations, messages, AI settings, user state, "
        "longitudinal memory, and system evaluation."
    ),
)


# ============================================================
# COMMON ERROR HELPERS
# ============================================================

def _handle_value_error(exc: ValueError):
    raise HTTPException(
        status_code=400,
        detail={
            "success": False,
            "error": str(exc),
        },
    )


def _handle_server_error(exc: Exception):
    raise HTTPException(
        status_code=500,
        detail={
            "success": False,
            "error": str(exc),
        },
    )


# ============================================================
# REQUEST MODELS
# ============================================================


# ------------------------------------------------------------
# Evaluation / database
# ------------------------------------------------------------

class DatabaseQueryRequest(BaseModel):
    query: str


# ------------------------------------------------------------
# Users
# ------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str
    role: str | None = None
    display_name: str | None = None
    email: str | None = None


class UpdateUserRequest(BaseModel):
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    metadata: dict | None = None


class UserRoleRequest(BaseModel):
    role: str


# ------------------------------------------------------------
# Relationships
# ------------------------------------------------------------

class CreateRelationshipRequest(BaseModel):
    client_user_id: str
    therapist_user_id: str


class UpdateRelationshipRequest(BaseModel):
    status: str | None = None
    metadata: dict | None = None


# ------------------------------------------------------------
# Relationship AI settings
# ------------------------------------------------------------

class UpdateAISettingsRequest(BaseModel):
    ai_enabled: bool | None = None
    analysis_enabled: bool | None = None
    memory_enabled: bool | None = None

    strategy_planner_enabled: bool | None = None
    therapist_assistance_enabled: bool | None = None
    client_response_generation_enabled: bool | None = None

    real_time_analysis_enabled: bool | None = None
    post_conversation_analysis_enabled: bool | None = None

    allowed_data_sources: list | None = None
    restricted_data_sources: list | None = None

    allowed_capabilities: list | None = None
    restricted_capabilities: list | None = None

    strategy_constraints: dict | None = None

    custom_instructions: str | None = None

    configuration: dict | None = None


# ------------------------------------------------------------
# Conversations
# ------------------------------------------------------------

class CreateConversationRequest(BaseModel):
    relationship_id: str
    topic: str | None = None


class UpdateConversationRequest(BaseModel):
    topic: str | None = None
    status: str | None = None
    metadata: dict | None = None


# ------------------------------------------------------------
# Messages
# ------------------------------------------------------------

class AddMessageRequest(BaseModel):
    sender_user_id: str
    content: str


class AddClientMessageRequest(BaseModel):
    content: str


class AddTherapistMessageRequest(BaseModel):
    content: str


class EditMessageRequest(BaseModel):
    content: str


# ------------------------------------------------------------
# Memory buffer
# ------------------------------------------------------------

class MemoryBufferMessage(BaseModel):
    id: str | None = None
    content: str
    timestamp: str | None = None


class AddMemoryBufferMessageRequest(BaseModel):
    user_id: str
    message: MemoryBufferMessage


class InitializeMemoryBufferRequest(BaseModel):
    user_id: str


class ClearMemoryBufferRequest(BaseModel):
    user_id: str


# ------------------------------------------------------------
# Temporal memory
# ------------------------------------------------------------

class TemporalMemoryMessage(BaseModel):
    id: str | None = None
    content: str
    timestamp: str | None = None


class WriteTemporalMemoryRequest(BaseModel):
    user_id: str
    conversation_id: str
    messages: list[TemporalMemoryMessage]


# ------------------------------------------------------------
# Traits + preferences
# ------------------------------------------------------------

class UpdateTraitsPreferencesRequest(BaseModel):
    psychological_traits: dict | None = None
    preferences: dict | None = None


class ReplaceTraitsRequest(BaseModel):
    facts: list


class AppendTraitsRequest(BaseModel):
    facts: list


class ReplacePreferencesRequest(BaseModel):
    items: list


class AppendPreferencesRequest(BaseModel):
    items: list


# ============================================================
# ROOT / HEALTH
# ============================================================

@app.get(
    "/",
    tags=["System"],
    summary="API status",
)
def root():
    return {
        "success": True,
        "service": "SAHA API",
        "version": "2.0.0",
        "status": "running",
    }


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
)
def health():
    return {
        "success": True,
        "status": "healthy",
    }


# ============================================================
# USERS
# ============================================================

@app.post(
    "/api/v1/users",
    tags=["Users"],
    summary="Create user",
)
def create_user(
    request: CreateUserRequest,
):
    """
    Create a new user.

    This endpoint is CREATE ONLY.
    It does not act as a lookup endpoint.
    """

    try:
        result = generate_user_id(
            username=request.username,
            role=request.role,
            display_name=request.display_name,
            email=request.email,
        )

        return {
            "success": True,
            "user": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/users/{user_id}",
    tags=["Users"],
    summary="Get user",
)
def get_user_endpoint(
    user_id: str,
):
    try:
        result = get_user(user_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found.",
                    "user_id": user_id,
                },
            )

        return {
            "success": True,
            "user": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/users/by-username/{username}",
    tags=["Users"],
    summary="Find user by username",
)
def get_user_by_username_endpoint(
    username: str,
):
    try:
        result = get_user_by_username(username)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found.",
                    "username": username,
                },
            )

        return {
            "success": True,
            "user": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/users/{user_id}",
    tags=["Users"],
    summary="Update user",
)
def update_user_endpoint(
    user_id: str,
    request: UpdateUserRequest,
):
    try:
        result = update_user(
            user_id=user_id,
            username=request.username,
            display_name=request.display_name,
            email=request.email,
            metadata=request.metadata,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found.",
                },
            )

        return {
            "success": True,
            "user": result[0],
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}",
    tags=["Users"],
    summary="Delete user",
)
def delete_user_endpoint(
    user_id: str,
):
    try:
        result = delete_user(user_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found.",
                },
            )

        return {
            "success": True,
            "deleted": True,
            "user": result[0],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# USER ROLES
# ============================================================

@app.get(
    "/api/v1/users/{user_id}/roles",
    tags=["User Roles"],
    summary="Get user roles",
)
def get_user_roles_endpoint(
    user_id: str,
):
    try:
        query = """
        SELECT
            role,
            created_at
        FROM user_roles
        WHERE user_id = %s
        ORDER BY created_at ASC;
        """

        result = execute_read_only(
            query,
            (user_id,),
        )

        return {
            "success": True,
            "user_id": user_id,
            "count": len(result),
            "roles": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/users/{user_id}/roles",
    tags=["User Roles"],
    summary="Add role to user",
)
def add_user_role_endpoint(
    user_id: str,
    request: UserRoleRequest,
):
    try:
        result = add_user_role(
            user_id=user_id,
            role=request.role,
        )

        return {
            "success": True,
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}/roles/{role}",
    tags=["User Roles"],
    summary="Remove role from user",
)
def remove_user_role_endpoint(
    user_id: str,
    role: str,
):
    try:
        result = remove_user_role(
            user_id=user_id,
            role=role,
        )

        return {
            "success": True,
            "removed": bool(result),
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# RELATIONSHIPS
# ============================================================

@app.post(
    "/api/v1/relationships",
    tags=["Relationships"],
    summary="Create client-therapist relationship",
)
def create_relationship(
    request: CreateRelationshipRequest,
):
    try:
        result = link_users(
            client_user_id=request.client_user_id,
            therapist_user_id=request.therapist_user_id,
        )

        return result

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/relationships/{relationship_id}",
    tags=["Relationships"],
    summary="Get relationship",
)
def get_relationship_endpoint(
    relationship_id: str,
):
    try:
        result = get_relationship(relationship_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Relationship not found.",
                },
            )

        return {
            "success": True,
            "relationship": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/users/{user_id}/relationships",
    tags=["Relationships"],
    summary="Get user's relationships",
)
def get_user_relationships_endpoint(
    user_id: str,
):
    try:
        result = get_user_relationships(user_id)

        return {
            "success": True,
            "user_id": user_id,
            "count": len(result),
            "relationships": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/relationships/{relationship_id}",
    tags=["Relationships"],
    summary="Update relationship",
)
def update_relationship_endpoint(
    relationship_id: str,
    request: UpdateRelationshipRequest,
):
    try:
        result = update_relationship(
            relationship_id=relationship_id,
            status=request.status,
            metadata=request.metadata,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Relationship not found.",
                },
            )

        return {
            "success": True,
            "relationship": result[0],
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/relationships/{relationship_id}/end",
    tags=["Relationships"],
    summary="End relationship",
)
def end_relationship_endpoint(
    relationship_id: str,
):
    try:
        result = end_relationship(relationship_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Relationship not found.",
                },
            )

        return {
            "success": True,
            "ended": True,
            "relationship": result[0],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/relationships/{relationship_id}",
    tags=["Relationships"],
    summary="Delete relationship",
)
def delete_relationship_endpoint(
    relationship_id: str,
):
    try:
        result = delete_relationship(relationship_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Relationship not found.",
                },
            )

        return {
            "success": True,
            "deleted": True,
            "relationship": result[0],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# RELATIONSHIP AI SETTINGS
# ============================================================

@app.get(
    "/api/v1/relationships/{relationship_id}/ai-settings",
    tags=["AI Settings"],
    summary="Get AI settings",
)
def get_ai_settings_endpoint(
    relationship_id: str,
):
    try:
        result = get_relationship_ai_settings(
            relationship_id
        )

        if not result:
            result = initialize_relationship_ai_settings(
                relationship_id
            )

        return {
            "success": True,
            "relationship_id": relationship_id,
            "settings": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/relationships/{relationship_id}/ai-settings",
    tags=["AI Settings"],
    summary="Update AI settings",
)
def update_ai_settings_endpoint(
    relationship_id: str,
    request: UpdateAISettingsRequest,
):
    try:
        settings = request.model_dump(
            exclude_none=True
        )

        if not settings:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "No settings supplied.",
                },
            )

        initialize_relationship_ai_settings(
            relationship_id
        )

        result = update_relationship_ai_settings(
            relationship_id=relationship_id,
            **settings,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "AI settings not found.",
                },
            )

        return {
            "success": True,
            "relationship_id": relationship_id,
            "settings": result,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# CONVERSATIONS
# ============================================================

@app.post(
    "/api/v1/conversations",
    tags=["Conversations"],
    summary="Start conversation",
)
def create_conversation_endpoint(
    request: CreateConversationRequest,
):
    try:
        conversation = ConversationSession(
            relationship_id=request.relationship_id,
            topic=request.topic,
        )

        result = conversation.create()

        return {
            "success": True,
            "conversation_id": conversation.conversation_id,
            "relationship_id": conversation.relationship_id,
            "client_user_id": conversation.client_user_id,
            "therapist_user_id": conversation.therapist_user_id,
            "topic": conversation.topic,
            "status": conversation.status,
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Get conversation",
)
def get_conversation_endpoint(
    conversation_id: str,
):
    try:
        result = get_conversation(conversation_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        return {
            "success": True,
            "conversation": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/relationships/{relationship_id}/conversations",
    tags=["Conversations"],
    summary="Get relationship conversations",
)
def get_relationship_conversations_endpoint(
    relationship_id: str,
):
    try:
        query = """
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
            AND deleted_at IS NULL
        ORDER BY updated_at DESC;
        """

        result = execute_read_only(
            query,
            (relationship_id,),
        )

        for conversation in result:
            conversation["conversation_id"] = str(
                conversation["conversation_id"]
            )
            conversation["relationship_id"] = str(
                conversation["relationship_id"]
            )

        return {
            "success": True,
            "relationship_id": relationship_id,
            "count": len(result),
            "conversations": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Update conversation",
)
def update_conversation_endpoint(
    conversation_id: str,
    request: UpdateConversationRequest,
):
    try:
        result = update_conversation(
            conversation_id=conversation_id,
            topic=request.topic,
            status=request.status,
            metadata=request.metadata,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        return {
            "success": True,
            "conversation": result[0],
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/end",
    tags=["Conversations"],
    summary="End conversation",
)
def end_conversation_endpoint(
    conversation_id: str,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.end()

        return {
            "success": True,
            "ended": True,
            "conversation_id": conversation_id,
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/pause",
    tags=["Conversations"],
    summary="Pause conversation",
)
def pause_conversation_endpoint(
    conversation_id: str,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.pause()

        return {
            "success": True,
            "status": "paused",
            "conversation_id": conversation_id,
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/resume",
    tags=["Conversations"],
    summary="Resume conversation",
)
def resume_conversation_endpoint(
    conversation_id: str,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.resume()

        return {
            "success": True,
            "status": "active",
            "conversation_id": conversation_id,
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/conversations/{conversation_id}",
    tags=["Conversations"],
    summary="Delete conversation",
)
def delete_conversation_endpoint(
    conversation_id: str,
):
    try:
        result = delete_conversation(
            conversation_id
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        return {
            "success": True,
            "deleted": True,
            "conversation": result[0],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# MESSAGES
# ============================================================

@app.get(
    "/api/v1/conversations/{conversation_id}/messages",
    tags=["Messages"],
    summary="Get conversation messages",
)
def get_conversation_messages_endpoint(
    conversation_id: str,
    include_deleted: bool = False,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.get_history(
            include_deleted=include_deleted
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "count": len(result),
            "messages": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/messages",
    tags=["Messages"],
    summary="Add message",
)
def add_message_endpoint(
    conversation_id: str,
    request: AddMessageRequest,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        if str(request.sender_user_id) == str(
            conversation.client_user_id
        ):
            sender_type = "client"

        elif str(request.sender_user_id) == str(
            conversation.therapist_user_id
        ):
            sender_type = "therapist"

        else:
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": (
                        "User is not a participant "
                        "in this conversation."
                    ),
                },
            )

        result = conversation.add_message(
            sender_user_id=request.sender_user_id,
            sender_type=sender_type,
            content=request.content,
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "sender_type": sender_type,
            "result": result,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/client-messages",
    tags=["Messages"],
    summary="Add client message",
)
def add_client_message_endpoint(
    conversation_id: str,
    request: AddClientMessageRequest,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.add_client_message(
            request.content
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "sender_type": "client",
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/conversations/{conversation_id}/therapist-messages",
    tags=["Messages"],
    summary="Add therapist message",
)
def add_therapist_message_endpoint(
    conversation_id: str,
    request: AddTherapistMessageRequest,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.add_therapist_message(
            request.content
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "sender_type": "therapist",
            "result": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/conversations/{conversation_id}/client-messages",
    tags=["Messages"],
    summary="Get client messages",
)
def get_client_messages_endpoint(
    conversation_id: str,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.get_client_messages()

        return {
            "success": True,
            "conversation_id": conversation_id,
            "count": len(result),
            "messages": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/conversations/{conversation_id}/therapist-messages",
    tags=["Messages"],
    summary="Get therapist messages",
)
def get_therapist_messages_endpoint(
    conversation_id: str,
):
    try:
        conversation = ConversationSession(
            conversation_id=conversation_id
        )

        result = conversation.get_therapist_messages()

        return {
            "success": True,
            "conversation_id": conversation_id,
            "count": len(result),
            "messages": result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/messages/{message_id}",
    tags=["Messages"],
    summary="Get message",
)
def get_message_endpoint(
    message_id: str,
):
    try:
        result = get_message(message_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Message not found.",
                },
            )

        return {
            "success": True,
            "message": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/messages/{message_id}",
    tags=["Messages"],
    summary="Edit message",
)
def edit_message_endpoint(
    message_id: str,
    request: EditMessageRequest,
):
    try:
        result = edit_message(
            message_id=message_id,
            content=request.content,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Message not found.",
                },
            )

        return {
            "success": True,
            "message": result[0],
        }

    except HTTPException:
        raise

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/messages/{message_id}",
    tags=["Messages"],
    summary="Delete message",
)
def delete_message_endpoint(
    message_id: str,
):
    try:
        result = delete_message(message_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Message not found.",
                },
            )

        return {
            "success": True,
            "deleted": True,
            "message": result[0],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# USER TRAITS
# ============================================================

@app.get(
    "/api/v1/users/{user_id}/traits",
    tags=["User Traits"],
    summary="Get psychological traits",
)
def get_traits_endpoint(
    user_id: str,
    limit: int | None = None,
):
    try:
        result = read_psychological_traits(
            user_id=user_id,
            limit=limit,
        )

        return {
            "success": True,
            **result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.put(
    "/api/v1/users/{user_id}/traits",
    tags=["User Traits"],
    summary="Replace psychological traits",
)
def replace_traits_endpoint(
    user_id: str,
    request: ReplaceTraitsRequest,
):
    try:
        return write_psychological_traits(
            user_id=user_id,
            facts=request.facts,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/users/{user_id}/traits",
    tags=["User Traits"],
    summary="Add psychological traits",
)
def add_traits_endpoint(
    user_id: str,
    request: AppendTraitsRequest,
):
    try:
        return append_psychological_traits(
            user_id=user_id,
            facts=request.facts,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}/traits",
    tags=["User Traits"],
    summary="Delete psychological trait",
)
def delete_trait_endpoint(
    user_id: str,
    fact: str = Query(...),
):
    try:
        return delete_psychological_trait(
            user_id=user_id,
            fact=fact,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}/traits/all",
    tags=["User Traits"],
    summary="Clear all psychological traits",
)
def clear_traits_endpoint(
    user_id: str,
):
    try:
        return clear_psychological_traits(user_id)

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# USER PREFERENCES
# ============================================================

@app.get(
    "/api/v1/users/{user_id}/preferences",
    tags=["User Preferences"],
    summary="Get preferences",
)
def get_preferences_endpoint(
    user_id: str,
    limit: int | None = None,
):
    try:
        result = read_preferences(
            user_id=user_id,
            limit=limit,
        )

        return {
            "success": True,
            **result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.put(
    "/api/v1/users/{user_id}/preferences",
    tags=["User Preferences"],
    summary="Replace preferences",
)
def replace_preferences_endpoint(
    user_id: str,
    request: ReplacePreferencesRequest,
):
    try:
        return write_preferences(
            user_id=user_id,
            items=request.items,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/users/{user_id}/preferences",
    tags=["User Preferences"],
    summary="Add preferences",
)
def add_preferences_endpoint(
    user_id: str,
    request: AppendPreferencesRequest,
):
    try:
        return append_preferences(
            user_id=user_id,
            items=request.items,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}/preferences",
    tags=["User Preferences"],
    summary="Delete preference",
)
def delete_preference_endpoint(
    user_id: str,
    preference: str = Query(...),
):
    try:
        return delete_preference(
            user_id=user_id,
            preference=preference,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/users/{user_id}/preferences/all",
    tags=["User Preferences"],
    summary="Clear all preferences",
)
def clear_preferences_endpoint(
    user_id: str,
):
    try:
        return clear_preferences(user_id)

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/users/{user_id}/traits-preferences",
    tags=["User State"],
    summary="Get traits and preferences",
)
def get_traits_preferences_endpoint(
    user_id: str,
    traits_limit: int | None = None,
    preferences_limit: int | None = None,
):
    try:
        result = read_traits_preferences(
            user_id=user_id,
            traits_limit=traits_limit,
            preferences_limit=preferences_limit,
        )

        return {
            "success": True,
            **result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.patch(
    "/api/v1/users/{user_id}/traits-preferences",
    tags=["User State"],
    summary="Update traits and preferences",
)
def update_traits_preferences_endpoint(
    user_id: str,
    request: UpdateTraitsPreferencesRequest,
):
    try:
        return write_traits_preferences(
            user_id=user_id,
            psychological_traits=request.psychological_traits,
            preferences=request.preferences,
        )

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/users/{user_id}/traits-preferences/counts",
    tags=["User State"],
    summary="Get trait and preference counts",
)
def get_traits_preferences_counts_endpoint(
    user_id: str,
):
    try:
        result = get_traits_preferences_counts(
            user_id
        )

        return {
            "success": True,
            **result,
        }

    except ValueError as exc:
        _handle_value_error(exc)

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# MEMORY BUFFER
#
# This is the temporary Graphiti ingestion buffer.
# It belongs to the conversation.
# ============================================================

@app.post(
    "/api/v1/memory/buffer/{conversation_id}/initialize",
    tags=["Memory Buffer"],
    summary="Initialize memory buffer",
)
def initialize_memory_buffer_endpoint(
    conversation_id: str,
    request: InitializeMemoryBufferRequest,
):
    try:
        conversation = get_conversation(
            conversation_id
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        if (
            str(conversation["client_user_id"])
            != str(request.user_id)
            and
            str(conversation["therapist_user_id"])
            != str(request.user_id)
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": (
                        "User is not a participant "
                        "in this conversation."
                    ),
                },
            )

        result = initialize_graphiti_buffer(
            conversation_id=conversation_id
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            **result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/memory/buffer/{conversation_id}",
    tags=["Memory Buffer"],
    summary="Get memory buffer",
)
def get_memory_buffer_endpoint(
    conversation_id: str,
):
    try:
        result = get_graphiti_buffer(
            conversation_id
        )

        if not result:
            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": [],
                "message_count": 0,
                "max_messages": 5,
                "ready": False,
            }

        return {
            "success": True,
            "conversation_id": conversation_id,
            "messages": result["messages"],
            "message_count": len(result["messages"]),
            "max_messages": 5,
            "ready": len(result["messages"]) >= 5,
            "updated_at": result["updated_at"],
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/memory/buffer/{conversation_id}/messages",
    tags=["Memory Buffer"],
    summary="Add message to memory buffer",
)
def add_memory_buffer_message_endpoint(
    conversation_id: str,
    request: AddMemoryBufferMessageRequest,
):
    try:
        conversation = get_conversation(
            conversation_id
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        if (
            str(conversation["client_user_id"])
            != str(request.user_id)
            and
            str(conversation["therapist_user_id"])
            != str(request.user_id)
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": (
                        "User is not a participant "
                        "in this conversation."
                    ),
                },
            )

        current = get_graphiti_buffer(
            conversation_id
        )

        messages = (
            current["messages"]
            if current
            else []
        )

        messages.append(
            request.message.model_dump()
        )

        query = """
        INSERT INTO graphiti_message_buffer (
            conversation_id,
            messages,
            updated_at
        )
        VALUES (
            %s,
            %s::jsonb,
            NOW()
        )
        ON CONFLICT (conversation_id)
        DO UPDATE SET
            messages = EXCLUDED.messages,
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
                json.dumps(
                    messages,
                    ensure_ascii=False,
                ),
            ),
        )

        buffer = result[0]

        return {
            "success": True,
            "conversation_id": str(
                buffer["conversation_id"]
            ),
            "messages": buffer["messages"],
            "message_count": len(
                buffer["messages"]
            ),
            "max_messages": 5,
            "ready": len(
                buffer["messages"]
            ) >= 5,
            "updated_at": buffer["updated_at"],
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.delete(
    "/api/v1/memory/buffer/{conversation_id}",
    tags=["Memory Buffer"],
    summary="Clear memory buffer",
)
def clear_memory_buffer_endpoint(
    conversation_id: str,
    request: ClearMemoryBufferRequest,
):
    try:
        conversation = get_conversation(
            conversation_id
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        if (
            str(conversation["client_user_id"])
            != str(request.user_id)
            and
            str(conversation["therapist_user_id"])
            != str(request.user_id)
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": (
                        "User is not a participant "
                        "in this conversation."
                    ),
                },
            )

        query = """
        DELETE FROM graphiti_message_buffer
        WHERE conversation_id = %s
        RETURNING conversation_id;
        """

        result = execute_read_write(
            query,
            (conversation_id,),
        )

        return {
            "success": True,
            "conversation_id": conversation_id,
            "cleared": bool(result),
            "message_count": 0,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# LONGITUDINAL MEMORY / GRAPHITI
#
# IMPORTANT:
# The underlying workflow remains unchanged.
# ============================================================

@app.post(
    "/api/v1/memory/temporal",
    tags=["Longitudinal Memory"],
    summary="Write longitudinal memory",
)
async def write_temporal_memory_endpoint(
    request: WriteTemporalMemoryRequest,
):
    try:
        conversation = get_conversation(
            request.conversation_id
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        if (
            str(conversation["client_user_id"])
            != str(request.user_id)
            and
            str(conversation["therapist_user_id"])
            != str(request.user_id)
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": (
                        "User is not a participant "
                        "in this conversation."
                    ),
                },
            )

        if len(request.messages) > 5:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": (
                        "Maximum 5 messages can be "
                        "written at once."
                    ),
                },
            )

        result = await write_temporal_memory(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            messages=[
                message.model_dump()
                for message in request.messages
            ],
        )

        return result

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/memory/temporal/search",
    tags=["Longitudinal Memory"],
    summary="Search longitudinal memory",
)
async def search_temporal_memory_endpoint(
    user_id: str,
    query: str,
    num_results: int = 10,
):
    try:
        if num_results < 1 or num_results > 50:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": (
                        "num_results must be between "
                        "1 and 50."
                    ),
                },
            )

        result = await retrieve_temporal_memory(
            query=query,
            user_id=user_id,
            num_results=num_results,
        )

        return {
            "success": True,
            "user_id": user_id,
            "query": query,
            "count": len(result),
            "results": result,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


# ============================================================
# EVALUATION
#
# These are inspection APIs.
# They are NOT normal client/therapist application APIs.
# ============================================================

@app.get(
    "/api/v1/evaluation/users",
    tags=["Evaluation"],
    summary="Get all users for evaluation",
)
def evaluation_users(
    include_deleted: bool = False,
):
    try:
        result = get_users_overview(
            include_deleted=include_deleted
        )

        return {
            "success": True,
            "count": len(result),
            "users": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/evaluation/user/{user_id}",
    tags=["Evaluation"],
    summary="Inspect complete user state",
)
def evaluation_user(
    user_id: str,
):
    try:
        user = get_user(user_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "User not found.",
                },
            )

        relationships = get_user_relationships(
            user_id
        )

        traits_preferences = read_traits_preferences(
            user_id
        )

        counts = get_traits_preferences_counts(
            user_id
        )

        return {
            "success": True,
            "user": user,
            "relationships": relationships,
            "traits_preferences": traits_preferences,
            "traits_preferences_counts": counts,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/evaluation/relationship/{relationship_id}",
    tags=["Evaluation"],
    summary="Inspect complete relationship",
)
def evaluation_relationship(
    relationship_id: str,
):
    try:
        relationship = get_relationship(
            relationship_id
        )

        if not relationship:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Relationship not found.",
                },
            )

        ai_settings = get_relationship_ai_settings(
            relationship_id
        )

        query = """
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
        ORDER BY started_at ASC;
        """

        conversations = execute_read_only(
            query,
            (relationship_id,),
        )

        return {
            "success": True,
            "relationship": relationship,
            "ai_settings": ai_settings,
            "conversation_count": len(
                conversations
            ),
            "conversations": conversations,
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/evaluation/conversation/{conversation_id}",
    tags=["Evaluation"],
    summary="Inspect complete conversation",
)
def evaluation_conversation(
    conversation_id: str,
):
    try:
        conversation = get_conversation(
            conversation_id
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Conversation not found.",
                },
            )

        relationship = get_relationship(
            conversation["relationship_id"]
        )

        ai_settings = get_relationship_ai_settings(
            conversation["relationship_id"]
        )

        session = ConversationSession(
            conversation_id=conversation_id
        )

        messages = session.get_history(
            include_deleted=True
        )

        buffer = get_graphiti_buffer(
            conversation_id
        )

        return {
            "success": True,
            "relationship": relationship,
            "ai_settings": ai_settings,
            "conversation": conversation,
            "messages": messages,
            "memory_buffer": (
                buffer
                if buffer
                else {
                    "conversation_id": conversation_id,
                    "messages": [],
                }
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        _handle_server_error(exc)


@app.get(
    "/api/v1/evaluation/memory/{user_id}",
    tags=["Evaluation"],
    summary="Search user longitudinal memory",
)
async def evaluation_memory(
    user_id: str,
    query: str,
    num_results: int = 10,
):
    return await search_temporal_memory_endpoint(
        user_id=user_id,
        query=query,
        num_results=num_results,
    )


# ============================================================
# EVALUATION DATABASE
#
# Raw SQL endpoints are deliberately separated from normal
# application APIs.
# ============================================================

@app.post(
    "/api/v1/evaluation/database/read",
    tags=["Evaluation Database"],
    summary="Run read-only PostgreSQL query",
)
def evaluation_database_read(
    request: DatabaseQueryRequest,
):
    try:
        result = execute_read_only(
            request.query
        )

        return {
            "success": True,
            "mode": "read-only",
            "result": result,
        }

    except Exception as exc:
        _handle_server_error(exc)


@app.post(
    "/api/v1/evaluation/database/write",
    tags=["Evaluation Database"],
    summary="Run PostgreSQL write query",
)
def evaluation_database_write(
    request: DatabaseQueryRequest,
):
    try:
        result = execute_read_write(
            request.query
        )

        return {
            "success": True,
            "mode": "read-write",
            "result": result,
        }

    except Exception as exc:
        _handle_server_error(exc)