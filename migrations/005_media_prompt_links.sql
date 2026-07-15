ALTER TABLE character_media
    ADD COLUMN IF NOT EXISTS prompt_post_url TEXT;

-- Старую привязку к персонажу безопасно переносим только там, где у персонажа
-- ровно один материал. При нескольких материалах нельзя угадать, к какой
-- картинке относился промт, поэтому владелец назначит его кнопкой вручную.
UPDATE character_media AS cm
SET prompt_post_url = c.prompt_post_url
FROM characters AS c
WHERE c.id = cm.character_id
  AND c.prompt_post_url IS NOT NULL
  AND cm.prompt_post_url IS NULL
  AND (
      SELECT COUNT(*)
      FROM character_media AS only_cm
      WHERE only_cm.character_id = c.id
  ) = 1;

-- Старая привязка к персонажу больше не используется: один персонаж может
-- иметь много изображений и у каждого изображения свой пост с промтом.
UPDATE characters
SET prompt_post_url = NULL
WHERE prompt_post_url IS NOT NULL;
