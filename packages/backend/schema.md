# Database Schema

This document describes the PostgreSQL database schema used for storing Telegram messages, media files, and user data.

## Tables Overview

```
+---------------+     +-----------------+     +------------------+
|    users      |     |    messages    |     |      media      |
+---------------+     +-----------------+     +------------------+
| *id           |     | *id            |     | *id             |
| telegram_id UK|<-+  | telegram_msg_id|     | message_id FK   |
| username      |  |  | update_id      |  +->| media_type      |
| first_name    |  |  | user_id FK     |  |  | file_id         |
| last_name     |  +--| chat_id        |  |  | file_path       |
| language_code |     | text           |  |  | file_name       |
| created_at    |     | timestamp      |  |  | mime_type       |
+---------------+     | raw_json       |  |  | file_size       |
                     +-----------------+  |  | transcription    |
                                        |  | description      |
+-----------------+                     |  | latitude         |
|   last_update   |                    |  | longitude        |
+-----------------+                    |  +------------------+
| *id (=1)        |                    |
| last_update_id  |                    |
+-----------------+                    |

Legend:
* = Primary Key
UK = Unique Key
FK = Foreign Key
--+ = One-to-Many Relationship
```

## Table Descriptions

### users
Stores Telegram user information.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `telegram_user_id` | BIGINT | Unique Telegram user ID |
| `username` | TEXT | Telegram username |
| `first_name` | TEXT | User's first name |
| `last_name` | TEXT | User's last name |
| `language_code` | TEXT | User's language preference |
| `created_at` | TIMESTAMP WITH TIME ZONE | Account creation timestamp |

### messages
Stores all messages received from Telegram.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `telegram_message_id` | BIGINT | Original Telegram message ID |
| `update_id` | BIGINT | Telegram update ID |
| `user_id` | INTEGER | References users(id) |
| `chat_id` | BIGINT | Telegram chat ID |
| `text` | TEXT | Message text or caption |
| `timestamp` | TIMESTAMP WITH TIME ZONE | Message timestamp |
| `raw_json` | JSONB | Complete message data from Telegram |

### media
Stores media attachments and their metadata.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `message_id` | INTEGER | References messages(id) |
| `media_type` | TEXT | Type (photo/video/audio/voice/document/location/sticker) |
| `file_id` | TEXT | Telegram file ID |
| `file_path` | TEXT | S3/R2 storage path |
| `file_name` | TEXT | Original filename |
| `mime_type` | TEXT | MIME type |
| `file_size` | INTEGER | File size in bytes |
| `transcription` | TEXT | Audio/voice transcription |
| `description` | TEXT | Media description |
| `latitude` | DOUBLE PRECISION | Location latitude |
| `longitude` | DOUBLE PRECISION | Location longitude |

### last_update
Tracks the last processed Telegram update to prevent duplicate processing.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SMALLINT | Primary key (always 1) |
| `last_update_id` | BIGINT | Last processed update_id |

## Relationships

1. `messages.user_id` → `users.id` (ON DELETE SET NULL)
   - Each message is associated with a user
   - If user is deleted, message is kept but user_id set to NULL

2. `media.message_id` → `messages.id` (ON DELETE CASCADE)
   - Media entries are linked to their parent message
   - If message is deleted, associated media entries are also deleted

## Indexes

Default indexes are created on:
- Primary keys (`id` columns)
- Foreign keys (`user_id`, `message_id`)
- Unique constraints (`telegram_user_id`)

## Notes

1. **Timestamps**:
   - All timestamps include timezone information
   - `users.created_at` defaults to current timestamp
   - `messages.timestamp` uses Telegram message time or current UTC time

2. **Media Storage**:
   - Media files are stored in S3-compatible storage 
   - `media.file_path` contains the storage key
   - Original Telegram `file_id` is preserved for reference

3. **Message Content**:
   - Full message content preserved in `messages.raw_json`
   - Text/caption extracted to `messages.text` for easy querying
   - Media details stored separately in media table