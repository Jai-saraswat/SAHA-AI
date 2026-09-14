from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from postgres import (
    execute_read_only,
    execute_read_write,
    generate_user_id,
)

from conversation_class import ConversationSession


app = FastAPI(
    title="SAHA API",
    description="API for SAHA's conversation and database services.",
)


class PostgreSQLRequest(BaseModel):
    code: str


class CreateUserRequest(BaseModel):
    username: str


class StartConversationRequest(BaseModel):
    user_id: str
    message: str
    topic: str | None = None


class ContinueConversationRequest(BaseModel):
    conversation_id: str
    message: str


@app.post(
    "/postgres/read-only",
    summary="Execute a read-only PostgreSQL query",
    description=(
        "Executes PostgreSQL code inside a read-only transaction. "
        "Database modifications are not permitted."
    ),
)
def postgres_read_only(request: PostgreSQLRequest):
    try:
        result = execute_read_only(request.code)

        return {
            "success": True,
            "mode": "read-only",
            "result": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": str(exc),
            },
        )


@app.post(
    "/postgres/read-write",
    summary="Execute a read-write PostgreSQL query",
    description=(
        "Executes PostgreSQL code with read and write access. "
        "Successful database changes are committed."
    ),
)
def postgres_read_write(request: PostgreSQLRequest):
    try:
        result = execute_read_write(request.code)

        return {
            "success": True,
            "mode": "read-write",
            "result": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": str(exc),
            },
        )


@app.post(
    "/create_user",
    summary="Create or retrieve a user",
    description=(
        "Creates a new user with the supplied username. "
        "If the username already exists, returns the existing user."
    ),
)
def create_user(request: CreateUserRequest):
    try:
        return generate_user_id(request.username)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(exc),
            },
        )


@app.get(
    "/conversations/{user_id}",
    summary="Get a user's conversations",
    description=(
        "Returns the conversations belonging to a user, including "
        "their conversation IDs, topics, and timestamps."
    ),
)
def get_conversations(user_id: str):
    try:
        query = """
        SELECT
            conversation_id,
            user_id,
            topic,
            started_at,
            ended_at,
            created_at,
            updated_at
        FROM conversations
        WHERE user_id = %s
        ORDER BY updated_at DESC;
        """

        result = ConversationSession._parameterize(
            query,
            (user_id,),
        )

        conversations = execute_read_only(result)

        return {
            "success": True,
            "user_id": user_id,
            "conversations": conversations,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(exc),
            },
        )


@app.post(
    "/start_conversation",
    summary="Start a new conversation",
    description=(
        "Creates a new conversation for an existing user and stores "
        "the initial user message."
    ),
)
def start_conversation(request: StartConversationRequest):
    try:
        conversation = ConversationSession(
            user_id=request.user_id,
            topic=request.topic,
        )

        conversation.create()
        conversation.add_user_message(request.message)

        return {
            "success": True,
            "conversation_id": conversation.session_id,
            "user_id": conversation.user_id,
            "topic": conversation.topic,
            "message": request.message,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(exc),
            },
        )


@app.post(
    "/conversation_continue",
    summary="Continue an existing conversation",
    description=(
        "Adds a new user message to an existing conversation and "
        "returns the conversation context needed by the workflow."
    ),
)
def conversation_continue(request: ContinueConversationRequest):
    try:
        conversation = ConversationSession(
            session_id=request.conversation_id
        )

        conversation.add_user_message(request.message)

        return {
            "success": True,
            "conversation_id": conversation.session_id,
            "user_id": conversation.user_id,
            "topic": conversation.topic,
            "message": request.message,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(exc),
            },
        )