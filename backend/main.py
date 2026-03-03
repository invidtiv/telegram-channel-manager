"""FastAPI backend for Telegram Channel Manager."""

import os
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_db, AsyncSessionLocal
from models import Channel, Tag, channel_tags
from schemas import (
    ChannelCreate, ChannelResponse, ChannelUpdate,
    TagCreate, TagResponse, TagUpdate,
    IngestionResponse, ChannelFilter
)
from telethon_client import TelegramIngestion


# ============== Lifespan Management ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


# ============== FastAPI App ==============

app = FastAPI(
    title="Telegram Channel Manager API",
    description="API for managing Telegram channels with tagging support",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Channel Endpoints ==============

@app.get("/api/channels", response_model=List[ChannelResponse])
async def get_channels(
    tag_ids: Optional[str] = None,
    search: Optional[str] = None,
    channel_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all channels with optional filtering."""
    query = select(Channel).options(selectinload(Channel.tags))
    
    # Filter by tag IDs
    if tag_ids:
        tag_id_list = [int(t) for t in tag_ids.split(",")]
        query = query.join(channel_tags).where(channel_tags.c.tag_id.in_(tag_id_list))
    
    # Filter by search term
    if search:
        search_filter = or_(
            Channel.name.ilike(f"%{search}%"),
            Channel.username.ilike(f"%{search}%") if Channel.username else False
        )
        query = query.where(search_filter)
    
    # Filter by type
    if channel_type:
        query = query.where(Channel.type == channel_type)
    
    query = query.order_by(Channel.name)
    result = await db.execute(query)
    channels = result.scalars().unique().all()
    return channels


@app.get("/api/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single channel by ID."""
    query = select(Channel).options(selectinload(Channel.tags)).where(Channel.id == channel_id)
    result = await db.execute(query)
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    return channel


@app.put("/api/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    update_data: ChannelUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update channel details."""
    query = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(query)
    channel = result.scalar_one_or_none()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Update fields
    if update_data.name is not None:
        channel.name = update_data.name
    if update_data.username is not None:
        channel.username = update_data.username
    if update_data.about is not None:
        channel.about = update_data.about
    
    channel.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(channel)
    
    # Reload with tags
    query = select(Channel).options(selectinload(Channel.tags)).where(Channel.id == channel_id)
    result = await db.execute(query)
    return result.scalar_one()


@app.post("/api/channels/{channel_id}/tags/{tag_id}")
async def add_tag_to_channel(
    channel_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Add a tag to a channel."""
    # Check if channel exists
    channel_query = select(Channel).where(Channel.id == channel_id)
    channel_result = await db.execute(channel_query)
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check if tag exists
    tag_query = select(Tag).where(Tag.id == tag_id)
    tag_result = await db.execute(tag_query)
    tag = tag_result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # Check if association already exists
    assoc_query = select(channel_tags).where(
        and_(channel_tags.c.channel_id == channel_id, channel_tags.c.tag_id == tag_id)
    )
    assoc_result = await db.execute(assoc_query)
    if assoc_result.first():
        return {"message": "Tag already assigned to channel"}
    
    # Add association
    await db.execute(
        channel_tags.insert().values(channel_id=channel_id, tag_id=tag_id)
    )
    await db.commit()
    
    return {"message": "Tag added to channel"}


@app.delete("/api/channels/{channel_id}/tags/{tag_id}")
async def remove_tag_from_channel(
    channel_id: int,
    tag_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove a tag from a channel."""
    await db.execute(
        channel_tags.delete().where(
            and_(channel_tags.c.channel_id == channel_id, channel_tags.c.tag_id == tag_id)
        )
    )
    await db.commit()
    return {"message": "Tag removed from channel"}


# ============== Tag Endpoints ==============

@app.get("/api/tags", response_model=List[TagResponse])
async def get_tags(db: AsyncSession = Depends(get_db)):
    """Get all tags."""
    query = select(Tag).order_by(Tag.name)
    result = await db.execute(query)
    return result.scalars().all()


@app.post("/api/tags", response_model=TagResponse)
async def create_tag(tag_data: TagCreate, db: AsyncSession = Depends(get_db)):
    """Create a new tag."""
    # Check if tag name already exists
    existing = await db.execute(select(Tag).where(Tag.name == tag_data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    
    tag = Tag(name=tag_data.name, color=tag_data.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@app.put("/api/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a tag."""
    query = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(query)
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    if tag_data.name is not None:
        tag.name = tag_data.name
    if tag_data.color is not None:
        tag.color = tag_data.color
    
    await db.commit()
    await db.refresh(tag)
    return tag


@app.delete("/api/tags/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a tag."""
    query = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(query)
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    await db.delete(tag)
    await db.commit()
    return {"message": "Tag deleted"}


# ============== Ingestion Endpoints ==============

ingestion_status = {
    "running": False,
    "total": 0,
    "processed": 0,
    "message": ""
}


@app.get("/api/ingestion/status")
async def get_ingestion_status():
    """Get current ingestion status."""
    return ingestion_status


@app.post("/api/ingestion/start", response_model=IngestionResponse)
async def start_ingestion(background_tasks: BackgroundTasks):
    """Start a new ingestion from Telegram."""
    if ingestion_status["running"]:
        raise HTTPException(status_code=409, detail="Ingestion already running")
    
    background_tasks.add_task(run_ingestion_task)
    return IngestionResponse(success=True, message="Ingestion started")


async def run_ingestion_task():
    """Background task for ingestion."""
    global ingestion_status
    ingestion_status["running"] = True
    ingestion_status["message"] = "Connecting to Telegram..."
    
    async with AsyncSessionLocal() as db:
        try:
            ingestor = TelegramIngestion(db)
            result = await ingestor.run_ingestion(ingestion_status)
            ingestion_status.update({
                "running": False,
                "message": f"Completed: {result['channels_added']} added, {result['channels_updated']} updated"
            })
        except Exception as e:
            ingestion_status.update({
                "running": False,
                "message": f"Error: {str(e)}"
            })


# ============== Health Check ==============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
