import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from graphiti_core import Graphiti

from graphiti_core.llm_client.gemini_client import (
    GeminiClient,
    LLMConfig,
)

from graphiti_core.embedder.gemini import (
    GeminiEmbedder,
    GeminiEmbedderConfig,
)

from graphiti_core.cross_encoder.gemini_reranker_client import (
    GeminiRerankerClient,
)

from graphiti_core.nodes import EpisodeType

from graphiti_core.utils.bulk_utils import RawEpisode


# =====================================================================
# ENVIRONMENT
# =====================================================================

load_dotenv()


# =====================================================================
# CONFIGURATION
# =====================================================================

NEO4J_URI = os.getenv(
    "GRAPHITI_NEO4J_URI"
)

NEO4J_USER = os.getenv(
    "GRAPHITI_NEO4J_USER"
)

NEO4J_PASSWORD = os.getenv(
    "GRAPHITI_NEO4J_PASSWORD"
)

GEMINI_API_KEY = os.getenv(
    "GRAPHITI_LLM_API_KEY"
)


# =====================================================================
# MODELS
# =====================================================================

# ---------------------------------------------------------------------
# IMPORTANT:
#
# Keep the Graphiti LLM model explicit.
#
# This is the model currently defined by the workflow.
# ---------------------------------------------------------------------

MODEL = "gemini-3.1-flash-lite"


# ---------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv(
    "GRAPHITI_EMBEDDING_MODEL",
    "gemini-embedding-001",
)


# =====================================================================
# CONFIGURATION VALIDATION
# =====================================================================

def _validate_configuration():
    """
    Validate required Graphiti configuration before initializing
    the client.
    """

    missing = []

    if not NEO4J_URI:
        missing.append(
            "GRAPHITI_NEO4J_URI"
        )

    if not NEO4J_USER:
        missing.append(
            "GRAPHITI_NEO4J_USER"
        )

    if not NEO4J_PASSWORD:
        missing.append(
            "GRAPHITI_NEO4J_PASSWORD"
        )

    if not GEMINI_API_KEY:
        missing.append(
            "GRAPHITI_LLM_API_KEY"
        )

    if missing:

        raise RuntimeError(
            "Missing required Graphiti environment variables: "
            + ", ".join(missing)
        )


# =====================================================================
# GRAPHITI CLIENT
# =====================================================================

_validate_configuration()


llm_client = GeminiClient(
    config=LLMConfig(
        api_key=GEMINI_API_KEY,
        model=MODEL,
        small_model=MODEL,
    )
)


embedder = GeminiEmbedder(
    config=GeminiEmbedderConfig(
        api_key=GEMINI_API_KEY,
        embedding_model=EMBEDDING_MODEL,
    )
)


reranker = GeminiRerankerClient(
    config=LLMConfig(
        api_key=GEMINI_API_KEY,
        model=MODEL,
        small_model=MODEL,
    )
)


graphiti = Graphiti(
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    llm_client=llm_client,
    embedder=embedder,
    cross_encoder=reranker,
)


# =====================================================================
# INITIALIZATION STATE
# =====================================================================

_initialized = False


# =====================================================================
# INITIALIZATION
# =====================================================================

async def _ensure_initialized():
    """
    Initialize Graphiti indices and constraints once.

    This function is intentionally internal.

    The public write/retrieve workflow does not change.
    """

    global _initialized

    if _initialized:
        return

    await graphiti.build_indices_and_constraints()

    _initialized = True


# =====================================================================
# TIMESTAMP NORMALIZATION
# =====================================================================

