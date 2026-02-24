#!/usr/bin/env python3

import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from telegram import Bot, Message
import boto3

# --- Import from our new db.py module ---
from db import get_conn, init_db

# --- Load Environment Variables ---
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Telegram
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# S3-Compatible Storage
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')
S3_ACCESS_KEY_ID = os.environ.get('S3_ACCESS_KEY_ID')
S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRET_ACCESS_KEY')

# --- Validations ---
if not BOT_TOKEN:
    raise RuntimeError("Please set TELEGRAM_BOT_TOKEN in your .env file.")
if not S3_BUCKET_NAME or not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
    raise RuntimeError("Please set S3_BUCKET_NAME, S3_ACCESS_KEY_ID, and S3_SECRET_ACCESS_KEY in your .env")

# --- Global Clients ---
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY_ID,
    aws_secret_access_key=S3_SECRET_ACCESS_KEY
)
# --- Question Bank for FSM (can be expanded later) ---
QUESTION_BANK = [
    "Where are you going?", 
    "Who is the local guide?", 
    "What's the target species?"
]

# ---------------- DB helpers (specific to fetcher) ----------------

def get_last_update_id(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT last_update_id FROM last_update WHERE id=1')
        row = cur.fetchone()
        return row[0] if row else None

def set_last_update_id(conn, update_id):
    with conn.cursor() as cur:
        cur.execute('UPDATE last_update SET last_update_id=%s WHERE id=1', (update_id,))
    conn.commit()

def upsert_user(conn, user_obj):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (telegram_user_id, username, first_name, last_name, language_code)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
              username = EXCLUDED.username,
              first_name = EXCLUDED.first_name,
              last_name = EXCLUDED.last_name,
              language_code = EXCLUDED.language_code
            RETURNING id
        """, (
            user_obj.id,
            getattr(user_obj, 'username', None),
            getattr(user_obj, 'first_name', None),
            getattr(user_obj, 'last_name', None),
            getattr(user_obj, 'language_code', None)
        ))
        uid = cur.fetchone()[0]
    conn.commit()
    return uid

def insert_message(conn, update_id, msg: Message, user_id, survey_question=None):
    with conn.cursor() as cur:
        ts = msg.date if msg.date else datetime.now(timezone.utc)
        cur.execute(
            "INSERT INTO messages (telegram_message_id, update_id, user_id, chat_id, text, survey_question, timestamp, raw_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                msg.message_id,
                update_id,
                user_id,
                msg.chat.id if msg.chat else None,
                msg.text or msg.caption,
                survey_question, # Added column
                ts,
                psycopg2.extras.Json(msg.to_dict())
            )
        )
        mid = cur.fetchone()[0]
    conn.commit()
    return mid

def insert_media(conn, message_id, media_record):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO media (message_id, media_type, file_id, file_path, file_name, mime_type, file_size, transcription, description, latitude, longitude) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                message_id,
                media_record.get('media_type'),
                media_record.get('file_id'),
                media_record.get('file_path'),
                media_record.get('file_name'),
                media_record.get('mime_type'),
                media_record.get('file_size'),
                media_record.get('transcription', ''),
                media_record.get('description', ''),
                media_record.get('latitude'),
                media_record.get('longitude')
            )
        )
        mid = cur.fetchone()[0]
    conn.commit()
    return mid

# ---------------- S3/Telegram helpers ----------------

async def upload_telegram_file_to_s3(file_obj, s3_key, mime_type):
    try:
        byte_data = await file_obj.download_as_bytearray()
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=byte_data,
            ContentType=mime_type or 'application/octet-stream'
        )
        return len(byte_data)
    except Exception as e:
        print(f"Error uploading {s3_key} to S3: {e}")
        return 0

# ---------------- Main Processor ----------------

async def process_update(conn, update_obj, bot: Bot):
    msg = update_obj.message or update_obj.edited_message
    if not msg: return
    update_id = update_obj.update_id
    from_user = msg.from_user
    if not from_user: return

    user_id_db = upsert_user(conn, from_user)
    
    # 1. Check FSM State BEFORE saving the message
    with conn.cursor() as cur:
        cur.execute("SELECT current_state, current_step, answers FROM user_states WHERE user_id = %s", (user_id_db,))
        state_row = cur.fetchone()
        
    current_question_context = None
    text = msg.text or msg.caption or ""

    # 2. Command Interception
    if text.strip() == "/start_trip":
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_states (user_id, current_state, current_step, answers) 
                VALUES (%s, 'survey_active', 0, '[]'::jsonb)
                ON CONFLICT (user_id) DO UPDATE SET current_state = 'survey_active', current_step = 0, answers = '[]'::jsonb
            """, (user_id_db,))
            conn.commit()
        await bot.send_message(chat_id=msg.chat.id, text=f"Question 1: {QUESTION_BANK[0]}")
        insert_message(conn, update_id, msg, user_id_db, survey_question=None)
        return 

    # 3. Answer Processing
    if state_row and state_row[0] == 'survey_active':
        current_step = state_row[1]
        answers = state_row[2] or []
        
        # Context for the DB save
        current_question_context = QUESTION_BANK[current_step]
        answers.append(text)
        next_step = current_step + 1

        with conn.cursor() as cur:
            if next_step < len(QUESTION_BANK):
                cur.execute("UPDATE user_states SET current_step = %s, answers = %s::jsonb WHERE user_id = %s", 
                            (next_step, psycopg2.extras.Json(answers), user_id_db))
                conn.commit()
                await bot.send_message(chat_id=msg.chat.id, text=f"Question {next_step + 1}: {QUESTION_BANK[next_step]}")
            else:
                cur.execute("UPDATE user_states SET current_state = NULL, current_step = 0 WHERE user_id = %s", (user_id_db,))
                conn.commit()
                summary = "\n".join([f"Q: {q}\nA: {a}" for q, a in zip(QUESTION_BANK, answers)])
                await bot.send_message(chat_id=msg.chat.id, text=f"Survey Complete! Here is your summary:\n\n{summary}")

    # 4. Standard Archiving (With Context)
    message_db_id = insert_message(conn, update_id, msg, user_id_db, survey_question=current_question_context)

    # Location
    if msg.location:
        loc = msg.location
        media_record = {'media_type': 'location', 'latitude': loc.latitude, 'longitude': loc.longitude}
        insert_media(conn, message_db_id, media_record)

    # Photo
    if msg.photo:
        best = msg.photo[-1]
        file_obj = await bot.get_file(best.file_id)
        ext = Path(file_obj.file_path).suffix or '.jpg'
        s3_key_name = f'photo_{best.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, 'image/jpeg')
        media_record = {'media_type': 'photo', 'file_id': best.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': 'image/jpeg', 'file_size': size}
        insert_media(conn, message_db_id, media_record)

    # Audio
    if msg.audio:
        audio = msg.audio
        file_obj = await bot.get_file(audio.file_id)
        ext = Path(file_obj.file_path).suffix or '.mp3'
        s3_key_name = audio.file_name or f'audio_{audio.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, audio.mime_type)
        media_record = {'media_type': 'audio', 'file_id': audio.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': audio.mime_type, 'file_size': size}
        insert_media(conn, message_db_id, media_record)

    # Voice
    if msg.voice:
        voice = msg.voice
        file_obj = await bot.get_file(voice.file_id)
        ext = Path(file_obj.file_path).suffix or '.ogg'
        s3_key_name = f'voice_{voice.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, voice.mime_type)
        media_record = {'media_type': 'voice', 'file_id': voice.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': voice.mime_type, 'file_size': size}
        insert_media(conn, message_db_id, media_record)

    # Video
    if msg.video:
        video = msg.video
        file_obj = await bot.get_file(video.file_id)
        ext = Path(file_obj.file_path).suffix or '.mp4'
        s3_key_name = f'video_{video.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, video.mime_type)
        media_record = {'media_type': 'video', 'file_id': video.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': video.mime_type, 'file_size': size}
        insert_media(conn, message_db_id, media_record)

    # Document
    if msg.document:
        doc = msg.document
        file_obj = await bot.get_file(doc.file_id)
        ext = Path(file_obj.file_path).suffix or '.bin'
        s3_key_name = doc.file_name or f'doc_{doc.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, doc.mime_type)
        media_record = {'media_type': 'document', 'file_id': doc.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': doc.mime_type, 'file_size': size}
        insert_media(conn, message_db_id, media_record)

    # Sticker
    if msg.sticker:
        st = msg.sticker
        file_obj = await bot.get_file(st.file_id)
        ext = Path(file_obj.file_path).suffix or '.webp'
        s3_key_name = f'sticker_{st.file_id}{ext}'
        s3_key_path = f"{from_user.id}/{msg.message_id}/{s3_key_name}"
        size = await upload_telegram_file_to_s3(file_obj, s3_key_path, st.mime_type or 'image/webp')
        media_record = {'media_type': 'sticker', 'file_id': st.file_id, 'file_path': s3_key_path, 'file_name': s3_key_name, 'mime_type': st.mime_type or 'image/webp', 'file_size': size}
        insert_media(conn, message_db_id, media_record)

# ---------------- Main Execution ----------------

async def main():
    """Main entry point for the script."""
    bot = Bot(token=BOT_TOKEN)
    init_db() # This now uses the shared function
    conn = get_conn()
    try:
        last = get_last_update_id(conn)
        offset = (last + 1) if last is not None else None
        print(f'[{datetime.now().isoformat()}] Fetching updates with offset: {offset}')
        
        updates = await bot.get_updates(offset=offset, timeout=10)
        
        if not updates:
            print(f'[{datetime.now().isoformat()}] No new updates.')
            return

        print(f'[{datetime.now().isoformat()}] Received {len(updates)} new updates.')
        max_update = last or -1
        
        for upd in updates:
            try:
                await process_update(conn, upd, bot)
                if getattr(upd, 'update_id', None) and upd.update_id > max_update:
                    max_update = upd.update_id
            except Exception as e:
                print(f"Error processing update {getattr(upd, 'update_id', None)}: {e}")
        
        if max_update is not None and max_update >= 0:
            set_last_update_id(conn, max_update)
            print(f'[{datetime.now().isoformat()}] Updated last_update_id to {max_update}')
            
    finally:
        conn.close()
        print(f'[{datetime.now().isoformat()}] Run complete. Connection closed.')

if __name__ == '__main__':
    asyncio.run(main())

# --- DEPLOYMENT HANDLER FOR AWS LAMBDA ---
def lambda_handler(event, context):
    """
    This is the function AWS Lambda will run.
    'event' and 'context' are passed by Lambda.
    """
    print("Fetcher Lambda job started...")
    
    try:
        asyncio.run(main())
        print("Fetcher Lambda job complete.")
        return { 'statusCode': 200, 'body': 'Success' }
    except Exception as e:
        print(f"Error in fetcher: {e}")
        return { 'statusCode': 500, 'body': 'Error' }