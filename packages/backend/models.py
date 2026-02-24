from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List, Any

# --- Base Pydantic Model Configuration ---

class OrmBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# --- Database Table Models ---

class User(OrmBaseModel):
    id: int
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    created_at: datetime

class Media(OrmBaseModel):
    id: int
    message_id: int
    media_type: str
    file_id: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    transcription: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class Message(OrmBaseModel):
    id: int
    telegram_message_id: int
    update_id: int
    user_id: Optional[int] = None
    chat_id: int
    text: Optional[str] = None
    survey_question: Optional[str] = None
    timestamp: datetime
    raw_json: Optional[Any] = None 

# --- API Response Models ---

class MessageWithRelations(Message):
    user: Optional[User] = None
    media: List[Media] = []

# --- Pagination Response Model ---
class PaginatedMessages(BaseModel):
    messages: List[MessageWithRelations]
    total_count: int
    total_pages: int
    current_page: int

# --- API Request Models ---

class GenerateRequest(BaseModel):
    prompt: Optional[str] = None

class UpdateDescriptionRequest(BaseModel):
    description: str = ""

class UpdateTranscriptionRequest(BaseModel):
    transcription: str = ""

class SummarizeRequest(BaseModel):
    full_text: str  # This is the concatenated blob
    prompt: Optional[str] = None

# --- NEW: Export Response Model ---
# This defines the "shape" of our new export.
# We are creating a simple model for the list items.
class ExportMessage(BaseModel):
    timestamp: str
    user: str
    text: Optional[str] = None
    image_description: Optional[str] = None
    audio_transcription: Optional[str] = None
    location: Optional[str] = None