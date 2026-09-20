-- ============================================================
-- SAHA DATABASE SCHEMA
-- Therapist-controlled AI architecture
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    username VARCHAR(100) NOT NULL UNIQUE,

    display_name VARCHAR(255),

    email VARCHAR(255),

    psychological_traits JSONB NOT NULL
        DEFAULT '{"facts": []}'::jsonb,

    preferences JSONB NOT NULL
        DEFAULT '{"items": []}'::jsonb,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    deleted_at TIMESTAMPTZ,

    CONSTRAINT users_psychological_traits_object
        CHECK (
            jsonb_typeof(psychological_traits) = 'object'
        ),

    CONSTRAINT users_preferences_object
        CHECK (
            jsonb_typeof(preferences) = 'object'
        ),

    CONSTRAINT users_metadata_object
        CHECK (
            jsonb_typeof(metadata) = 'object'
        )
);


-- ============================================================
-- USER ROLES
-- ============================================================

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    role VARCHAR(30) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_id, role),

    CONSTRAINT user_roles_role_check
        CHECK (
            role IN (
                'client',
                'therapist',
                'admin'
            )
        )
);


-- ============================================================
-- CLIENT / THERAPIST RELATIONSHIPS
-- ============================================================

CREATE TABLE IF NOT EXISTS user_relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    client_user_id UUID NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    therapist_user_id UUID NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    status VARCHAR(30) NOT NULL DEFAULT 'active',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    ended_at TIMESTAMPTZ,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    deleted_at TIMESTAMPTZ,

    CONSTRAINT user_relationships_status_check
        CHECK (
            status IN (
                'active',
                'paused',
                'ended'
            )
        ),

    CONSTRAINT user_relationships_different_users
        CHECK (
            client_user_id <> therapist_user_id
        ),

    CONSTRAINT user_relationships_metadata_object
        CHECK (
            jsonb_typeof(metadata) = 'object'
        ),

    CONSTRAINT user_relationships_dates_check
        CHECK (
            ended_at IS NULL
            OR ended_at >= started_at
        )
);


-- ============================================================
-- THERAPIST-CONTROLLED AI SETTINGS
-- ============================================================

CREATE TABLE IF NOT EXISTS relationship_ai_settings (
    relationship_id UUID PRIMARY KEY
        REFERENCES user_relationships(relationship_id)
        ON DELETE CASCADE,

    ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    analysis_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    strategy_planner_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    therapist_assistance_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    client_response_generation_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    real_time_analysis_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    post_conversation_analysis_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    allowed_data_sources JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    restricted_data_sources JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    allowed_capabilities JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    restricted_capabilities JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    strategy_constraints JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    custom_instructions TEXT,

    configuration JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT relationship_ai_settings_allowed_sources_array
        CHECK (
            jsonb_typeof(allowed_data_sources) = 'array'
        ),

    CONSTRAINT relationship_ai_settings_restricted_sources_array
        CHECK (
            jsonb_typeof(restricted_data_sources) = 'array'
        ),

    CONSTRAINT relationship_ai_settings_allowed_capabilities_array
        CHECK (
            jsonb_typeof(allowed_capabilities) = 'array'
        ),

    CONSTRAINT relationship_ai_settings_restricted_capabilities_array
        CHECK (
            jsonb_typeof(restricted_capabilities) = 'array'
        ),

    CONSTRAINT relationship_ai_settings_strategy_object
        CHECK (
            jsonb_typeof(strategy_constraints) = 'object'
        ),

    CONSTRAINT relationship_ai_settings_configuration_object
        CHECK (
            jsonb_typeof(configuration) = 'object'
        )
);


-- ============================================================
-- CONVERSATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    relationship_id UUID NOT NULL
        REFERENCES user_relationships(relationship_id)
        ON DELETE RESTRICT,

    topic VARCHAR(255),

    status VARCHAR(30) NOT NULL DEFAULT 'active',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    ended_at TIMESTAMPTZ,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    deleted_at TIMESTAMPTZ,

    CONSTRAINT conversations_status_check
        CHECK (
            status IN (
                'active',
                'paused',
                'ended',
                'archived'
            )
        ),

    CONSTRAINT conversations_metadata_object
        CHECK (
            jsonb_typeof(metadata) = 'object'
        ),

    CONSTRAINT conversations_dates_check
        CHECK (
            ended_at IS NULL
            OR ended_at >= started_at
        )
);


-- ============================================================
-- CONVERSATION MESSAGES
-- ============================================================

CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    conversation_id UUID NOT NULL
        REFERENCES conversations(conversation_id)
        ON DELETE RESTRICT,

    sender_user_id UUID NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    sender_type VARCHAR(30) NOT NULL,

    content TEXT NOT NULL,

    sequence_number INTEGER NOT NULL,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    edited_at TIMESTAMPTZ,

    deleted_at TIMESTAMPTZ,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    CONSTRAINT conversation_messages_sender_type_check
        CHECK (
            sender_type IN (
                'client',
                'therapist'
            )
        ),

    CONSTRAINT conversation_messages_sequence_positive
        CHECK (
            sequence_number > 0
        ),

    CONSTRAINT conversation_messages_content_not_empty
        CHECK (
            length(trim(content)) > 0
        ),

    CONSTRAINT conversation_messages_metadata_object
        CHECK (
            jsonb_typeof(metadata) = 'object'
        ),

    UNIQUE (
        conversation_id,
        sequence_number
    )
);


-- ============================================================
-- GRAPHITI MESSAGE BUFFER
-- ============================================================

CREATE TABLE IF NOT EXISTS graphiti_message_buffer (
    conversation_id UUID PRIMARY KEY
        REFERENCES conversations(conversation_id)
        ON DELETE CASCADE,

    messages JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT graphiti_message_buffer_messages_array
        CHECK (
            jsonb_typeof(messages) = 'array'
        )
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_users_updated_at
    ON users(updated_at);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_active
    ON users(user_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_psychological_traits
    ON users USING GIN (psychological_traits);

CREATE INDEX IF NOT EXISTS idx_users_preferences
    ON users USING GIN (preferences);


CREATE INDEX IF NOT EXISTS idx_user_roles_role
    ON user_roles(role);


CREATE INDEX IF NOT EXISTS idx_relationships_client
    ON user_relationships(client_user_id);

CREATE INDEX IF NOT EXISTS idx_relationships_therapist
    ON user_relationships(therapist_user_id);

CREATE INDEX IF NOT EXISTS idx_relationships_status
    ON user_relationships(status);

CREATE INDEX IF NOT EXISTS idx_relationships_active
    ON user_relationships(relationship_id)
    WHERE deleted_at IS NULL;


CREATE INDEX IF NOT EXISTS idx_conversations_relationship
    ON conversations(relationship_id);

CREATE INDEX IF NOT EXISTS idx_conversations_status
    ON conversations(status);

CREATE INDEX IF NOT EXISTS idx_conversations_started_at
    ON conversations(started_at);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
    ON conversations(updated_at);

CREATE INDEX IF NOT EXISTS idx_conversations_active
    ON conversations(conversation_id)
    WHERE deleted_at IS NULL;


CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON conversation_messages(conversation_id);

CREATE INDEX IF NOT EXISTS idx_messages_sender
    ON conversation_messages(sender_user_id);

CREATE INDEX IF NOT EXISTS idx_messages_sender_type
    ON conversation_messages(sender_type);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_time
    ON conversation_messages(
        conversation_id,
        occurred_at
    );

CREATE INDEX IF NOT EXISTS idx_messages_active
    ON conversation_messages(message_id)
    WHERE deleted_at IS NULL;


CREATE INDEX IF NOT EXISTS idx_graphiti_buffer_updated_at
    ON graphiti_message_buffer(updated_at);


-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE users IS
    'Human users of the SAHA platform.';

COMMENT ON COLUMN users.psychological_traits IS
    'Persistent user-level psychological and behavioral facts.';

COMMENT ON COLUMN users.preferences IS
    'Persistent user-level preferences.';

COMMENT ON TABLE user_roles IS
    'Platform roles assigned to human users.';

COMMENT ON TABLE user_relationships IS
    'Client-therapist relationship connecting users and their conversations.';

COMMENT ON TABLE relationship_ai_settings IS
    'Therapist-controlled AI configuration for a specific client-therapist relationship.';

COMMENT ON TABLE conversations IS
    'Conversation belonging to a client-therapist relationship.';

COMMENT ON TABLE conversation_messages IS
    'Canonical client-therapist conversation stream.';

COMMENT ON COLUMN conversation_messages.edited_at IS
    'Time when the message content was last edited.';

COMMENT ON COLUMN conversation_messages.deleted_at IS
    'Soft deletion timestamp. NULL means the message is active.';

COMMENT ON TABLE graphiti_message_buffer IS
    'Temporary persistent buffer for Graphiti ingestion.';