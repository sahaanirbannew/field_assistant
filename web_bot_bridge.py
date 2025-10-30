import os
import json
import asyncio
import re  # <-- Import regular expressions for sanitizing
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
import google.generativeai as genai
from collections import defaultdict # <-- Import defaultdict

# --- Load environment variables ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN:
    raise EnvironmentError("❌ TELEGRAM_BOT_TOKEN not found in .env file")

if not GEMINI_API_KEY:
    print("⚠️ WARNING: GEMINI_API_KEY not found in .env file. Audio transcription will be disabled.")
    GEMINI_ENABLED = False
else:
    GEMINI_ENABLED = True
    genai.configure(api_key=GEMINI_API_KEY)

# --- NEW: File & Directory Constants ---
MESSAGES_DIR = "messages"
USER_MESSAGES_DIR = os.path.join(MESSAGES_DIR, "users")
METADATA_FILE = os.path.join(MESSAGES_DIR, "metadata.json")
OLD_MESSAGE_FILE = os.path.join(MESSAGES_DIR, "messages.json") # For migration

# --- Create directories ---
os.makedirs(USER_MESSAGES_DIR, exist_ok=True) # Ensure /users subdir exists
os.makedirs(os.path.join("static", "uploads"), exist_ok=True) # Ensure uploads dir exists
# --- Time Format ---
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- NEW: Helper to make safe filenames ---
def sanitize_filename(username: str) -> str:
    """Converts a username into a safe filename."""
    if not username:
        return "unknown_user.json"
    # Remove invalid chars
    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', username)
    # Ensure it's not empty
    if not safe_name.strip('_'):
        return "unknown_user.json"
    return f"{safe_name.lower()}.json"

