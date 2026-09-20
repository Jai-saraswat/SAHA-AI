from typing import Any

from API.postgres import (
    execute_read_only,
    execute_read_write,
    get_conversation,
    get_message,
    update_conversation,
    delete_conversation,
)


# =====================================================================
# CONSTANTS
# =====================================================================

VALID_SENDER_TYPES = {
    "client",
    "therapist",
}

VALID_CONVERSATION_STATUSES = {
    "active",
    "paused",
    "ended",
}


# =====================================================================
# CONVERSATION SESSION
# =====================================================================

class ConversationSession:
    """
    Domain/session layer for a shared client-therapist conversation.

    SAHA is NOT a conversation sender.

    Valid senders are only:

        client
        therapist

    The relationship determines which user is allowed to use
    each sender type.
    """

    # -----------------------------------------------------------------
    # INITIALIZATION
    # -----------------------------------------------------------------

    def __init__(
        self,
        relationship_id: str | None = None,
        conversation_id: str | None = None,
        topic: str | None = None,
    ):
        if not relationship_id and not conversation_id:
            raise ValueError(
                "Either relationship_id or conversation_id "
                "must be provided."
            )

        if relationship_id and conversation_id:
            raise ValueError(
                "Provide either relationship_id or conversation_id, "
                "not both."
            )

        self.relationship_id = relationship_id
        self.conversation_id = conversation_id
        self.topic = topic

        self.client_user_id: str | None = None
        self.therapist_user_id: str | None = None

        self.status: str | None = None
        self.started_at = None
        self.ended_at = None

        self._next_sequence_number = 1

        # -------------------------------------------------------------
        # Existing conversation
        # -------------------------------------------------------------

        if conversation_id:

            self._load_existing_conversation(
                conversation_id
            )

        # -------------------------------------------------------------
        # New conversation
        # -------------------------------------------------------------

        else:

            self._load_relationship(
                relationship_id
            )

    # =================================================================
    # LOADING
    # =================================================================

    def _load_existing_conversation(
        self,
        conversation_id: str,
    ):
        """
        Load an existing conversation and its relationship context.
        """

        conversation = get_conversation(
            conversation_id
        )

        if conversation is None:
            raise ValueError(
                "Conversation not found."
            )

        self.conversation_id = (
            conversation["conversation_id"]
        )

        self.relationship_id = (
            conversation["relationship_id"]
        )

        self.client_user_id = (
            conversation["client_user_id"]
        )

        self.therapist_user_id = (
            conversation["therapist_user_id"]
        )

        self.topic = conversation["topic"]

        self.status = conversation["status"]

        self.started_at = conversation[
            "started_at"
        ]

        self.ended_at = conversation[
            "ended_at"
        ]

        # -------------------------------------------------------------
        # Determine next sequence number.
        #
        # Deleted messages retain their sequence number, therefore
        # the maximum sequence number must include deleted rows.
        # -------------------------------------------------------------

        query = """
        SELECT
            COALESCE(
                MAX(sequence_number),
                0
            ) AS max_sequence_number

        FROM conversation_messages

        WHERE
            conversation_id = %s;
        """

        result = execute_read_only(
            query,
            (
                self.conversation_id,
            ),
        )

        max_sequence_number = int(
            result[0]["max_sequence_number"]
        )

        self._next_sequence_number = (
            max_sequence_number + 1
        )

    def _load_relationship(
        self,
        relationship_id: str,
    ):
        """
        Load relationship participants for a new conversation.
        """

        query = """
        SELECT
            relationship_id,
            client_user_id,
            therapist_user_id,
            status,
            started_at,
            ended_at

        FROM user_relationships

        WHERE
            relationship_id = %s
            AND deleted_at IS NULL;
        """

        result = execute_read_only(
            query,
            (
                relationship_id,
            ),
        )

        if not result:
            raise ValueError(
                "Relationship not found."
            )

        relationship = result[0]

        relationship_status = (
            relationship["status"]
        )

        if relationship_status == "ended":
            raise ValueError(
                "Cannot create a conversation "
                "for an ended relationship."
            )

        self.relationship_id = str(
            relationship[
                "relationship_id"
            ]
        )

        self.client_user_id = str(
            relationship[
                "client_user_id"
            ]
        )

        self.therapist_user_id = str(
            relationship[
                "therapist_user_id"
            ]
        )

    # =================================================================
    # CREATE
    # =================================================================

    def create(self):
        """
        Create the conversation.

        Returns the created conversation ID.
        """

        if self.conversation_id:
            raise ValueError(
                "Conversation already exists."
            )

        if not self.relationship_id:
            raise ValueError(
                "relationship_id is required."
            )

        query = """
        INSERT INTO conversations (
            relationship_id,
            topic,
            status,
            started_at
        )

        VALUES (
            %s,
            %s,
            'active',
            NOW()
        )

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
            (
                self.relationship_id,
                self.topic,
            ),
        )

        if not result:
            raise RuntimeError(
                "Failed to create conversation."
            )

        conversation = result[0]

        self.conversation_id = str(
            conversation[
                "conversation_id"
            ]
        )

        self.relationship_id = str(
            conversation[
                "relationship_id"
            ]
        )

        self.status = conversation[
            "status"
        ]

        self.started_at = conversation[
            "started_at"
        ]

        self.ended_at = conversation[
            "ended_at"
        ]

        self._next_sequence_number = 1

        return self.conversation_id

    # =================================================================
    # MESSAGE CREATION
    # =================================================================

    def add_message(
        self,
        sender_user_id: str,
        sender_type: str,
        content: str,
        occurred_at=None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Add a client or therapist message.

        Sender identity is validated against the relationship.

        SAHA cannot be inserted as a sender.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        sender_user_id = str(
            sender_user_id
        ).strip()

        if not sender_user_id:
            raise ValueError(
                "sender_user_id cannot be empty."
            )

        sender_type = str(
            sender_type
        ).strip().lower()

        if sender_type not in VALID_SENDER_TYPES:
            raise ValueError(
                "sender_type must be 'client' "
                "or 'therapist'."
            )

        content = str(
            content
        ).strip()

        if not content:
            raise ValueError(
                "Message content cannot be empty."
            )

        # -------------------------------------------------------------
        # Conversation status
        # -------------------------------------------------------------

        if self.status == "ended":
            raise ValueError(
                "Cannot add a message to an ended conversation."
            )

        if self.status == "paused":
            raise ValueError(
                "Cannot add a message to a paused conversation."
            )

        # -------------------------------------------------------------
        # Validate sender against relationship
        # -------------------------------------------------------------

        if sender_type == "client":

            if sender_user_id != self.client_user_id:
                raise ValueError(
                    "Sender does not match the client "
                    "associated with this conversation."
                )

        elif sender_type == "therapist":

            if sender_user_id != self.therapist_user_id:
                raise ValueError(
                    "Sender does not match the therapist "
                    "associated with this conversation."
                )

        # -------------------------------------------------------------
        # Metadata
        # -------------------------------------------------------------

        if metadata is None:
            metadata = {}

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "metadata must be an object."
            )

        # -------------------------------------------------------------
        # Sequence number
        # -------------------------------------------------------------

        sequence_number = (
            self._next_sequence_number
        )

        # -------------------------------------------------------------
        # Insert message
        # -------------------------------------------------------------

        query = """
        INSERT INTO conversation_messages (
            conversation_id,
            sender_user_id,
            sender_type,
            content,
            sequence_number,
            occurred_at,
            metadata
        )

        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            COALESCE(%s, NOW()),
            %s
        )

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

        import psycopg2.extras

        result = execute_read_write(
            query,
            (
                self.conversation_id,
                sender_user_id,
                sender_type,
                content,
                sequence_number,
                occurred_at,
                psycopg2.extras.Json(
                    metadata
                ),
            ),
        )

        if not result:
            raise RuntimeError(
                "Failed to create conversation message."
            )

        message = result[0]

        # -------------------------------------------------------------
        # Advance local sequence state
        # -------------------------------------------------------------

        self._next_sequence_number = (
            sequence_number + 1
        )

        # -------------------------------------------------------------
        # Touch conversation
        # -------------------------------------------------------------

        self._touch_conversation()

        return self._normalize_message(
            message
        )

    # =================================================================
    # MESSAGE CONVENIENCE METHODS
    # =================================================================

    def add_client_message(
        self,
        content: str,
        occurred_at=None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Add a message from the client.
        """

        if not self.client_user_id:
            raise ValueError(
                "Client user is not available."
            )

        return self.add_message(
            sender_user_id=self.client_user_id,
            sender_type="client",
            content=content,
            occurred_at=occurred_at,
            metadata=metadata,
        )

    def add_therapist_message(
        self,
        content: str,
        occurred_at=None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Add a message from the therapist.
        """

        if not self.therapist_user_id:
            raise ValueError(
                "Therapist user is not available."
            )

        return self.add_message(
            sender_user_id=self.therapist_user_id,
            sender_type="therapist",
            content=content,
            occurred_at=occurred_at,
            metadata=metadata,
        )

    # =================================================================
    # HISTORY
    # =================================================================

    def get_history(
        self,
        limit: int | None = None,
        include_deleted: bool = False,
    ):
        """
        Retrieve chronological conversation history.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        if limit is not None:

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

        deleted_condition = (
            ""
            if include_deleted
            else "AND deleted_at IS NULL"
        )

        limit_clause = (
            "LIMIT %s"
            if limit is not None
            else ""
        )

        parameters: list[Any] = [
            self.conversation_id
        ]

        if limit is not None:
            parameters.append(limit)

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
            conversation_id = %s
            {deleted_condition}

        ORDER BY
            sequence_number ASC

        {limit_clause};
        """

        result = execute_read_only(
            query,
            tuple(parameters),
        )

        return [
            self._normalize_message(
                message
            )
            for message in result
        ]

    def get_client_messages(
        self,
        limit: int | None = None,
        include_deleted: bool = False,
    ):
        """
        Retrieve client messages.
        """

        return self._get_messages_by_sender(
            sender_type="client",
            limit=limit,
            include_deleted=include_deleted,
        )

    def get_therapist_messages(
        self,
        limit: int | None = None,
        include_deleted: bool = False,
    ):
        """
        Retrieve therapist messages.
        """

        return self._get_messages_by_sender(
            sender_type="therapist",
            limit=limit,
            include_deleted=include_deleted,
        )

    def _get_messages_by_sender(
        self,
        sender_type: str,
        limit: int | None = None,
        include_deleted: bool = False,
    ):
        """
        Internal sender-specific message retrieval.
        """

        if sender_type not in VALID_SENDER_TYPES:
            raise ValueError(
                "Invalid sender type."
            )

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        if limit is not None:

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

        deleted_condition = (
            ""
            if include_deleted
            else "AND deleted_at IS NULL"
        )

        limit_clause = (
            "LIMIT %s"
            if limit is not None
            else ""
        )

        parameters: list[Any] = [
            self.conversation_id,
            sender_type,
        ]

        if limit is not None:
            parameters.append(limit)

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
            conversation_id = %s
            AND sender_type = %s
            {deleted_condition}

        ORDER BY
            sequence_number ASC

        {limit_clause};
        """

        result = execute_read_only(
            query,
            tuple(parameters),
        )

        return [
            self._normalize_message(
                message
            )
            for message in result
        ]

    # =================================================================
    # SINGLE MESSAGE
    # =================================================================

    def get_message(
        self,
        message_id: str,
        include_deleted: bool = False,
    ):
        """
        Retrieve one message.
        """

        message = get_message(
            message_id,
            include_deleted=include_deleted,
        )

        if message is None:
            return None

        # -------------------------------------------------------------
        # Ensure message belongs to this conversation
        # -------------------------------------------------------------

        if (
            self.conversation_id
            and message["conversation_id"]
            != self.conversation_id
        ):
            raise ValueError(
                "Message does not belong to this conversation."
            )

        return self._normalize_message(
            message
        )

    # =================================================================
    # EDIT MESSAGE
    # =================================================================

    def edit_message(
        self,
        message_id: str,
        content: str,
    ):
        """
        Edit one message belonging to this conversation.
        """

        message = self.get_message(
            message_id
        )

        if message is None:
            raise ValueError(
                "Message not found."
            )

        updated = self._edit_message_direct(
            message_id,
            content,
        )

        if not updated:
            raise ValueError(
                "Message could not be edited."
            )

        return self._normalize_message(
            updated[0]
        )

    def _edit_message_direct(
        self,
        message_id: str,
        content: str,
    ):
        """
        Internal edit operation.

        Kept here rather than importing a second abstraction so
        conversation ownership can be validated before mutation.
        """

        content = str(
            content
        ).strip()

        if not content:
            raise ValueError(
                "Message content cannot be empty."
            )

        query = """
        UPDATE conversation_messages

        SET
            content = %s,
            edited_at = NOW()

        WHERE
            message_id = %s
            AND conversation_id = %s
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

        return execute_read_write(
            query,
            (
                content,
                message_id,
                self.conversation_id,
            ),
        )

    # =================================================================
    # DELETE MESSAGE
    # =================================================================

    def delete_message(
        self,
        message_id: str,
    ):
        """
        Soft-delete one message belonging to this conversation.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        message = get_message(
            message_id
        )

        if message is None:
            raise ValueError(
                "Message not found."
            )

        if (
            message["conversation_id"]
            != self.conversation_id
        ):
            raise ValueError(
                "Message does not belong to this conversation."
            )

        query = """
        UPDATE conversation_messages

        SET
            deleted_at = NOW()

        WHERE
            message_id = %s
            AND conversation_id = %s
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
                message_id,
                self.conversation_id,
            ),
        )

        if not result:
            raise ValueError(
                "Message could not be deleted."
            )

        return self._normalize_message(
            result[0]
        )

    # =================================================================
    # TOPIC
    # =================================================================

    def update_topic(
        self,
        topic: str | None,
    ):
        """
        Update conversation topic.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        result = update_conversation(
            self.conversation_id,
            topic=topic,
        )

        if not result:
            raise ValueError(
                "Conversation not found."
            )

        conversation = result[0]

        self.topic = conversation[
            "topic"
        ]

        self.status = conversation[
            "status"
        ]

        return conversation

    # =================================================================
    # STATUS
    # =================================================================

    def update_status(
        self,
        status: str,
    ):
        """
        Change conversation status.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        status = str(
            status
        ).strip().lower()

        if status not in VALID_CONVERSATION_STATUSES:
            raise ValueError(
                "Invalid conversation status."
            )

        if (
            self.status == "ended"
            and status != "ended"
        ):
            raise ValueError(
                "An ended conversation cannot be reopened."
            )

        result = update_conversation(
            self.conversation_id,
            status=status,
        )

        if not result:
            raise ValueError(
                "Conversation not found."
            )

        conversation = result[0]

        self.status = conversation[
            "status"
        ]

        self.ended_at = conversation[
            "ended_at"
        ]

        return conversation

    # =================================================================
    # PAUSE
    # =================================================================

    def pause(self):
        """
        Pause the conversation.
        """

        if self.status == "ended":
            raise ValueError(
                "Ended conversation cannot be paused."
            )

        return self.update_status(
            "paused"
        )

    # =================================================================
    # RESUME
    # =================================================================

    def resume(self):
        """
        Resume a paused conversation.
        """

        if self.status == "ended":
            raise ValueError(
                "Ended conversation cannot be resumed."
            )

        return self.update_status(
            "active"
        )

    # =================================================================
    # END
    # =================================================================

    def end(self):
        """
        End the conversation.

        Ending is terminal.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        if self.status == "ended":

            return {
                "conversation_id":
                    self.conversation_id,
                "status": "ended",
                "already_ended": True,
            }

        result = update_conversation(
            self.conversation_id,
            status="ended",
        )

        if not result:
            raise ValueError(
                "Conversation not found."
            )

        conversation = result[0]

        self.status = "ended"

        self.ended_at = conversation[
            "ended_at"
        ]

        return conversation

    # =================================================================
    # DELETE
    # =================================================================

    def delete(self):
        """
        Soft-delete the conversation.
        """

        if not self.conversation_id:
            raise ValueError(
                "Conversation has not been created."
            )

        result = delete_conversation(
            self.conversation_id
        )

        if not result:
            raise ValueError(
                "Conversation not found."
            )

        return result[0]

    # =================================================================
    # SESSION INFO
    # =================================================================

    def get_session_info(self):
        """
        Return the current conversation context.
        """

        return {
            "conversation_id":
                self.conversation_id,

            "relationship_id":
                self.relationship_id,

            "client_user_id":
                self.client_user_id,

            "therapist_user_id":
                self.therapist_user_id,

            "topic":
                self.topic,

            "status":
                self.status,

            "started_at":
                self.started_at,

            "ended_at":
                self.ended_at,
        }

    # =================================================================
    # CONVERSATION TOUCH
    # =================================================================

    def _touch_conversation(self):
        """
        Update conversation.updated_at after message activity.

        This is intentionally internal.
        """

        if not self.conversation_id:
            return

        query = """
        UPDATE conversations

        SET
            updated_at = NOW()

        WHERE
            conversation_id = %s
            AND deleted_at IS NULL;
        """

        execute_read_write(
            query,
            (
                self.conversation_id,
            ),
        )

    # =================================================================
    # NORMALIZATION
    # =================================================================

    @staticmethod
    def _normalize_message(
        message: dict[str, Any],
    ):
        """
        Normalize UUID fields returned by PostgreSQL.
        """

        message = dict(
            message
        )

        for field in (
            "message_id",
            "conversation_id",
            "sender_user_id",
        ):

            if message.get(field) is not None:

                message[field] = str(
                    message[field]
                )

        return message