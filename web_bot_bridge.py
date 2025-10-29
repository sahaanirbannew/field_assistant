import os
import json
import asyncio
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime
from typing import Optional

# --- Load environment variables ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise EnvironmentError("❌ TELEGRAM_BOT_TOKEN not found in .env file")

# --- Create directories ---
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("messages", exist_ok=True)

# --- JSON message file ---
MESSAGE_FILE = "messages/messages.json"

# --- Time Format ---
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def load_messages():
    """Load messages from JSON file"""
    if os.path.exists(MESSAGE_FILE):
        try:
            with open(MESSAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠️ Warning: Could not parse messages.json. Starting fresh.")
            return []
    return []


def save_messages():
    """Save messages to JSON file"""
    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=4, ensure_ascii=False)


# Shared message list
messages = load_messages()


# --- Telegram message handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or update.effective_user.first_name or "Unknown"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    msg_entry = None
    base_filename = f"{username}_{int(datetime.now().timestamp())}"

    try:
        # --- Text message ---
        if update.message.text:
            msg_entry = {"user": username, "type": "text", "content": update.message.text, "time": timestamp}

        # --- Photo ---
        elif update.message.photo:
            file = await update.message.photo[-1].get_file()
            path = f"static/uploads/{base_filename}.jpg"
            await file.download_to_drive(path)
            caption = update.message.caption or None
            msg_entry = {"user": username, "type": "photo", "content": path, "time": timestamp}
            if caption:
                msg_entry["caption"] = caption
        # --- Video ---
        elif update.message.video:
            file = await update.message.video.get_file()
            path = f"static/uploads/{base_filename}.mp4"
            await file.download_to_drive(path)
            caption = update.message.caption or None
            msg_entry = {"user": username, "type": "video", "content": path, "time": timestamp}
            if caption:
                msg_entry["caption"] = caption

        # --- Video Note (round bubble video) ---
        elif update.message.video_note:
            file = await update.message.video_note.get_file()
            path = f"static/uploads/{base_filename}_note.mp4"
            await file.download_to_drive(path)
            msg_entry = {"user": username, "type": "video", "content": path, "time": timestamp}

        # --- Audio File ---
        elif update.message.audio:
            file = await update.message.audio.get_file()
            # get mime type (if available)
            ext = ".mp3" if update.message.audio.mime_type == "audio/mpeg" else ".ogg"
            path = f"static/uploads/{base_filename}{ext}"
            await file.download_to_drive(path)
            caption = update.message.caption or None
            msg_entry = {"user": username, "type": "audio", "content": path, "time": timestamp}
            if caption:
                msg_entry["caption"] = caption

        # --- Voice Message ---
        elif update.message.voice:
            file = await update.message.voice.get_file()
            path = f"static/uploads/{base_filename}_voice.ogg"
            await file.download_to_drive(path)
            msg_entry = {"user": username, "type": "audio", "content": path, "time": timestamp}

        # --- Document ---
        elif update.message.document:
            file = await update.message.document.get_file()
            safe_name = update.message.document.file_name.replace(" ", "_")
            path = f"static/uploads/{base_filename}_{safe_name}"
            await file.download_to_drive(path)
            caption = update.message.caption or None
            msg_entry = {"user": username, "type": "document", "content": path, "time": timestamp}
            if caption:
                msg_entry["caption"] = caption

        # --- Location ---
        elif update.message.location:
            lat = update.message.location.latitude
            lon = update.message.location.longitude
            msg_entry = {"user": username, "type": "location", "content": f"{lat},{lon}", "time": timestamp}

        # --- Save message ---
        if msg_entry:
            messages.append(msg_entry)
            save_messages()
            print(f"✅ Saved message from {username} ({msg_entry['type']}) at {timestamp}")

    except Exception as e:
        print(f"❌ Error handling message: {e}")


# --- Telegram Bot Runner ---
async def run_telegram_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    await app.initialize()
    await app.start()
    print("🤖 Telegram bot is running in background...")
    await app.updater.start_polling()
    await asyncio.Event().wait()


# --- FastAPI Web App ---
web_app = FastAPI()
web_app.mount("/static", StaticFiles(directory="static"), name="static")


@web_app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <html>
    <head>
        <title>Telegram Bridge</title>
        <!--<meta http-equiv="refresh" content="3">-->
    </head>
    <body>
        <h2>Messages from Telegram</h2>
        <ul>
    """
    for msg in reversed(messages[-30:]):  # Show latest 30
        if msg["type"] == "text":
            html += f"<li><b>{msg['user']}</b>: {msg['content']} <small>({msg['time']})</small></li>"
        elif msg["type"] == "photo":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a photo:<br><img src='/{msg['content']}' width='150'>{caption_html}</li><small>({msg['time']})</small>"
        elif msg["type"] == "video":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a video:<br><video width='250' controls src='/{msg['content']}'></video>{caption_html}</li><small>({msg['time']})</small>"
        elif msg["type"] == "audio":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent audio:<br><audio controls src='/{msg['content']}'></audio></li><small>({msg['time']}){caption_html}</small>"
        elif msg["type"] == "document":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a document: <a href='/{msg['content']}' download>Download</a>{caption_html}</li><small>({msg['time']})</small>"
        elif msg["type"] == "location":
            lat, lon = msg["content"].split(",")
            html += f"<li><b>{msg['user']}</b> shared location: <a href='https://www.google.com/maps?q={lat},{lon}' target='_blank'>View on map</a></li><small>({msg['time']})</small>"
    html += "</ul></body></html>"
    return HTMLResponse(html)


@web_app.get("/messages")
async def get_messages():
    """Return last 50 messages as JSON"""
    return JSONResponse(messages[-50:])

# --- Search Endpoint ---
@web_app.get("/search")
async def search_messages(
    username: Optional[str] = None,
    start_time: Optional[datetime] = Query(None, description="Start time (ISO 8601, e.g., 2025-10-29T06:00:00)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO 8601, e.g., 2025-10-29T07:00:00)")
):
    """
    Filters messages by username and/or time range.
    """
    
    # Use the global 'messages' list that's already in memory
    results_to_filter = messages 
    
    # 1. Apply username filter (if provided)
    if username:
        results_to_filter = [
            msg for msg in results_to_filter if msg.get("user") == username
        ]
    
    # 2. Apply time filters (if provided)
    if start_time or end_time:
        final_results = []
        for msg in results_to_filter:
            try:
                # Parse the message's time string using our defined format
                msg_time = datetime.strptime(msg["time"], TIME_FORMAT) 
                
                # Check if it's outside the requested range
                if start_time and msg_time < start_time:
                    continue  # Too early
                if end_time and msg_time > end_time:
                    continue  # Too late
                    
                # If it passes, add it
                final_results.append(msg)
                
            except (KeyError, ValueError):
                # Skip messages with missing or badly formatted time
                continue
        
        # Overwrite the list with the time-filtered results
        results_to_filter = final_results
    
    # Return whatever is left after filtering
    return JSONResponse(content=results_to_filter)


# --- Startup Event ---
@web_app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_telegram_bot())


print("🚀 Starting FastAPI + Telegram Bridge")
