CREATE OR REPLACE FUNCTION sync_character_name_alias()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    compact_name TEXT;
BEGIN
    compact_name := LOWER(
        REGEXP_REPLACE(NEW.name, '[^[:alnum:]]+', '', 'g')
    );
    IF compact_name = '' THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        DELETE FROM character_aliases
        WHERE character_id = NEW.id
          AND source = 'name';
    END IF;

    INSERT INTO character_aliases (
        character_id,
        alias,
        normalized_alias,
        source
    )
    VALUES (NEW.id, NEW.name, compact_name, 'name')
    ON CONFLICT (normalized_alias) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_character_name_alias ON characters;

CREATE TRIGGER trg_sync_character_name_alias
AFTER INSERT OR UPDATE OF name ON characters
FOR EACH ROW
EXECUTE FUNCTION sync_character_name_alias();
