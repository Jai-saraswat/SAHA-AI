import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from postgres import (
    execute_read_only,
    execute_read_write,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / "Database" / ".env"

load_dotenv(ENV_FILE)


class ConversationSession:
    """
    Represents one conversation session for one user.
    """

    def __init__(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        topic: str | None = None,
    ):
        self.session_id = (
            session_id
            if session_id
            else str(uuid.uuid4())
        )

        self.sequence_number = 0

        self.started_at = datetime.now(
            timezone.utc
        ).isoformat()

        self.topic = topic

        if session_id:

            conversation_query = """
            SELECT
                user_id,
                topic,
                started_at
            FROM conversations
            WHERE conversation_id = %s;
            """

            conversation_result = execute_read_only(
                self._parameterize(
                    conversation_query,
                    (self.session_id,),
                )
            )

            if not conversation_result:
                raise ValueError(
                    f"Conversation '{self.session_id}' does not exist."
                )

            self.user_id = conversation_result[0]["user_id"]
            self.topic = conversation_result[0]["topic"]
            self.started_at = conversation_result[0]["started_at"]

            sequence_query = """
            SELECT
                COALESCE(MAX(sequence_number), 0) AS sequence_number
            FROM conversation_messages
            WHERE conversation_id = %s;
            """

            sequence_result = execute_read_only(
                self._parameterize(
                    sequence_query,
                    (self.session_id,),
                )
            )

            self.sequence_number = (
                sequence_result[0]["sequence_number"]
            )

        else:

            if not user_id:
                raise ValueError(
                    "user_id is required when creating a new conversation."
                )

            self.user_id = user_id

    def create(self):
        """
        Create the conversation session in PostgreSQL.
        """

        query = """
        INSERT INTO conversations (
            conversation_id,
            user_id,
            topic,
            started_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
        RETURNING conversation_id;
        """

        return execute_read_write(
            self._parameterize(
                query,
                (
                    self.session_id,
                    self.user_id,
                    self.topic,
                    self.started_at,
                ),
            )
        )

    def add_message(
        self,
        role: str,
        content: str,
    ):
        """
        Store a message in the current conversation.
        """

        if role not in {
            "user",
            "assistant",
            "system",
        }:
            raise ValueError(
                "role must be 'user', 'assistant', or 'system'."
            )

        if not content:
            raise ValueError(
                "Message content cannot be empty."
            )

        self.sequence_number += 1

        occurred_at = datetime.now(
            timezone.utc
        ).isoformat()

        query = """
        INSERT INTO conversation_messages (
            message_id,
            conversation_id,
            user_id,
            role,
            content,
            sequence_number,
            occurred_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        RETURNING message_id;
        """

        return execute_read_write(
            self._parameterize(
                query,
                (
                    str(uuid.uuid4()),
                    self.session_id,
                    self.user_id,
                    role,
                    content,
                    self.sequence_number,
                    occurred_at,
                ),
            )
        )

    def add_user_message(self, content: str):
        return self.add_message(
            "user",
            content,
        )

    def add_assistant_message(self, content: str):
        return self.add_message(
            "assistant",
            content,
        )

    def get_history(self):
        """
        Retrieve all messages belonging to this conversation.
        """

        query = """
        SELECT
            message_id,
            conversation_id,
            user_id,
            role,
            content,
            sequence_number,
            occurred_at,
            created_at,
            metadata
        FROM conversation_messages
        WHERE conversation_id = %s
        ORDER BY sequence_number;
        """

        return execute_read_only(
            self._parameterize(
                query,
                (self.session_id,),
            )
        )

    def end(self):
        """
        Mark the current conversation as completed.
        """

        ended_at = datetime.now(
            timezone.utc
        ).isoformat()

        query = """
        UPDATE conversations
        SET
            ended_at = %s,
            updated_at = %s
        WHERE conversation_id = %s;
        """

        return execute_read_write(
            self._parameterize(
                query,
                (
                    ended_at,
                    ended_at,
                    self.session_id,
                ),
            )
        )

    def get_session_info(self):
        return {
            "conversation_id": self.session_id,
            "user_id": self.user_id,
            "topic": self.topic,
        }

    @staticmethod
    def _parameterize(
        query: str,
        parameters: tuple,
    ):
        """
        Convert parameters into SQL-safe literals.
        """

        for parameter in parameters:

            if parameter is None:
                value = "NULL"

            elif isinstance(parameter, str):
                value = "'{}'".format(
                    parameter.replace("'", "''")
                )

            else:
                value = str(parameter)

            query = query.replace(
                "%s",
                value,
                1,
            )

        return query