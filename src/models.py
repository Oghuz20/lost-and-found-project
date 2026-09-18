from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ItemBase(BaseModel):
    user_text: str
    image_path: str

class Item(ItemBase):
    id: int
    status: str
    vlm_description: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

class MatchRecord(BaseModel):
    id: int
    lost_item_id: int
    found_item_id: int
    score: float
    reason: str