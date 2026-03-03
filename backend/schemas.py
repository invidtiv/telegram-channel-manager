"""Pydantic schemas for API requests/responses."""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


# ============== Tag Schemas ==============

class TagBase(BaseModel):
    name: str
    color: str = "#3B82F6"


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: datetime


class TagWithChannels(TagResponse):
    channels: List['ChannelResponse'] = []


# ============== Channel Schemas ==============

class ChannelBase(BaseModel):
    id: int
    bot_chat_id: str
    name: str
    username: Optional[str] = None
    type: str
    participants_count: Optional[int] = None
    is_verified: bool = False
    is_megagroup: bool = False
    about: Optional[str] = None


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    about: Optional[str] = None


class ChannelResponse(ChannelBase):
    model_config = ConfigDict(from_attributes=True)
    
    created_at: datetime
    updated_at: datetime
    tags: List[TagResponse] = []


# ============== Ingestion Schemas ==============

class IngestionStatus(BaseModel):
    status: str  # 'running', 'completed', 'error'
    total: int = 0
    processed: int = 0
    message: Optional[str] = None


class IngestionResponse(BaseModel):
    success: bool
    message: str
    channels_added: int = 0
    channels_updated: int = 0


# ============== Filter Schemas ==============

class ChannelFilter(BaseModel):
    tag_ids: Optional[List[int]] = None
    search: Optional[str] = None
    type: Optional[str] = None
