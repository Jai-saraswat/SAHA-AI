-- SAHA - Initial Conversation Persistence Schema
-- PostgreSQL
--
-- Purpose:
--   Store the original conversation data received by SAHA.
--   This is the initial persistence layer only.
--
-- Raw conversation storage is independent of downstream memory,
-- clinical analysis, NLP analysis, embeddings, and other derived data.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- USERS
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CONVERSATIONS
CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CONVERSATION MESSAGES
CREATE TABLE conversation_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(conversation_id),
    user_id UUID NOT NULL REFERENCES users(user_id),
    role VARCHAR(20) NOT NULL
        CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);

-- INDEXES
CREATE INDEX idx_conversations_user_id
    ON conversations(user_id);

CREATE INDEX idx_messages_conversation
    ON conversation_messages(conversation_id, sequence_number);

CREATE INDEX idx_messages_user
    ON conversation_messages(user_id, occurred_at);

-- A message sequence number is unique within a conversation.
CREATE UNIQUE INDEX uq_message_conversation_sequence
    ON conversation_messages(conversation_id, sequence_number);