CREATE TABLE IF NOT EXISTS character_story_links (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    story_id BIGINT NOT NULL REFERENCES character_stories(id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_by BIGINT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (character_id, story_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_character_story_links_one_primary
    ON character_story_links(character_id)
    WHERE is_primary;

CREATE INDEX IF NOT EXISTS idx_character_story_links_story
    ON character_story_links(story_id, character_id);

INSERT INTO character_story_links (character_id, story_id, is_primary)
SELECT c.id, c.story_id, TRUE
FROM characters AS c
JOIN character_stories AS s ON s.id = c.story_id
WHERE c.story_id IS NOT NULL
  AND c.universe = s.universe
ON CONFLICT (character_id, story_id) DO UPDATE
SET is_primary = TRUE;

WITH ranked AS (
    SELECT
        character_id,
        story_id,
        ROW_NUMBER() OVER (
            PARTITION BY character_id
            ORDER BY is_primary DESC, assigned_at, story_id
        ) AS position
    FROM character_story_links
)
UPDATE character_story_links AS link
SET is_primary = (ranked.position = 1)
FROM ranked
WHERE link.character_id = ranked.character_id
  AND link.story_id = ranked.story_id;

UPDATE characters AS c
SET story_id = selected.story_id
FROM (
    SELECT character_id, story_id
    FROM character_story_links
    WHERE is_primary
) AS selected
WHERE c.id = selected.character_id
  AND c.story_id IS DISTINCT FROM selected.story_id;
