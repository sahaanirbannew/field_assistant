# Field Assistant 

An application to archive Telegram messages, media, and locations. It features a Python/FastAPI backend for data ingestion and a React/TypeScript frontend for viewing, filtering, and enriching your data with AI.

## Features

### 📦 Core Archiving

  - **Telegram Fetcher**: A script (`fetcher.py`) to fetch all new messages, media, and locations from your Telegram bot.
  - **PostgreSQL Storage**: All message text and metadata are stored in a SQL database.
  - **S3 Storage**: All media (photos, videos, audio, documents) are downloaded and archived in a private S3-compatible bucket.

### 🌐 Web Interface

  - **React + TypeScript UI**: A fast, modern, and type-safe web app to browse your archive.
  - **Dynamic Filters**: Filter your entire message history by user, start date, and end date.
  - **Secure Media**: Loads all media (images, video, audio) using secure, temporary (presigned) URLs from the backend.

### ✨ AI Enrichment (Gemini)

  - **AI Image Description**: Automatically generate descriptions for images using the Gemini vision model.
  - **AI Audio Transcription**: Automatically transcribe voice notes and audio files.
  - **Manual Override**: Manually edit or correct any AI-generated text, or add your own.

-----

## Tech Stack

  - **Backend**: **Python**, **FastAPI**, **PostgreSQL** (with `psycopg2`), **Boto3** (for S3)
  - **AI**: **Google Gemini** (`google-generativeai`)
  - **Frontend**: **TypeScript**, **React**, **Vite**, **Tailwind CSS**
  - **Data Model**: **Pydantic** (for API validation)

-----

## Project Structure

This project is a **monorepo** containing two main packages: `backend` and `frontend`.

```
field-assistant/
├── .env                  # Root config file (stores ALL secrets)
├── .gitignore            # Ignores venv, node_modules, .env, etc.
├── packages/
│   ├── backend/          # All Python code
│   │   ├── venv/         # Python virtual environment
│   │   ├── api.py        # The FastAPI web server
│   │   ├── db.py         # Shared database connection & schema
│   │   ├── fetcher.py    # The Telegram message fetcher
│   │   ├── models.py     # Pydantic data models for the API
│   │   ├── show_db.py    # CLI tool to view DB (optional)
│   │   └── requirements.txt
│   │
│   └── frontend/         # All React/TypeScript code
│       ├── node_modules/
│       ├── src/
│       │   ├── App.tsx   # The main React app component
│       │   ├── types.ts  # TypeScript types that match the API
│       │   └── index.css # Tailwind CSS directives
│       ├── package.json
│       └── tailwind.config.js
│
└── README.md             # This file
```

-----

## Prerequisites

  - Python 3.9+
  - Node.js v18+ (which includes `npm`)
  - PostgreSQL database server
  - S3-compatible storage (AWS S3, Cloudflare R2, or MinIO)
  - Telegram Bot Token (from [@BotFather](https://t.me/botfather))
  - Google Gemini API Key (from [Google AI Studio](https://aistudio.google.com/app/apikey))

-----

## Setup

1.  **Clone the Repository**

    ```bash
    git clone <your-repo-url>
    cd field-assistant
    ```

2.  **Configure Environment**
    Create a file named `.env` in the root of the project. Copy the contents of `.env.example` (if you have one) or use the template below.

    ```ini
    # Telegram
    TELEGRAM_BOT_TOKEN=your_bot_token_here

    # Database (local, Docker, or AWS RDS)
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=telegram_bot_db
    DB_USER=postgres
    DB_PASS=your_password

    # S3 Storage
    S3_BUCKET_NAME=your_bucket_name
    S3_ACCESS_KEY_ID=your_access_key
    S3_SECRET_ACCESS_KEY=your_secret_key
    S3_ENDPOINT_URL=https://xxx.r2.cloudflarestorage.com # Optional: for R2, MinIO

    # Google Gemini
    GOOGLE_API_KEY=your_gemini_api_key_here
    ```

3.  **Set Up the Backend (Python)**

    ```powershell
    # Navigate to the backend
    cd packages\backend

    # Create a virtual environment
    python -m venv venv

    # Activate it (Windows PowerShell)
    .\venv\Scripts\Activate.ps1

    # Install Python dependencies
    pip install -r requirements.txt

    # Run the db.py script once to create your database tables
    python db.py
    ```

4.  **Set Up the Frontend (React)**

    ```powershell
    # Go back to root, then to the frontend
    cd ..\frontend

    # Install Node.js dependencies
    npm install
    ```

-----

## Usage (Running the App)

You must run **two servers** at the same time in two separate terminals.

### Terminal 1: Run the Backend (FastAPI)

```powershell
# Navigate to the backend
cd packages\backend

# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Start the FastAPI server
uvicorn api:app --reload
```

Your API is now running at `http://127.0.0.1:8000`.

### Terminal 2: Run the Frontend (React)

```powershell
# Navigate to the frontend
cd packages\frontend

# Start the React development server
npm run dev
```

Your React app is now running at `http://localhost:5173`.

**Open `http://localhost:5173` in your browser** to use the web application.

-----

## Running the Fetcher

The web app *displays* data, but the `fetcher.py` script *gets* it. You can run this script manually whenever you want to archive new messages.

**Open a third terminal:**

```powershell
# Navigate to the backend
cd packages\backend

# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Run the fetcher
python fetcher.py
```

This will fetch all new messages, download media to S3, and save the metadata to your database. Your web app will show the new messages on the next refresh.

-----

## Development

  - **To modify the database schema:** Edit the `CREATE_TABLE_SQL` string in `packages/backend/db.py`.
  - **To modify the API data shape:** Update the Pydantic models in `packages/backend/models.py`.
  - **To modify the frontend data shape:** Update the TypeScript interfaces in `packages/frontend/src/types.ts` to match `models.py`.

