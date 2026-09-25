-- Supabase PostgreSQL Schema Migration for HTH2.0 / QueryLens
-- Preserves all domain models, conversation history, user sessions, chat files, and datasets.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. AUTH USERS
CREATE TABLE IF NOT EXISTS public.auth_users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_users_email ON public.auth_users (LOWER(email));

-- 2. AUTH SESSIONS
CREATE TABLE IF NOT EXISTS public.auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public.auth_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON public.auth_sessions (expires_at);

-- 3. CONVERSATIONS / CHATS
CREATE TABLE IF NOT EXISTS public.conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    dataset_id TEXT,
    owner_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON public.conversations (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated ON public.conversations (owner_id, updated_at DESC);

-- 4. MESSAGES
CREATE TABLE IF NOT EXISTS public.messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    result_json JSONB,
    visualization_json JSONB,
    intent_json JSONB,
    query_spec_json JSONB,
    file_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON public.messages (conversation_id, created_at ASC);

-- 5. CHAT FILES (File metadata associated with a chat session)
CREATE TABLE IF NOT EXISTS public.chat_files (
    file_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, file_id)
);

-- 6. DATASETS (Master dataset registry)
CREATE TABLE IF NOT EXISTS public.datasets (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    chat_id TEXT REFERENCES public.conversations(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_filename TEXT,
    processed_filename TEXT,
    file_type TEXT NOT NULL,
    file_size BIGINT DEFAULT 0,
    row_count INTEGER DEFAULT 0,
    column_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'processed',
    schema_json JSONB,
    profile_json JSONB,
    cleaning_report_json JSONB,
    metadata_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_datasets_chat_id ON public.datasets (chat_id);
CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON public.datasets (user_id);

-- 7. DATASET FILES (File metadata linked to Supabase storage paths)
CREATE TABLE IF NOT EXISTS public.dataset_files (
    id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES public.datasets(id) ON DELETE CASCADE,
    chat_id TEXT REFERENCES public.conversations(id) ON DELETE CASCADE,
    user_id TEXT,
    storage_bucket TEXT NOT NULL DEFAULT 'datasets',
    storage_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_role TEXT NOT NULL, -- 'raw', 'processed', 'metadata', 'artifact'
    file_size BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dataset_files_dataset_id ON public.dataset_files (dataset_id);
CREATE INDEX IF NOT EXISTS idx_dataset_files_chat_id ON public.dataset_files (chat_id);

-- 8. DATASET FILE CONTENTS (Supabase Storage binary content backing store)
CREATE TABLE IF NOT EXISTS public.dataset_file_contents (
    storage_bucket TEXT NOT NULL DEFAULT 'datasets',
    storage_path TEXT NOT NULL,
    content BYTEA NOT NULL,
    content_type TEXT DEFAULT 'application/octet-stream',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (storage_bucket, storage_path)
);
