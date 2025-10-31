# Telegram Journal

A FastAPI-based personal journal application that fetches messages from your Telegram bot and displays them in a web interface. Messages are fetched on-demand when you run the script, making it perfect for maintaining a personal journal.

## Features

  - **Fetch-on-Demand Architecture**: Run the script when you want to sync new messages.
  - **Incremental Sync**: Only fetches new messages since the last run using Telegram's `update_id`.
  - **🎤 Audio Transcription**: Automatically transcribes all voice and audio messages using Google's Gemini API.
  - **🗃️ Per-User Storage**: Automatically organizes messages into separate JSON files per user.
  - **Multiple Message Types**:
      - Text messages
      - Photos (with captions)
      - Videos (with captions)
      - Video notes (round messages)
      - Audio files (MP3/OGG)
      - Voice messages
      - Documents
      - Location sharing
  - **Web Interface**: Clean UI to view your journal entries.
  - **Media Storage**: Local file storage for all media.
  - **Search Functionality**: Filter by username and time range.

## How It Works

1.  **Send messages** to your Telegram bot (DM the bot directly).
2.  **Run the script** (`python web_bot_bridge.py`).
3.  The script fetches new messages, downloads media, and transcribes all audio.
4.  **View your journal** in the automatically-started web interface at `http://localhost:8000`.

The bot tracks the last fetched message using `update_id` (stored in `messages/metadata.json`), so subsequent runs only fetch new messages—no duplicates\!

## Prerequisites

  - Python 3.9+
  - Telegram Bot Token (from [@BotFather](https://t.me/botfather))
  - Google Gemini API Key (from [Google AI Studio](https://aistudio.google.com/))
  - Python virtual environment (strongly recommended)

## Dependencies

All project dependencies are listed in the `requirements.txt` file.

## Setup

1.  **Clone** the repository.

2.  **Create a virtual environment** and activate it:

    ```powershell
    # Create the environment
    python -m venv venv

    # Activate the environment (Windows PowerShell)
    .\venv\Scripts\Activate.ps1

    # Or for Linux/Mac
    source venv/bin/activate
    ```

3.  **Install all dependencies** using the `requirements.txt` file:

    ```powershell
    # Make sure your (venv) is active
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file** in the project root with your API keys:

    ```
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    GEMINI_API_KEY=your_gemini_api_key_here
    ```

5.  **Create your bot on Telegram**:

      - Open Telegram and search for [@BotFather](https://t.me/botfather).
      - Send `/newbot` and follow the instructions.
      - Copy the bot token to your `.env` file.
      - Start a direct message (DM) with your bot.

## Usage

### Running the Journal

```powershell
# Make sure your (venv) is active
python web_bot_bridge.py
```

**What happens:**

1.  Script loads `messages/metadata.json` to get the `last_update_id`.
2.  Scans `messages/users/` to load all existing messages into memory.
3.  Fetches only new messages from Telegram.
4.  Downloads any new media files to `static/uploads/`.
5.  **Transcribes** all new audio/voice messages using the Gemini API.
6.  Saves the new `last_update_id` to `messages/metadata.json`.
7.  Saves all new messages to the correct user file (e.g., `messages/users/your_username.json`).
8.  Starts the web server automatically at `http://localhost:8000`.
9.  Open your browser to view your journal.

**Console Output:**

```
🚀 Starting Telegram Journal - Fetch on Demand (User-based files)
Loading user messages from messages\users...
✅ Loaded 0 messages from 0 users.
🚀 Starting Telegram Journal Fetch...
📥 Fetching updates with offset: 123
📨 Found 1 new update(s)
✅ Processed message from Joe (audio) at 2025-10-30 23:36:45
💾 Saved 1 new message(s). Last update_id: 123

🎤 Starting transcription for 1 audio message(s)...
🎤 Transcribing: static/uploads/Joe_1761847605_voice.ogg
✅ Transcription complete: [The transcribed text will appear here]...
💾 Saved transcriptions to user files
✅ Fetch complete. Starting web server...
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Project Structure

```
Telegram_Journal/
├── web_bot_bridge.py      # Main application file
├── .env                   # Environment variables (TOKENS)
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── static/
│   └── uploads/           # Downloaded media files (photos, videos, audio)
├── messages/
│   ├── metadata.json      # Stores the single last_update_id "bookmark"
│   └── users/
│       ├── aryarishi.json # Messages for user 'aryarishi'
│       └── another.json   # Messages for 'another' user
└── venv/                  # Python virtual environment
```

## Data Storage

Your journal data is now split into two parts for better organization.

### 1\. Metadata (`messages/metadata.json`)

This file stores *only* the "bookmark" for the Telegram API.

```json
{
    "last_update_id": 123
}
```

### 2\. User Messages (`messages/users/<username>.json`)

Each user's messages are stored in their own file. The file is a **JSON list** of message objects.

**Example: `messages/users/joe.json`**

```json
[
    {
        "user": "Joe",
        "type": "text",
        "content": "My journal entry for today",
        "time": "2025-10-30 14:30:00"
    },
    {
        "user": "Joe",
        "type": "photo",
        "content": "static/uploads/Aryarishi_1730284200.jpg",
        "caption": "Beautiful sunset",
        "time": "2025-10-30 14:35:00"
    },
    {
        "user": "Joe",
        "type": "audio",
        "content": "static/uploads/Aryarishi_1761847605_voice.ogg",
        "time": "2025-10-30 23:36:45",
        "transcription": "This is the transcribed text from the audio."
    }
]
```

## API Endpoints

### Web Interface

  - `GET /` - Main web interface showing the latest 30 messages from all users.

### API Endpoints

  - `GET /messages` - Get last 50 messages as JSON.
  - `GET /search` - Search messages with filters:
      - `username`: Filter by username.
      - `start_time`: Start time in ISO 8601 format (e.g., "2025-10-29T06:00:00").
      - `end_time`: End time in ISO 8601 format.

**Example Search:**

```
http://localhost:8000/search?username=Aryarishi&start_time=2025-10-30T00:00:00
```

## Security Notes

  - The server runs on all interfaces (0.0.0.0).
  - Media files are stored locally without cleanup - monitor disk usage.
  - No authentication on web interface - only use on trusted networks.
  - Your API keys should **never** be committed to version control (the `.gitignore` file should list `.env`).

## Implementations

  - [x] **Audio transcription for voice messages** (Completed)
  - [x] **User-wise data organization** (Completed)

## Development

To run in development mode with auto-reload:

```powershell
uvicorn web_bot_bridge:web_app --reload --host 0.0.0.0 --port 8000
```