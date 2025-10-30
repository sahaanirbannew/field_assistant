import os
import json
import asyncio
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
import google.generativeai as genai

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

# --- Create directories ---
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("messages", exist_ok=True)

# --- JSON message file ---
MESSAGE_FILE = "messages/messages.json"

# --- Time Format ---
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def load_data():
    """Load messages and last_update_id from JSON file"""
    if os.path.exists(MESSAGE_FILE):
        try:
            with open(MESSAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Handle old format (just a list) or new format (dict with metadata)
                if isinstance(data, list):
                    return {"last_update_id": None, "messages": data}
                # Handle empty dict or ensure required keys exist
                if isinstance(data, dict):
                    return {
                        "last_update_id": data.get("last_update_id"),
                        "messages": data.get("messages", [])
                    }
                # Fallback for unexpected formats
                print("⚠️ Warning: Unexpected data format in messages.json. Starting fresh.")
                return {"last_update_id": None, "messages": []}
        except json.JSONDecodeError:
            print("⚠️ Warning: Could not parse messages.json. Starting fresh.")
            return {"last_update_id": None, "messages": []}
    return {"last_update_id": None, "messages": []}


def save_data(data):
    """Save messages and last_update_id to JSON file"""
    with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def transcribe_audio(audio_path: str) -> Optional[str]:
    """Transcribe audio file using Gemini API"""
    if not GEMINI_ENABLED:
        return None
    
    try:
        print(f"🎤 Transcribing: {audio_path}")
        
        # Upload audio file to Gemini
        audio_file = genai.upload_file(path=audio_path)
        
        # Use Gemini 2.5 Flash for transcription
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        # Request transcription with language auto-detection
        response = model.generate_content([
            "Transcribe this audio file. Detect the language automatically and provide only the transcription text without any additional commentary.",
            audio_file
        ])
        
        transcription = response.text.strip()
        print(f"✅ Transcription complete: {transcription[:50]}...")
        
        return transcription
    
    except Exception as e:
        print(f"❌ Transcription failed for {audio_path}: {e}")
        return None


# Load initial data
data = load_data()
messages = data["messages"]
last_update_id = data["last_update_id"]


async def fetch_new_messages():
    """Fetch new messages from Telegram since last update"""
    global messages, last_update_id
    
    bot = Bot(token=BOT_TOKEN)
    
    # Calculate offset (last_update_id + 1, or None for first fetch)
    offset = (last_update_id + 1) if last_update_id is not None else None
    
    print(f"📥 Fetching updates with offset: {offset}")
    
    try:
        # Get updates from Telegram
        updates = await bot.get_updates(offset=offset, timeout=10)
        
        if not updates:
            print("✅ No new messages to fetch")
            return
        
        print(f"📨 Found {len(updates)} new update(s)")
        
        # Track messages that need transcription
        messages_to_transcribe = []
        
        # Process each update
        for update in updates:
            # Track the highest update_id
            if last_update_id is None or update.update_id > last_update_id:
                last_update_id = update.update_id
            
            # Skip if no message (could be other update types)
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
                    msg_entry = {
                        "user": username,
                        "type": "text",
                        "content": message.text,
                        "time": timestamp
                    }
                
                # --- Photo ---
                elif message.photo:
                    file = await message.photo[-1].get_file()
                    path = f"static/uploads/{base_filename}.jpg"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {
                        "user": username,
                        "type": "photo",
                        "content": path,
                        "time": timestamp
                    }
                    if caption:
                        msg_entry["caption"] = caption
                
                # --- Video ---
                elif message.video:
                    file = await message.video.get_file()
                    path = f"static/uploads/{base_filename}.mp4"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {
                        "user": username,
                        "type": "video",
                        "content": path,
                        "time": timestamp
                    }
                    if caption:
                        msg_entry["caption"] = caption
                
                # --- Video Note (round bubble video) ---
                elif message.video_note:
                    file = await message.video_note.get_file()
                    path = f"static/uploads/{base_filename}_note.mp4"
                    await file.download_to_drive(path)
                    msg_entry = {
                        "user": username,
                        "type": "video",
                        "content": path,
                        "time": timestamp
                    }
                
                # --- Audio File ---
                elif message.audio:
                    file = await message.audio.get_file()
                    ext = ".mp3" if message.audio.mime_type == "audio/mpeg" else ".ogg"
                    path = f"static/uploads/{base_filename}{ext}"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {
                        "user": username,
                        "type": "audio",
                        "content": path,
                        "time": timestamp,
                        "transcription": ""  # Will be filled later
                    }
                    if caption:
                        msg_entry["caption"] = caption
                    # Mark for transcription
                    messages_to_transcribe.append(msg_entry)
                
                # --- Voice Message ---
                elif message.voice:
                    file = await message.voice.get_file()
                    path = f"static/uploads/{base_filename}_voice.ogg"
                    await file.download_to_drive(path)
                    msg_entry = {
                        "user": username,
                        "type": "audio",
                        "content": path,
                        "time": timestamp,
                        "transcription": ""  # Will be filled later
                    }
                    # Mark for transcription
                    messages_to_transcribe.append(msg_entry)
                
                # --- Document ---
                elif message.document:
                    file = await message.document.get_file()
                    safe_name = message.document.file_name.replace(" ", "_")
                    path = f"static/uploads/{base_filename}_{safe_name}"
                    await file.download_to_drive(path)
                    caption = message.caption or None
                    msg_entry = {
                        "user": username,
                        "type": "document",
                        "content": path,
                        "time": timestamp
                    }
                    if caption:
                        msg_entry["caption"] = caption
                
                # --- Location ---
                elif message.location:
                    lat = message.location.latitude
                    lon = message.location.longitude
                    msg_entry = {
                        "user": username,
                        "type": "location",
                        "content": f"{lat},{lon}",
                        "time": timestamp
                    }
                
                # Add message to list
                if msg_entry:
                    messages.append(msg_entry)
                    print(f"✅ Processed message from {username} ({msg_entry['type']}) at {timestamp}")
            
            except Exception as e:
                print(f"❌ Error processing message: {e}")
        
        # Save messages before transcription
        save_data({
            "last_update_id": last_update_id,
            "messages": messages
        })
        print(f"💾 Saved {len(updates)} new message(s). Last update_id: {last_update_id}")
        
        # Transcribe audio messages (after saving)
        if messages_to_transcribe and GEMINI_ENABLED:
            print(f"\n🎤 Starting transcription for {len(messages_to_transcribe)} audio message(s)...")
            
            for msg in messages_to_transcribe:
                # Skip if already transcribed
                if msg.get("transcription"):
                    print(f"⏭️ Skipping already transcribed: {msg['content']}")
                    continue
                
                transcription = await transcribe_audio(msg["content"])
                if transcription:
                    msg["transcription"] = transcription
                
                # Small delay to respect rate limits (10 RPM = 6 seconds between requests)
                await asyncio.sleep(6)
            
            # Save again with transcriptions
            save_data({
                "last_update_id": last_update_id,
                "messages": messages
            })
            print("💾 Saved transcriptions to JSON")
        elif messages_to_transcribe and not GEMINI_ENABLED:
            print("⚠️ Skipping transcription: GEMINI_API_KEY not configured")
    
    except Exception as e:
        print(f"❌ Error fetching updates: {e}")


# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fetch messages on startup
    print("🚀 Starting Telegram Journal Fetch...")
    await fetch_new_messages()
    print("✅ Fetch complete. Starting web server...")
    yield
    # Cleanup on shutdown (if any)


# --- FastAPI Web App ---
web_app = FastAPI(lifespan=lifespan)
web_app.mount("/static", StaticFiles(directory="static"), name="static")

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
            img, video { border-radius: 8px; margin-top: 10px; }
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
        <p><small>Showing latest 30 messages</small></p>
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
            html += f"<li><b>{msg['user']}</b> shared location: <a href='https://www.google.com/maps?q={lat},{lon}' target='_blank'>View on map</a><br><small>{msg['time']}</small></li>"
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


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Telegram Journal - Fetch on Demand")
    uvicorn.run(web_app, host="0.0.0.0", port=8000)