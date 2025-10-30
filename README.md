# Telegram Journal

A FastAPI-based personal journal application that fetches messages from your Telegram bot and displays them in a web interface. Messages are fetched on-demand when you run the script, making it perfect for maintaining a personal journal.

## Features

- **Fetch-on-Demand Architecture**: Run the script when you want to sync new messages, no 24/7 server needed
- **Incremental Sync**: Only fetches new messages since last run using Telegram's update_id tracking
- **Multiple Message Types**:
  - Text messages
  - Photos (with captions)
  - Videos (with captions)
  - Video notes (round messages)
  - Audio files (MP3/OGG) (with transcription)
  - Voice messages  (with transcription)
  - Documents
  - Location sharing
- **Web Interface**: Clean UI to view your journal entries
- **Message Persistence**: JSON-based storage with automatic backup
- **Media Storage**: Local file storage for all media (S3 migration planned)
- **Search Functionality**: Filter by username and time range

## How It Works

1. **Send messages** to your Telegram bot (DM the bot directly)
2. **Run the script** when you want to fetch new messages
3. **View your journal** in the automatically-started web interface

The bot tracks the last fetched message using `update_id`, so subsequent runs only fetch new messages - no duplicates!

## Prerequisites

- Python 3.9+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Python virtual environment (strongly recommended)

## Dependencies

This project's dependencies are listed in `requirements.txt`.

The main packages are:

```txt
fastapi
python-telegram-bot==20.8
python-dotenv
uvicorn
python-multipart
httpx
```

## Setup

1. **Clone** the repository.

2. **Create a virtual environment** and activate it:

   ```powershell
   # Create the environment
   python -m venv venv

   # Activate the environment (Windows PowerShell)
   .\venv\Scripts\Activate.ps1

   # Or for Windows CMD
   .\venv\Scripts\activate.bat

   # Or for Linux/Mac
   source venv/bin/activate
   ```

3. **Install all dependencies** using the `requirements.txt` file:

   ```powershell
   # Make sure your (venv) is active
   pip install -r requirements.txt
   ```

4. **Create a `.env` file** in the project root with your Telegram bot token:

   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

5. **Create your bot on Telegram**:
   - Open Telegram and search for [@BotFather](https://t.me/botfather)
   - Send `/newbot` and follow the instructions
   - Copy the bot token to your `.env` file
   - Start a direct message (DM) with your bot

## Usage

### Running the Journal

```powershell
# Make sure your (venv) is active
python web_bot_bridge.py
```

**What happens:**
1. Script loads existing messages from `messages.json`
2. Fetches only new messages from Telegram (using last update_id)
3. Downloads any media files to `static/uploads/`
4. Saves updated messages and new update_id
5. Starts web server automatically at `http://localhost:8000`
6. Open your browser to view your journal

**Console Output:**
```
🚀 Starting Telegram Journal - Fetch on Demand
📥 Fetching updates with offset: 12346
📨 Found 3 new update(s)
✅ Processed message from YourName (text) at 2025-10-30 11:30:00
✅ Processed message from YourName (photo) at 2025-10-30 11:31:15
💾 Saved 3 new message(s). Last update_id: 12348
✅ Fetch complete. Starting web server...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Typical Workflow

```
1. Send messages/photos/videos to your bot throughout the day
2. Run the script: python web_bot_bridge.py
3. View your journal entries at http://localhost:8000
4. Press Ctrl+C to stop the server when done
5. Repeat whenever you want to sync new messages
```

## Project Structure

```
Telegram_Bot/
├── web_bot_bridge.py      # Main application file
├── .env                   # Environment variables (your bot token)
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── static/
│   └── uploads/           # Media files from Telegram
├── messages/
│   └── messages.json      # Message persistence + last_update_id
└── venv/                  # Python virtual environment
```

## Data Storage

### Message Format

Messages are stored in `messages/messages.json` with the following structure:

```json
{
  "last_update_id": 12348,
  "messages": [
    {
      "user": "username",
      "type": "text",
      "content": "My journal entry for today",
      "time": "2025-10-30 14:30:00"
    },
    {
      "user": "username",
      "type": "photo",
      "content": "static/uploads/username_1730284200.jpg",
      "caption": "Beautiful sunset",
      "time": "2025-10-30 14:35:00"
    }
  ]
}
```

**Message Types:**
- `text` - Plain text messages
- `photo` - Images (JPG)
- `video` - Videos (MP4)
- `audio` - Audio files or voice messages (MP3/OGG)
- `document` - Files/documents
- `location` - GPS coordinates

## API Endpoints

### Web Interface

- `GET /` - Main web interface showing the latest 30 messages

### API Endpoints

- `GET /messages` - Get last 50 messages as JSON
- `GET /search` - Search messages with filters:
  - `username`: Filter by username
  - `start_time`: Start time in ISO 8601 format (e.g., "2025-10-29T06:00:00")
  - `end_time`: End time in ISO 8601 format

**Example Search:**
```
http://localhost:8000/search?username=YourName&start_time=2025-10-30T00:00:00
```

## Technical Details

### Update ID Tracking

The app uses Telegram's `update_id` mechanism to avoid duplicate messages:

- First run: Fetches all available updates
- Saves highest `update_id` to JSON
- Subsequent runs: Fetches only updates with `id > last_update_id`
- Guarantees no duplicate messages

### Media Handling

- All media files are downloaded to `static/uploads/`
- Filenames: `{username}_{timestamp}.{extension}`
- Original document names are preserved (spaces replaced with underscores)

## Troubleshooting

### Script exits immediately
Make sure you have the proper startup code at the end of `web_bot_bridge.py`:
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(web_app, host="0.0.0.0", port=8000)
```

### "No module named 'telegram'"
Install dependencies: `pip install -r requirements.txt`

### Bot doesn't respond
1. Make sure your bot token in `.env` is correct
2. Start a DM with your bot on Telegram first
3. Send a test message to the bot

### "TELEGRAM_BOT_TOKEN not found"
Create a `.env` file in the project root with:
```
TELEGRAM_BOT_TOKEN=your_actual_token_here
```

## Security Notes

- The server runs on all interfaces (0.0.0.0).
- Media files are stored locally without cleanup - monitor disk usage
- No authentication on web interface - only use on trusted networks
- Bot token should never be committed to version control (use `.env`)

## Future Implementations

- [ ] Audio transcription for voice messages
- [ ] User-wise data organization (multi-user support)

## Development

To run in development mode with auto-reload:

```powershell
uvicorn web_bot_bridge:web_app --reload --host 0.0.0.0 --port 8000
```

