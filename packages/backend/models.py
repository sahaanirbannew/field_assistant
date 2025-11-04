from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List, Any

# --- Base Pydantic Model Configuration ---

class OrmBaseModel(BaseModel):
    """
    A base model that configures Pydantic to read data from
    database objects (ORM objects) as well as dictionaries.
    """
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
    timestamp: datetime
    raw_json: Optional[Any] = None 

# --- API Response Models ---

class MessageWithRelations(Message):
    """
    A full Message response model that includes the user who
    sent it and a list of any attached media.
    """
    user: Optional[User] = None
    media: List[Media] = []

