CREATE OR REPLACE FUNCTION ignore_palette_hex_hashtag()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.normalized_hashtag ~ '^[a-f0-9]{6}$' THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ignore_palette_hex_hashtag
    ON channel_post_hashtags;

CREATE TRIGGER trg_ignore_palette_hex_hashtag
BEFORE INSERT OR UPDATE ON channel_post_hashtags
FOR EACH ROW
EXECUTE FUNCTION ignore_palette_hex_hashtag();

DELETE FROM channel_post_hashtags
WHERE normalized_hashtag ~ '^[a-f0-9]{6}$';