# --- MODIFIED: load_data ---
def load_data():
    """Load metadata and all user messages from their respective files."""
    
    last_update_id = None
    all_messages = []

    # --- Step 1: Migration Check ---
    # If new metadata file doesn't exist, check for the old messages.json
    if not os.path.exists(METADATA_FILE) and os.path.exists(OLD_MESSAGE_FILE):
        print("Migrating old messages.json to new user-based format...")
        try:
            with open(OLD_MESSAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Handle old-old format (just a list)
                if isinstance(data, list):
                    data = {"last_update_id": None, "messages": data}
                
                # This is the old data structure
                old_messages = data.get("messages", [])
                old_update_id = data.get("last_update_id")
                
                # This is a one-time operation:
                # Call the *new* save_data to perform the migration.
                save_data({"last_update_id": old_update_id, "messages": old_messages})
                
                # Delete the old file after successful migration
                os.remove(OLD_MESSAGE_FILE)
                
                print(f"✅ Migration complete. {len(old_messages)} messages split into user files.")
                
                # Sort messages by time and return them
                old_messages.sort(key=lambda x: datetime.strptime(x["time"], TIME_FORMAT))
                return {"last_update_id": old_update_id, "messages": old_messages}
                
        except Exception as e:
            print(f"❌ ERROR: Migration failed: {e}. Starting fresh.")
            return {"last_update_id": None, "messages": []}

    # --- Step 2: Normal Load (Metadata) ---
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                last_update_id = metadata.get("last_update_id")
        except json.JSONDecodeError:
            print(f"⚠️ Warning: Could not parse {METADATA_FILE}. Starting fresh.")
    
    # --- Step 3: Normal Load (User Messages) ---
    print(f"Loading user messages from {USER_MESSAGES_DIR}...")
    for filename in os.listdir(USER_MESSAGES_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(USER_MESSAGES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    user_messages = json.load(f)
                    if isinstance(user_messages, list):
                        all_messages.extend(user_messages)
            except json.JSONDecodeError:
                print(f"⚠️ Warning: Could not parse {filepath}.")
                
    # --- Step 4: Sort all loaded messages by time ---
    # This is crucial for the UI to be correct
    all_messages.sort(key=lambda x: datetime.strptime(x["time"], TIME_FORMAT))
    
    print(f"✅ Loaded {len(all_messages)} messages from {len(os.listdir(USER_MESSAGES_DIR))} users.")
    return {"last_update_id": last_update_id, "messages": all_messages}


# --- MODIFIED: save_data ---
def save_data(data):
    """Saves metadata and splits all messages into per-user JSON files."""
    
    global_messages = data.get("messages", [])
    
    # --- Step 1: Save Metadata ---
    metadata = {"last_update_id": data.get("last_update_id")}
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
    except Exception as e:
        print(f"❌ CRITICAL: Failed to save metadata: {e}")
        return # Don't proceed if we can't save the update_id
        
    # --- Step 2: Group all messages by user ---
    # We use defaultdict to easily create a list for new users
    messages_by_user = defaultdict(list)
    for msg in global_messages:
        # Ensure message has a user, default to 'unknown'
        username = msg.get("user", "Unknown")
        messages_by_user[username].append(msg)
        
    # --- Step 3: Save each user's messages to their file ---
    # This loop overwrites each user's file with the full,
    # up-to-date list of their messages.
    for username, user_messages in messages_by_user.items():
        user_filename = sanitize_filename(username)
        user_filepath = os.path.join(USER_MESSAGES_DIR, user_filename)
        
        try:
            with open(user_filepath, "w", encoding="utf-8") as f:
                json.dump(user_messages, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error saving messages for {username}: {e}")
    
    # print(f"💾 Saved data for {len(messages_by_user)} users.") # Can be noisy


# --- Transcription Function (Unchanged) ---
async def transcribe_audio(audio_path: str) -> Optional[str]:
    """Transcribe audio file using Gemini API"""
    if not GEMINI_ENABLED:
        return None
    
    try:
        print(f"🎤 Transcribing: {audio_path}")
        
        # Upload audio file to Gemini
        audio_file = genai.upload_file(path=audio_path)
        
        # Use Gemini 1.5 Flash
        model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
        
        # Request transcription
        response = model.generate_content([
            "Transcribe this audio file. Detect the language automatically and provide only the transcription text without any additional commentary.",
            audio_file
        ])
        
        transcription = response.text.strip()
        print(f"✅ Transcription complete: {transcription[:50]}...")
        
        # Clean up the file
        genai.delete_file(audio_file.name)
        
        return transcription
    
    except Exception as e:
        print(f"❌ Transcription failed for {audio_path}: {e}")
        return None


# --- Load initial data (This now runs the new load_data) ---
data = load_data()
messages = data["messages"]
last_update_id = data["last_update_id"]


# --- fetch_new_messages (With 1-Line Bug Fix) ---
async def fetch_new_messages():
    """Fetch new messages from Telegram since last update"""
    global messages, last_update_id
    
    bot = Bot(token=BOT_TOKEN)
    offset = (last_update_id + 1) if last_update_id is not None else None
    
    print(f"📥 Fetching updates with offset: {offset}")
    
    try:
        updates = await bot.get_updates(offset=offset, timeout=10)
        
        if not updates:
            print("✅ No new messages to fetch")
            return
        
        print(f"📨 Found {len(updates)} new update(s)")
        
        messages_to_transcribe = []
        
        for update in updates:
            if last_update_id is None or update.update_id > last_update_id:
                last_update_id = update.update_id
            
            if not update.message:
                continue
            
            message = update.message
            username = message.from_user.username or message.from_user.first_name or "Unknown"
            timestamp = datetime.now().strftime(TIME_FORMAT)
            base_filename = f"{username}_{int(datetime.now().timestamp())}"
            
            msg_entry = None
            
            try:
                # --- Text message ---
                if message.text:
                    msg_entry = {"user": username, "type": "text", "content": message.text, "time": timestamp}
                
                # --- Photo ---
                elif message.photo:
                    file = await message.photo[-1].get_file()
                    path = f"static/uploads/{base_filename}.jpg"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {"user": username, "type": "photo", "content": path, "time": timestamp}
                    if caption: msg_entry["caption"] = caption
                
                # --- Video ---
                elif message.video:
                    file = await message.video.get_file()
                    path = f"static/uploads/{base_filename}.mp4"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {"user": username, "type": "video", "content": path, "time": timestamp}
                    if caption: msg_entry["caption"] = caption
                
                # --- Video Note ---
                elif message.video_note:
                    file = await message.video_note.get_file()
                    path = f"static/uploads/{base_filename}_note.mp4"
                    await file.download_to_drive(path)
                    msg_entry = {"user": username, "type": "video", "content": path, "time": timestamp}
                
                # --- Audio File ---
                elif message.audio:
                    file = await message.audio.get_file()
                    ext = ".mp3" if message.audio.mime_type == "audio/mpeg" else ".ogg"
                    path = f"static/uploads/{base_filename}{ext}"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {"user": username, "type": "audio", "content": path, "time": timestamp, "transcription": ""}
                    if caption: msg_entry["caption"] = caption
                    messages_to_transcribe.append(msg_entry)
                
                # --- Voice Message ---
                elif message.voice:
                    file = await message.voice.get_file()
                    path = f"static/uploads/{base_filename}_voice.ogg"
                    await file.download_to_drive(path)
                    msg_entry = {"user": username, "type": "audio", "content": path, "time": timestamp, "transcription": ""}
                    messages_to_transcribe.append(msg_entry)
                
                # --- Document ---
                elif message.document:
                    file = await message.document.get_file()
                    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', message.document.file_name) # Sanitize doc name
                    path = f"static/uploads/{base_filename}_{safe_name}"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {"user": username, "type": "document", "content": path, "time": timestamp}
                    if caption: msg_entry["caption"] = caption
                
                # --- Location ---
                elif message.location:
                    lat, lon = message.location.latitude, message.location.longitude
                    msg_entry = {"user": username, "type": "location", "content": f"{lat},{lon}", "time": timestamp}
                
                # Add message to GLOBAL list
                if msg_entry:
                    messages.append(msg_entry)
                    print(f"✅ Processed message from {username} ({msg_entry['type']}) at {timestamp}")
            
            except Exception as e:
                print(f"❌ Error processing message: {e}")
        
        # --- Save Phase 1 (Save all messages and new update_id) ---
        # This calls the new save_data function, which splits files by user
        save_data({
            "last_update_id": last_update_id,
            "messages": messages
        })
        print(f"💾 Saved {len(updates)} new message(s). Last update_id: {last_update_id}")
        
        # --- Save Phase 2 (Transcriptions) ---
        if messages_to_transcribe and GEMINI_ENABLED:
            print(f"\n🎤 Starting transcription for {len(messages_to_transcribe)} audio message(s)...")
            
            for msg in messages_to_transcribe:
                # *** BUG FIX: Use asyncio.to_thread for synchronous genai call ***
                transcription = await asyncio.to_thread(transcribe_audio, msg["content"])
                if transcription:
                    msg["transcription"] = transcription
                
                # Small delay to respect rate limits
                await asyncio.sleep(4) # 15 RPM for flash model
            
            # Save again with transcriptions
            # This will re-write the user files, now with transcription text
            save_data({
                "last_update_id": last_update_id,
                "messages": messages
            })
            print("💾 Saved transcriptions to user files")
        
    except Exception as e:
        print(f"❌ Error fetching updates: {e}")


# --- Lifespan (Unchanged) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Telegram Journal Fetch...")
    await fetch_new_messages()
    print("✅ Fetch complete. Starting web server...")
    yield


# --- FastAPI Web App (Unchanged) ---
web_app = FastAPI(lifespan=lifespan)
web_app.mount("/static", StaticFiles(directory="static"), name="static")

# --- All Endpoints (Unchanged) ---
# They all read from the global 'messages' list, 
# which is correctly assembled by the new load_data()

@web_app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <html>
    <head>
        <title>Telegram Journal</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; }
            h2 { color: #0088cc; }
            ul { list-style: none; padding: 0; }
            li { margin-bottom: 20px; padding: 15px; background: #f5f5f5; border-radius: 8px; }
            small { color: #666; }
            img, video { border-radius: 8px; margin-top: 10px; max-width: 100%; }
            .transcription { 
                background: #e3f2fd; 
                padding: 10px; 
                border-left: 3px solid #2196f3; 
                margin-top: 10px;
                font-style: italic;
            }
        </style>
    </head>
    <body>
        <h2>📔 My Telegram Journal</h2>
        <p><small>Showing latest 30 messages (from all users)</small></p>
        <ul>
    """
    for msg in reversed(messages[-30:]):  # Show latest 30
        if msg["type"] == "text":
            html += f"<li><b>{msg['user']}</b>: {msg['content']} <br><small>{msg['time']}</small></li>"
        elif msg["type"] == "photo":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a photo:<br><img src='/{msg['content']}' width='400'>{caption_html}<br><small>{msg['time']}</small></li>"
        elif msg["type"] == "video":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a video:<br><video width='400' controls src='/{msg['content']}'></video>{caption_html}<br><small>{msg['time']}</small></li>"
        elif msg["type"] == "audio":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            transcription_html = ""
            if msg.get("transcription"):
                transcription_html = f"<div class='transcription'>🎤 Transcription: {msg['transcription']}</div>"
            html += f"<li><b>{msg['user']}</b> sent audio:<br><audio controls src='/{msg['content']}'></audio>{transcription_html}{caption_html}<br><small>{msg['time']}</small></li>"
        elif msg["type"] == "document":
            caption_html = f"<br><i>{msg.get('caption')}</i>" if msg.get("caption") else ""
            html += f"<li><b>{msg['user']}</b> sent a document: <a href='/{msg['content']}' download>Download</a>{caption_html}<br><small>{msg['time']}</small></li>"
        elif msg["type"] == "location":
            lat, lon = msg["content"].split(",")
            html += f"<li><b>{msg['user']}</b> shared location: <a href='https://www.google.com/maps/search/?api=1&query={lat},{lon}' target='_blank'>View on map</a><br><small>{msg['time']}</small></li>"
    html += "</ul></body></html>"
    return HTMLResponse(html)


@web_app.get("/messages")
async def get_messages():
    """Return last 50 messages as JSON"""
    return JSONResponse(messages[-50:])


@web_app.get("/search")
async def search_messages(
    username: Optional[str] = None,
    start_time: Optional[datetime] = Query(None, description="Start time (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End time (ISO 8601)")
):
    """Filter messages by username and/or time range"""
    results_to_filter = messages
    
    # Apply username filter
    if username:
        results_to_filter = [
            msg for msg in results_to_filter if msg.get("user") == username
        ]
    
    # Apply time filters
    if start_time or end_time:
        final_results = []
        for msg in results_to_filter:
            try:
                msg_time = datetime.strptime(msg["time"], TIME_FORMAT)
                
                if start_time and msg_time < start_time:
                    continue
                if end_time and msg_time > end_time:
                    continue
                
                final_results.append(msg)
            except (KeyError, ValueError):
                continue
        
        results_to_filter = final_results
    
    return JSONResponse(content=results_to_filter)


# --- Main runner (Unchanged) ---
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Telegram Journal - Fetch on Demand (User-based files)")
    uvicorn.run(web_app, host="0.0.0.0", port=8000)