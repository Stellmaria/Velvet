INSERT INTO tracked_channels (
    chat_id,
    title,
    enabled,
    source_kind,
    parent_channel_id,
    updated_at
)
VALUES (
    -1003802812639,
    'Vᴇʟᴠᴇᴛ Aɴᴀᴛᴏᴍʏ',
    TRUE,
    'channel',
    NULL,
    NOW()
)
ON CONFLICT (chat_id) DO UPDATE
SET source_kind = 'channel',
    parent_channel_id = NULL,
    enabled = TRUE,
    updated_at = NOW();

INSERT INTO tracked_channels (
    chat_id,
    title,
    enabled,
    source_kind,
    parent_channel_id,
    updated_at
)
VALUES (
    -1003859952761,
    'Vᴇʟᴠᴇᴛ Aɴᴀᴛᴏᴍʏ',
    TRUE,
    'discussion',
    -1003802812639,
    NOW()
)
ON CONFLICT (chat_id) DO UPDATE
SET source_kind = 'discussion',
    parent_channel_id = -1003802812639,
    enabled = TRUE,
    updated_at = NOW();

UPDATE tracked_channels
SET enabled = FALSE,
    updated_at = NOW()
WHERE source_kind = 'discussion'
  AND parent_channel_id = -1003802812639
  AND chat_id <> -1003859952761;