def _normalize_timestamp(
    timestamp: Any,
    message_id: str,
):
    """
    Convert a supported timestamp value into a timezone-aware
    datetime.

    Supported input:

        None
        datetime
        ISO-8601 string

    Naive datetimes are treated as UTC.
    """

    # -------------------------------------------------------------
    # No timestamp supplied
    # -------------------------------------------------------------

    if timestamp is None:

        timestamp = datetime.now(
            timezone.utc
        )

    # -------------------------------------------------------------
    # ISO timestamp
    # -------------------------------------------------------------

    elif isinstance(
        timestamp,
        str,
    ):

        value = timestamp.strip()

        if not value:

            raise ValueError(
                f"Timestamp for message "
                f"{message_id} cannot be empty."
            )

        try:

            timestamp = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError as exc:

            raise ValueError(
                f"Invalid timestamp for message "
                f"{message_id}: {timestamp}"
            ) from exc

    # -------------------------------------------------------------
    # Datetime
    # -------------------------------------------------------------

    elif not isinstance(
        timestamp,
        datetime,
    ):

        raise ValueError(
            f"Invalid timestamp for message "
            f"{message_id}."
        )

    # -------------------------------------------------------------
    # Ensure timezone awareness
    # -------------------------------------------------------------

    if timestamp.tzinfo is None:

        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    return timestamp


# =====================================================================
# MESSAGE ID
# =====================================================================

def _get_message_id(
    message: dict[str, Any],
    conversation_id: str,
    index: int,
):
    """
    Return the application-level message identifier.

    PostgreSQL message IDs remain application identifiers.

    They are used as Graphiti episode names.

    They are NOT passed as Graphiti UUIDs.
    """

    message_id = message.get(
        "id"
    )

    if message_id is not None:

        message_id = str(
            message_id
        ).strip()

        if message_id:

            return message_id

    # -------------------------------------------------------------
    # Fallback
    #
    # This only applies when a caller provides a message without
    # an application ID.
    # -------------------------------------------------------------

    return (
        f"{conversation_id}_{index}"
    )


# =====================================================================
# WRITE
# =====================================================================

async def write(
    user_id: str,
    conversation_id: str,
    messages: list[dict[str, Any]],
):
    """
    Write conversation messages into Graphiti.

    ---------------------------------------------------------------
    PUBLIC WORKFLOW CONTRACT
    ---------------------------------------------------------------

        write(
            user_id,
            conversation_id,
            messages
        )

    ---------------------------------------------------------------
    MEMORY SCOPE
    ---------------------------------------------------------------

    Graphiti memory remains scoped by:

        group_id = user_id

    Therefore memories from different conversations belonging to
    the same user participate in longitudinal retrieval.

    conversation_id is retained as source/context information.

    ---------------------------------------------------------------
    MESSAGE HANDLING
    ---------------------------------------------------------------

    Each valid message becomes one Graphiti episode.

    PostgreSQL message IDs are used as episode names.

    Graphiti generates the actual episode UUID because:

        uuid=None

    ---------------------------------------------------------------
    IMPORTANT
    ---------------------------------------------------------------

    This function does NOT change the existing Graphiti workflow.
    """

    await _ensure_initialized()

    # =================================================================
    # VALIDATE IDENTIFIERS
    # =================================================================

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


    if conversation_id is None:

        raise ValueError(
            "conversation_id cannot be empty."
        )

    conversation_id = str(
        conversation_id
    ).strip()

    if not conversation_id:

        raise ValueError(
            "conversation_id cannot be empty."
        )


    # =================================================================
    # VALIDATE MESSAGE COLLECTION
    # =================================================================

    if messages is None:

        raise ValueError(
            "messages cannot be None."
        )

    if not isinstance(
        messages,
        list,
    ):

        raise ValueError(
            "messages must be a list."
        )


    # =================================================================
    # EMPTY INPUT
    # =================================================================

    if not messages:

        return {
            "success": True,
            "episodes_written": 0,
            "user_id": user_id,
            "conversation_id": conversation_id,
        }


    # =================================================================
    # BUILD RAW EPISODES
    # =================================================================

    episodes = []

    for index, message in enumerate(
        messages
    ):

        # -------------------------------------------------------------
        # Message structure
        # -------------------------------------------------------------

        if not isinstance(
            message,
            dict,
        ):

            raise ValueError(
                f"Message at index {index} "
                f"must be a dictionary."
            )


        # -------------------------------------------------------------
        # Content
        # -------------------------------------------------------------

        content = message.get(
            "content"
        )

        if content is None:
            continue

        content = str(
            content
        ).strip()

        if not content:
            continue


        # -------------------------------------------------------------
        # Application message ID
        # -------------------------------------------------------------

        message_id = _get_message_id(
            message,
            conversation_id,
            index,
        )


        # -------------------------------------------------------------
        # Timestamp
        # -------------------------------------------------------------

        timestamp = _normalize_timestamp(
            message.get(
                "timestamp"
            ),
            message_id,
        )


        # =============================================================
        # GRAPHITI RAW EPISODE
        # =============================================================
        #
        # uuid MUST remain None.
        #
        # message_id is the application-level episode name.
        #
        # Graphiti generates the actual UUID.
        #
        # =============================================================

        episode = RawEpisode(
            name=message_id,

            uuid=None,

            content=content,

            source_description=(
                f"SAHA conversation "
                f"{conversation_id}"
            ),

            source=EpisodeType.message,

            reference_time=timestamp,
        )

        episodes.append(
            episode
        )


    # =================================================================
    # NO VALID EPISODES
    # =================================================================

    if not episodes:

        return {
            "success": True,
            "episodes_written": 0,
            "user_id": user_id,
            "conversation_id": conversation_id,
        }


    # =================================================================
    # BULK INGESTION
    # =================================================================

    await graphiti.add_episode_bulk(
        bulk_episodes=episodes,
        group_id=user_id,
    )


    # =================================================================
    # RESULT
    # =================================================================

    return {
        "success": True,
        "episodes_written": len(
            episodes
        ),
        "user_id": user_id,
        "conversation_id": conversation_id,
    }


