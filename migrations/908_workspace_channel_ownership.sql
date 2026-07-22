CREATE OR REPLACE FUNCTION enforce_workspace_channel_owner()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    conflicting_workspace_id BIGINT;
BEGIN
    PERFORM pg_advisory_xact_lock(NEW.chat_id);

    SELECT workspace_id
    INTO conflicting_workspace_id
    FROM workspace_channels
    WHERE chat_id = NEW.chat_id
      AND workspace_id <> NEW.workspace_id
    LIMIT 1;

    IF conflicting_workspace_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Telegram chat % is already connected to workspace %',
            NEW.chat_id,
            conflicting_workspace_id
            USING ERRCODE = '23505';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_workspace_channel_owner
    ON workspace_channels;

CREATE TRIGGER trg_workspace_channel_owner
BEFORE INSERT OR UPDATE OF workspace_id, chat_id
ON workspace_channels
FOR EACH ROW
EXECUTE FUNCTION enforce_workspace_channel_owner();

CREATE INDEX IF NOT EXISTS idx_workspace_channels_chat_owner
    ON workspace_channels (chat_id, workspace_id, kind);
