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
import math

# Import our shared database and models
import db
from models import MessageWithRelations, User, Media, PaginatedMessages

# --- Pydantic models for API request bodies ---
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

# --- Gemini Configuration ---
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not set. AI features will be disabled.")

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
    "https://main.d3i2w4tw6z3szj.amplifyapp.com",
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

@app.get("/messages", response_model=PaginatedMessages)
def get_all_messages(
    conn: psycopg2.extensions.connection = Depends(get_db_connection),
    # Filter params
    telegram_user_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    # Pagination params
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100)
):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        
        # --- Build WHERE clause for filters ---
        where_clauses = []
        filter_params = []
        join_clause = "LEFT JOIN users u ON m.user_id = u.id" 
        
        if telegram_user_id:
            where_clauses.append("u.telegram_user_id = %s")
            filter_params.append(telegram_user_id)
        if start_date:
            where_clauses.append("m.timestamp >= %s")
            filter_params.append(start_date)
        if end_date:
            where_clauses.append("m.timestamp <= %s")
            filter_params.append(end_date)
        
        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)
            
        # --- 1. Get TOTAL COUNT query ---
        count_query = f"""
            SELECT COUNT(m.id) 
            FROM messages m 
            {join_clause}
            {where_sql};
        """
        cur.execute(count_query, tuple(filter_params))
        total_count = cur.fetchone()['count']
        
        if total_count == 0:
            return {
                "messages": [],
                "total_count": 0,
                "total_pages": 0,
                "current_page": 1
            }

        # --- 2. Calculate pagination details ---
        total_pages = math.ceil(total_count / limit)
        offset = (page - 1) * limit
        
        # --- 3. Get paginated messages query ---
        main_query = f"""
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
            {join_clause}
            {where_sql}
            ORDER BY m.timestamp DESC
            LIMIT %s OFFSET %s;
        """
        
        final_params = tuple(filter_params) + (limit, offset)
        cur.execute(main_query, final_params)
        messages = cur.fetchall()
        
        # --- 4. Return the full paginated object ---
        return {
            "messages": messages,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page
        }

@app.put("/media/{media_id}/description", response_model=Media)
async def update_description(
    media_id: int, 
    payload: UpdateDescriptionRequest,
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
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

@app.post("/media/{media_id}/generate-description", response_model=Media)
async def generate_description(
    media_id: int,
    request: GenerateRequest,
    conn: psycopg2.extensions.connection = Depends(get_db_connection)
):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=501, detail="Gemini API key not configured")
    media = get_media_item(media_id, conn)
    if not media["file_path"]:
        raise HTTPException(status_code=400, detail="Media has no file path")
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=media["file_path"])
        image_bytes = obj['Body'].read()
        img = Image.open(io.BytesIO(image_bytes))
        prompt_text = request.prompt or "Describe this image for a field journal. Be concise and objective."
        response = await vision_model.generate_content_async([prompt_text, img])
        description = response.text
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
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=501, detail="Gemini API key not configured")
    media = get_media_item(media_id, conn)
    if not media["file_path"]:
        raise HTTPException(status_code=400, detail="Media has no file path")
    
    audio_file = None
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=media["file_path"])
        audio_bytes = obj['Body'].read()
        mime_type = media["mime_type"] or mimetypes.guess_type(media["file_name"])[0]
        
        audio_file = genai.upload_file(
            path=io.BytesIO(audio_bytes),
            display_name=media["file_name"],
            mime_type=mime_type
        )
        
        prompt_text = request.prompt or "Transcribe this audio. Only return the transcribed text."
        response = await vision_model.generate_content_async([prompt_text, audio_file])
        transcription = response.text
        
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
        # Clean up the file from Gemini
        if audio_file:
            try:
                # --- This is the fix for the delete_file_async error ---
                genai.files.delete_file(audio_file.name)
                print(f"Cleaned up Gemini file: {audio_file.name}")
            except Exception as e:
                print(f"Warning: Failed to delete Gemini file {audio_file.name}: {e}")

# --- Run the App ---
if __name__ == "__main__":
    print("Starting FastAPI server on http://127.0.0.1:8000")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)

# --- DEPLOYMENT HANDLER FOR AWS LAMBDA ---
from mangum import Mangum

# This 'handler' is the entry point for AWS Lambda
handler = Mangum(app)