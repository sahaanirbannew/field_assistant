import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import date, datetime
import psycopg2
import psycopg2.extras
import os
import boto3
import mimetypes 
import google.generativeai as genai
from PIL import Image
import io
import db
from models import MessageWithRelations, User, Media

# Pydantic models for API request bodies ---
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: Optional[str] = None

class UpdateDescriptionRequest(BaseModel):
    description: str = ""

class UpdateTranscriptionRequest(BaseModel):
    transcription: str = ""

# --- S3 Configuration ---
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')
S3_ACCESS_KEY_ID = os.environ.get('S3_ACCESS_KEY_ID')
S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRET_ACCESS_KEY')

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY_ID,
    aws_secret_access_key=S3_SECRET_ACCESS_KEY
)

# ---  Gemini Configuration ---
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not set. AI features will be disabled.")

# Use gemini-2.5-flash-preview-09-2025 for speed and multimodal capabilities
vision_model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")

# --- App Initialization ---
app = FastAPI(
    title="Field Assistant API",
    description="API for the Telegram bot archiver",
    version="1.0.0"
)

# --- CORS Configuration ---
origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Dependency ---
def get_db_connection():
    conn = db.get_conn()
    try:
        yield conn
    finally:
        conn.close()

# --- Helper function to get a single media item ---
def get_media_item(media_id: int, conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM media WHERE id = %s", (media_id,))
        media = cur.fetchone()
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        return media

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Welcome to the Field Assistant API!"}

@app.get("/media-url")
def get_media_url(key: str = Query(..., min_length=1)):
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket not configured")
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': key},
            ExpiresIn=3600
        )
        return {"url": url}
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate media URL")

@app.get("/users", response_model=List[User])
def get_all_users(conn: psycopg2.extensions.connection = Depends(get_db_connection)):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users ORDER BY first_name;")
        return cur.fetchall()

@app.get("/messages", response_model=List[MessageWithRelations])
def get_all_messages(
    conn: psycopg2.extensions.connection = Depends(get_db_connection),
    telegram_user_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None)
):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = """
            SELECT 
                m.id, m.telegram_message_id, m.update_id, m.user_id, 
                m.chat_id, m.text, m.timestamp, m.raw_json,
                to_jsonb(u) as user,
                COALESCE(
                    (SELECT jsonb_agg(med.* ORDER BY med.id) FROM media med WHERE med.message_id = m.id), 
                    '[]'::jsonb
                ) as media
            FROM 
                messages m
            LEFT JOIN 
                users u ON m.user_id = u.id
        """
        where_clauses = []
        params = []
        
        if telegram_user_id:
            where_clauses.append("u.telegram_user_id = %s")
            params.append(telegram_user_id)
        if start_date:
            where_clauses.append("m.timestamp >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("m.timestamp <= %s")
            params.append(end_date)
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        query += " ORDER BY m.timestamp DESC;"
        
        cur.execute(query, tuple(params))
        return cur.fetchall()

# --- NEW: Manual Update Endpoints ---

@app.put("/media/{media_id}/description", response_model=Media)
async def update_description(
    media_id: int, 
    payload: UpdateDescriptionRequest, 
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
    """Manually updates the description for any media item."""
    description = payload.description
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE media SET description = %s WHERE id = %s RETURNING *", 
            (description, media_id)
        )
        updated_media = cur.fetchone()
        conn.commit()
        if not updated_media:
            raise HTTPException(status_code=404, detail="Media not found")
        return updated_media

@app.put("/media/{media_id}/transcription", response_model=Media)
async def update_transcription(
    media_id: int, 
    payload: UpdateTranscriptionRequest, 
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
    """Manually updates the transcription for any media item."""
    transcription = payload.transcription
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE media SET transcription = %s WHERE id = %s RETURNING *", 
            (transcription, media_id)
        )
        updated_media = cur.fetchone()
        conn.commit()
        if not updated_media:
            raise HTTPException(status_code=404, detail="Media not found")
        return updated_media

# --- Gemini Generation Endpoints ---

@app.post("/media/{media_id}/generate-description", response_model=Media)
async def generate_description(
    media_id: int, 
    request: GenerateRequest,
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
    """Generates a description for an image using Gemini."""
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=501, detail="Gemini API key not configured")

    media = get_media_item(media_id, conn)
    if not media["file_path"]:
        raise HTTPException(status_code=400, detail="Media has no file path")

    try:
        # 1. Download image from S3
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=media["file_path"])
        image_bytes = obj['Body'].read()
        
        # 2. Load image with PIL
        img = Image.open(io.BytesIO(image_bytes))
        
        # 3. Send to Gemini
        prompt_text = request.prompt or "Describe this image for a field journal. Be concise and objective."
        response = await vision_model.generate_content_async([prompt_text, img])
        
        description = response.text
        
        # 4. Save to database
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE media SET description = %s WHERE id = %s RETURNING *",
                (description, media_id)
            )
            updated_media = cur.fetchone()
            conn.commit()
            return updated_media
            
    except Exception as e:
        print(f"Error generating description: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/media/{media_id}/generate-transcription", response_model=Media)
async def generate_transcription(
    media_id: int, 
    request: GenerateRequest,
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
    """Generates a transcription for an audio file using Gemini."""
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=501, detail="Gemini API key not configured")

    media = get_media_item(media_id, conn)
    if not media["file_path"]:
        raise HTTPException(status_code=400, detail="Media has no file path")

    audio_file = None # Define here so we can access in 'finally'
    try:
        # 1. Download audio from S3
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=media["file_path"])
        audio_bytes = obj['Body'].read()
        
        # Guess mime type if not present
        mime_type = media["mime_type"]
        if not mime_type:
            mime_type = mimetypes.guess_type(media["file_name"])[0]
        
        # 2. Upload to Gemini File API
        audio_file = genai.upload_file(
            path=io.BytesIO(audio_bytes),
            display_name=media["file_name"],
            mime_type=mime_type
        )
        
        # 3. Send to Gemini
        prompt_text = request.prompt or "Transcribe this audio. Only return the transcribed text."
        response = await vision_model.generate_content_async([prompt_text, audio_file])
        
        transcription = response.text
        
        # 4. Save to database
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE media SET transcription = %s WHERE id = %s RETURNING *",
                (transcription, media_id)
            )
            updated_media = cur.fetchone()
            conn.commit()
            return updated_media
            
    except Exception as e:
        print(f"Error generating transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 5. Clean up uploaded file from Gemini
        if audio_file:
            # Call genai.files.delete_file() (no 'await', no 'async')
            try:
                genai.files.delete_file(audio_file.name)
                print(f"Cleaned up Gemini file: {audio_file.name}")
            except Exception as e:
                # Don't crash the main request if cleanup fails
                print(f"Warning: Failed to delete Gemini file {audio_file.name}: {e}")

# --- Run the App ---
if __name__ == "__main__":
    print("Starting FastAPI server on http://127.0.0.1:8000")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)


from mangum import Mangum

handler = Mangum(app)

#--- comment ---