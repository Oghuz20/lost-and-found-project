-- Schema for the Smart Lost & Found service.
-- Owner: Person A.
--
-- Idempotent: every statement uses IF NOT EXISTS, so this file is safe to
-- run on every process startup (see `src.storage.db.init_schema`) without
-- a full migration framework. If the schema needs to evolve later, switch
-- this to Alembic migrations rather than editing table shapes in place.

CREATE TABLE IF NOT EXISTS items (
    id              BIGSERIAL PRIMARY KEY,
    status          TEXT NOT NULL CHECK (status IN ('lost', 'found', 'matched', 'closed')),
    user_text       TEXT NOT NULL DEFAULT '',
    image_path      TEXT NOT NULL,
    -- Flattened `ai.ItemDescription` (object_class, colors, brand, ...).
    vlm_description JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Packed float32 buffer from `ai.embed`; NULL until embedding runs.
    embedding       BYTEA,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items (status);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON items (created_at);

CREATE TABLE IF NOT EXISTS matches (
    id             BIGSERIAL PRIMARY KEY,
    lost_item_id   BIGINT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    found_item_id  BIGINT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    score          DOUBLE PRECISION NOT NULL,
    reason         TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_matches_lost_item ON matches (lost_item_id);
CREATE INDEX IF NOT EXISTS idx_matches_found_item ON matches (found_item_id);