# =====================================================================
# RETRIEVE
# =====================================================================

async def retrieve_related(
    query: str,
    user_id: str,
    num_results: int = 10,
):
    """
    Retrieve longitudinal Graphiti memories for one user.

    ---------------------------------------------------------------
    PUBLIC WORKFLOW CONTRACT
    ---------------------------------------------------------------

        retrieve_related(
            query,
            user_id,
            num_results=10
        )

    ---------------------------------------------------------------
    SEARCH SCOPE
    ---------------------------------------------------------------

    Graphiti search remains restricted to:

        group_ids=[user_id]

    This preserves longitudinal memory across conversations for
    the same user.
    """

    await _ensure_initialized()


    # =================================================================
    # VALIDATE USER
    # =================================================================

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


    # =================================================================
    # VALIDATE QUERY
    # =================================================================

    if query is None:

        return []

    query = str(
        query
    ).strip()

    if not query:

        return []


    # =================================================================
    # VALIDATE RESULT COUNT
    # =================================================================

    if not isinstance(
        num_results,
        int,
    ):

        raise ValueError(
            "num_results must be an integer."
        )

    if isinstance(
        num_results,
        bool,
    ):

        raise ValueError(
            "num_results must be an integer."
        )

    if num_results < 1:

        raise ValueError(
            "num_results must be greater than 0."
        )


    # =================================================================
    # SEARCH
    # =================================================================

    results = await graphiti.search(
        query=query,

        group_ids=[
            user_id
        ],

        num_results=num_results,
    )


    # =================================================================
    # NORMALIZE RESULTS
    # =================================================================

    normalized_results = []

    for result in results:

        normalized_results.append(
            {
                "fact": getattr(
                    result,
                    "fact",
                    None,
                ),

                "valid_at": getattr(
                    result,
                    "valid_at",
                    None,
                ),

                "invalid_at": getattr(
                    result,
                    "invalid_at",
                    None,
                ),

                "source_node_uuid": getattr(
                    result,
                    "source_node_uuid",
                    None,
                ),

                "target_node_uuid": getattr(
                    result,
                    "target_node_uuid",
                    None,
                ),
            }
        )


    return normalized_results