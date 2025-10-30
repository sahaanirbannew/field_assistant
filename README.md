
# Telegram Bot Bridge

A FastAPI-based web application that bridges Telegram messages with a web interface. It handles various types of media messages from Telegram and displays them in a web UI.

## Features

  - Handles multiple message types from Telegram:
      - Text messages
      - Photos (with captions)
      - Videos (with captions)
      - Video notes (round messages)
      - Audio files (MP3/OGG)
      - Voice messages
      - Documents
      - Location sharing
  - Web interface to view messages
  - Message persistence using JSON storage
  - Media file storage in local directory
  - Search functionality by username and time range

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

1.  **Clone** the repository.

2.  **Create a virtual environment** and activate it:

    ```powershell
    # Create the environment
    python -m venv venv

    # Activate the environment
    .\venv\Scripts\Activate.ps1
    ```

3.  **Install all dependencies** using the `requirements.txt` file:

    ```powershell
    # Make sure your (venv) is active
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file** in the project root with your Telegram bot token:

    ```
    TELEGRAM_BOT_TOKEN=your_bot_token_here
    ```

5.  **Start the server**:

    ```powershell
    # Make sure your (venv) is active
    uvicorn web_bot_bridge:web_app --host 0.0.0.0 --port 8000 --reload
    ```

    The server will start at `http://localhost:8000` and the Telegram bot will start polling in the background.

## Project Structure

```
Telegram_Bot/
├── web_bot_bridge.py      # Main application file
├── .env                   # Environment variables
├── requirements.txt       # Python dependencies
├── static/
│   └── uploads/           # Media files from Telegram
├── messages/
│   └── messages.json      # Message persistence
└── venv/                  # Python virtual environment
```

## API Endpoints

### Web Interface

  - `GET /` - Main web interface showing the latest 30 messages
  - `GET /static/*` - Static file serving (uploaded media)

### API Endpoints

  - `GET /messages` - Get all messages as JSON
  - `GET /search` - Search messages with filters:
      - `username`: Filter by username
      - `start_time`: Start time in ISO 8601 format (e.g., "2025-10-29T06:00:00")
      - `end_time`: End time in ISO 8601 format

## Message Storage

Messages are stored in `messages/messages.json` with the following structure:

```json
[
  {
    "user": "username",
    "type": "text|photo|video|audio|document|location",
    "content": "message_content_or_file_path",
    "time": "YYYY-MM-DD HH:MM:SS",
    "caption": "optional_caption"
  }
]
```

## Development

The application uses FastAPI's auto-reload feature (`--reload` flag). Any changes to the Python files will trigger an automatic reload of the server.

## Security Notes

  - The server is configured to run on all interfaces (0.0.0.0). In production, consider limiting this to specific interfaces.
  - Media files are stored in the `static/uploads` directory. Implement appropriate storage cleanup as needed.
  - Consider implementing authentication for the web interface in production.

## Error Handling

  - Missing environment variables will raise an error
  - Media download failures are logged but won't crash the application
  - JSON parsing errors for message storage will create a fresh message list

## Future Implementations

  - A text field in audio messages which will store the transcription
  - Fetch past chat messages from a single server fetch
  - Organizing the data (user-wise)