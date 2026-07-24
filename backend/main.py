"""FastAPI backend for Telegram Channel Manager."""

import os
import sys
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, cast, String
from sqlalchemy.orm import selectinload

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_db, AsyncSessionLocal
from models import Channel, Tag, channel_tags, GroupMember, Bot, BotCommand, BotHistory, ScanRun, TokenOccurrence
from schemas import (
    ChannelCreate, ChannelResponse, ChannelUpdate,
    TagCreate, TagResponse, TagUpdate,
    IngestionResponse, ChannelFilter,
    TelegramPhoneRequest, TelegramCodeRequest, TelegramPasswordRequest,
    TelegramAuthCancelRequest, TelegramAuthStatusResponse,
    MemberResponse, MemberFetchResponse,
    BotCreate, BotResponse, BotUpdate,
    BotCommandCreate, BotCommandResponse,
    BotHistoryEntry, BotImportResponse,
    ScanInventory, ScanRequest, ScanRunResponse,
    BotAssignRequest,
)
from telethon_client import TelegramIngestion
from telegram_auth import TelegramAuthError, TelegramAuthManager
from scanner import run_scan, resync_inventory
from botfather_parser import parse_botfather_history


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


@app.middleware("http")
async def disable_telegram_auth_caching(request: Request, call_next):
    """Keep authorization state and responses out of browser/proxy caches."""
    response = await call_next(request)
    if request.url.path.startswith("/api/telegram-auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def redact_telegram_auth_validation_errors(
    request: Request,
    error: RequestValidationError,
):
    """Avoid echoing phone, code, or password values in validation responses."""
    if request.url.path.startswith("/api/telegram-auth/"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "invalid_auth_input",
                    "message": "Invalid Telegram authorization input.",
                }
            },
            headers={"Cache-Control": "no-store"},
        )
    return await request_validation_exception_handler(request, error)


# ============== Channel Endpoints ==============

def _search_tokens(search: str) -> List[str]:
    """Split a search string into non-empty tokens."""
    return [token.strip() for token in search.split() if token.strip()]


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
        tokens = _search_tokens(search)
        search_filters = []
        for token in tokens:
            pattern = f"%{token}%"
            search_filters.append(or_(
                Channel.name.ilike(pattern),
                Channel.username.ilike(pattern),
                Channel.bot_chat_id.ilike(pattern),
                cast(Channel.id, String).ilike(pattern),
                Channel.about.ilike(pattern),
            ))
        if search_filters:
            query = query.where(and_(*search_filters))
    
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


# ============== Bot Registry Helpers ==============

TOKEN_REGEX = r'[0-9]{8,10}:[A-Za-z0-9_-]{35}'


def _default_settings():
    return {
        "privacy_mode": True,
        "inline_mode": False,
        "inline_placeholder": "",
        "inline_feedback_enabled": False,
        "inline_geo_enabled": False,
        "can_join_groups": True,
        "can_join_channels": False,
        "requires_admin_rights": False,
        "supports_inline_queries": False,
        "business_mode_enabled": False,
        "menu_button_type": "default",
        "web_app_url": "",
        "payments_enabled": False,
        "payment_provider": "",
        "commands": []
    }


def _settings_to_db(settings) -> dict:
    if settings is None:
        return _default_settings()
    data = settings.model_dump()
    data.setdefault("commands", [cmd.model_dump() for cmd in settings.commands] if settings.commands else [])
    return data


def _settings_from_db(data: dict):
    if not data:
        return _default_settings()
    return data


def _bot_to_response(bot: Bot) -> dict:
    """Convert a Bot ORM instance to a dict matching BotResponse."""
    return {
        "id": bot.id,
        "token": bot.token,
        "username": bot.username,
        "display_name": bot.display_name,
        "description": bot.description,
        "about_text": bot.about_text,
        "avatar_url": bot.avatar_url,
        "project": bot.project,
        "environment": bot.environment,
        "status": bot.status,
        "tags": bot.tags or [],
        "use_case": bot.use_case,
        "location": bot.location,
        "notes": bot.notes,
        "settings": _settings_from_db(bot.settings),
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
        "commands": [
            {
                "id": c.id,
                "bot_id": c.bot_id,
                "command": c.command,
                "description": c.description,
                "scope": c.scope,
                "language_code": c.language_code,
            }
            for c in bot.commands
        ],
        "history": [
            {
                "timestamp": h.timestamp,
                "action": h.action,
                "field": h.field,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "note": h.note,
            }
            for h in bot.history
        ],
    }


async def _log_history(db: AsyncSession, bot_id: str, action: str, field: str, new_value, old_value=None, note=None):
    entry = BotHistory(
        bot_id=bot_id,
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
        note=note,
    )
    db.add(entry)


# ============== Bot Registry Endpoints ==============

def _parse_datetime(value):
    """Parse an ISO datetime string or return a datetime object unchanged."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Replace trailing Z with +00:00 for older Python compatibility
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Cannot parse datetime value: {value!r}")


@app.post("/api/bots/import-botfather", response_model=BotImportResponse)
async def import_botfather_history(payload: dict, db: AsyncSession = Depends(get_db)):
    """Import bots from a Telegram Desktop BotFather chat history JSON export.

    Also marks bots as deleted when BotFather deletion events are found.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload: expected JSON object")

    parsed = parse_botfather_history(payload, project="botfather")
    bots = parsed["bots"]
    deleted_usernames = parsed["deleted_usernames"]

    if not bots and not deleted_usernames:
        raise HTTPException(status_code=400, detail="No bots or deletion events found in BotFather history")

    result = await import_bots({"bots": bots}, db)

    if deleted_usernames:
        deleted_count = 0
        for username in deleted_usernames:
            bot_result = await db.execute(select(Bot).where(Bot.username == username).limit(1))
            bot = bot_result.scalar_one_or_none()
            if bot:
                bot.status = "deleted"
                bot.updated_at = datetime.utcnow()
                deleted_count += 1
        await db.commit()
        result.deleted = deleted_count

    return result


@app.post("/api/bots/import", response_model=BotImportResponse)
async def import_bots(payload: dict, db: AsyncSession = Depends(get_db)):
    """Import bots from a TGsecrets registry JSON payload.

    Expects: {"meta": {...}, "bots": [...]} or a top-level list of bots.
    """
    bots = []
    if "bots" in payload:
        bots = payload["bots"]
    elif isinstance(payload, list):
        bots = payload
    else:
        raise HTTPException(status_code=400, detail="Invalid payload: expected 'bots' array or top-level list")

    added = 0
    skipped = 0
    errors = []

    for item in bots:
        try:
            settings = item.get("settings", {})
            commands = settings.get("commands", [])
            bot_id = item.get("id") or str(uuid.uuid4())

            # Skip if a bot with this ID or token already exists
            existing = await db.execute(
                select(Bot).where((Bot.id == bot_id) | (Bot.token == item.get("token", ""))).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            now = datetime.utcnow()
            created_at = _parse_datetime(item.get("createdAt", now)) or now
            updated_at = _parse_datetime(item.get("updatedAt", now)) or now
            bot = Bot(
                id=bot_id,
                token=item.get("token", ""),
                username=item.get("username", ""),
                display_name=item.get("displayName", ""),
                description=item.get("description", ""),
                about_text=item.get("aboutText", ""),
                avatar_url=item.get("avatarUrl", ""),
                project=item.get("project", ""),
                environment=item.get("environment", "development"),
                status=item.get("status", "active"),
                tags=item.get("tags", []),
                use_case=item.get("useCase", ""),
                location=item.get("location", ""),
                notes=item.get("notes", ""),
                settings={
                    "privacy_mode": settings.get("privacyMode", True),
                    "inline_mode": settings.get("inlineMode", False),
                    "inline_placeholder": settings.get("inlinePlaceholder", ""),
                    "inline_feedback_enabled": settings.get("inlineFeedbackEnabled", False),
                    "inline_geo_enabled": settings.get("inlineGeoEnabled", False),
                    "can_join_groups": settings.get("canJoinGroups", True),
                    "can_join_channels": settings.get("canJoinChannels", False),
                    "requires_admin_rights": settings.get("requiresAdminRights", False),
                    "supports_inline_queries": settings.get("supportsInlineQueries", False),
                    "business_mode_enabled": settings.get("businessModeEnabled", False),
                    "menu_button_type": settings.get("menuButtonType", "default"),
                    "web_app_url": settings.get("webAppUrl", ""),
                    "payments_enabled": settings.get("paymentsEnabled", False),
                    "payment_provider": settings.get("paymentProvider", ""),
                    "commands": commands,
                },
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(bot)

            for cmd in commands:
                db.add(BotCommand(
                    bot_id=bot_id,
                    command=cmd.get("command", ""),
                    description=cmd.get("description", ""),
                    scope=cmd.get("scope", "default"),
                    language_code=cmd.get("languageCode"),
                ))

            for hist in item.get("history", []):
                db.add(BotHistory(
                    bot_id=bot_id,
                    timestamp=_parse_datetime(hist.get("timestamp", now)) or now,
                    action=hist.get("action", "created"),
                    field=hist.get("field", "*"),
                    old_value=hist.get("oldValue"),
                    new_value=hist.get("newValue"),
                    note=hist.get("note"),
                ))

            added += 1
        except Exception as e:
            errors.append(f"Failed to import {item.get('username', 'unknown')}: {str(e)}")

    await db.commit()
    return BotImportResponse(success=len(errors) == 0, added=added, errors=errors, skipped=skipped)


@app.get("/api/bots/projects/environments")
async def get_bot_metadata(db: AsyncSession = Depends(get_db)):
    """Return distinct projects, environments, and tags for filters."""
    projects = await db.execute(select(Bot.project).distinct())
    environments = await db.execute(select(Bot.environment).distinct())
    tags = set()
    for row in await db.execute(select(Bot.tags)):
        tags.update(row[0] or [])
    return {
        "projects": [p for p in projects.scalars().all() if p],
        "environments": [e for e in environments.scalars().all() if e],
        "tags": sorted(tags),
    }


# ============== Bot Scanner Endpoints ==============

scan_status = {
    "running": False,
    "message": "",
}


@app.get("/api/bots/inventory", response_model=ScanInventory)
async def get_inventory(db: AsyncSession = Depends(get_db)):
    """Get current token inventory without running a new scan."""
    return await resync_inventory(db)


@app.post("/api/bots/scan", response_model=ScanInventory)
async def start_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a filesystem/Docker token scan."""
    if scan_status["running"]:
        raise HTTPException(status_code=409, detail="Scan already in progress")
    background_tasks.add_task(run_scan_task, request.mode)
    scan_status["running"] = True
    scan_status["message"] = "Scan started..."
    return await resync_inventory(db)


async def run_scan_task(mode: str):
    """Background task for token scanning."""
    global scan_status
    scan_status["running"] = True
    scan_status["message"] = "Scanning filesystem and Docker..."
    async with AsyncSessionLocal() as db:
        try:
            await run_scan(db, mode)
            scan_status["running"] = False
            scan_status["message"] = "Scan completed"
        except Exception as e:
            scan_status["running"] = False
            scan_status["message"] = f"Scan failed: {str(e)}"


@app.post("/api/bots/assign", response_model=BotResponse)
async def assign_token_to_bot(request: BotAssignRequest, db: AsyncSession = Depends(get_db)):
    """Create a new Bot registry entry from an unassigned found token."""
    # Find the most recent occurrence with this fingerprint to get the token
    result = await db.execute(
        select(TokenOccurrence)
        .where(TokenOccurrence.token_fingerprint == request.token_fingerprint)
        .order_by(TokenOccurrence.last_seen.desc())
        .limit(1)
    )
    occurrence = result.scalar_one_or_none()
    if not occurrence:
        raise HTTPException(status_code=404, detail="Token fingerprint not found in scan results")

    # Make sure it isn't already registered
    existing = await db.execute(
        select(Bot).where(Bot.token == occurrence.token).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A bot with this token already exists")

    now = datetime.utcnow()
    bot_id = str(uuid.uuid4())
    bot = Bot(
        id=bot_id,
        token=occurrence.token,
        username=request.username or occurrence.bot_id,
        display_name=request.display_name or request.username or occurrence.bot_id,
        description="",
        about_text="",
        avatar_url="",
        project=request.project,
        environment=request.environment,
        status="active",
        tags=[],
        use_case="",
        location="",
        notes=request.notes or f"Assigned from scan occurrence: {occurrence.source_label}",
        settings={
            "privacy_mode": True,
            "inline_mode": False,
            "inline_placeholder": "",
            "inline_feedback_enabled": False,
            "inline_geo_enabled": False,
            "can_join_groups": True,
            "can_join_channels": False,
            "requires_admin_rights": False,
            "supports_inline_queries": False,
            "business_mode_enabled": False,
            "menu_button_type": "default",
            "web_app_url": "",
            "payments_enabled": False,
            "payment_provider": "",
            "commands": [],
        },
        created_at=now,
        updated_at=now,
    )
    db.add(bot)
    await _log_history(db, bot_id, "created", "*", "Bot entry created from scan", note=f"Source: {occurrence.source_label}")
    await db.commit()

    result = await db.execute(
        select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history)).where(Bot.id == bot_id)
    )
    bot = result.scalar_one()
    return _bot_to_response(bot)


@app.get("/api/bots", response_model=List[BotResponse])
async def get_bots(
    search: Optional[str] = None,
    project: Optional[str] = None,
    environment: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all bot registry entries with optional filtering."""
    query = select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history))

    if search:
        pattern = f"%{search}%"
        query = query.where(or_(
            Bot.username.ilike(pattern),
            Bot.display_name.ilike(pattern),
            Bot.project.ilike(pattern),
            Bot.notes.ilike(pattern),
        ))
    if project:
        query = query.where(Bot.project.ilike(f"%{project}%"))
    if environment:
        query = query.where(Bot.environment == environment)
    if status:
        query = query.where(Bot.status == status)
    if tag:
        query = query.where(Bot.tags.contains([tag]))

    query = query.order_by(Bot.updated_at.desc())
    result = await db.execute(query)
    return [_bot_to_response(bot) for bot in result.scalars().unique().all()]


@app.get("/api/bots/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single bot by ID."""
    query = select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history)).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _bot_to_response(bot)


@app.post("/api/bots", response_model=BotResponse)
async def create_bot(bot_data: BotCreate, db: AsyncSession = Depends(get_db)):
    """Create a new bot registry entry."""
    now = datetime.utcnow()
    bot_id = str(uuid.uuid4())
    settings_db = _settings_to_db(bot_data.settings)

    bot = Bot(
        id=bot_id,
        token=bot_data.token,
        username=bot_data.username,
        display_name=bot_data.display_name or bot_data.username,
        description=bot_data.description,
        about_text=bot_data.about_text,
        avatar_url=bot_data.avatar_url,
        project=bot_data.project,
        environment=bot_data.environment,
        status=bot_data.status,
        tags=bot_data.tags or [],
        use_case=bot_data.use_case,
        location=bot_data.location,
        notes=bot_data.notes,
        settings=settings_db,
        created_at=now,
        updated_at=now,
    )
    db.add(bot)

    # Add commands
    for cmd in settings_db.get("commands", []):
        db.add(BotCommand(
            bot_id=bot_id,
            command=cmd.get("command", ""),
            description=cmd.get("description", ""),
            scope=cmd.get("scope", "default"),
            language_code=cmd.get("language_code"),
        ))

    await _log_history(db, bot_id, "created", "*", "Bot entry created", note="Created via API")
    await db.commit()
    await db.refresh(bot)
    # Re-fetch with eager-loaded relationships to avoid lazy-loading in async mode
    result = await db.execute(
        select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history)).where(Bot.id == bot_id)
    )
    bot = result.scalar_one()
    return _bot_to_response(bot)


@app.put("/api/bots/{bot_id}", response_model=BotResponse)
async def update_bot(bot_id: str, update_data: BotUpdate, db: AsyncSession = Depends(get_db)):
    """Update a bot registry entry."""
    query = select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history)).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    fields = [
        "token", "username", "display_name", "description", "about_text", "avatar_url",
        "project", "environment", "status", "tags", "use_case", "location", "notes"
    ]
    for field in fields:
        value = getattr(update_data, field, None)
        if value is not None:
            old = getattr(bot, field)
            await _log_history(db, bot_id, "updated", field, value, old)
            setattr(bot, field, value)

    if update_data.settings is not None:
        new_settings = _settings_to_db(update_data.settings)
        await _log_history(db, bot_id, "updated", "settings", new_settings, bot.settings)
        bot.settings = new_settings
        # Replace commands
        for cmd in bot.commands:
            await db.delete(cmd)
        for cmd in new_settings.get("commands", []):
            db.add(BotCommand(
                bot_id=bot_id,
                command=cmd.get("command", ""),
                description=cmd.get("description", ""),
                scope=cmd.get("scope", "default"),
                language_code=cmd.get("language_code"),
            ))

    bot.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(bot)
    # Re-fetch with eager-loaded relationships to avoid lazy-loading in async mode
    result = await db.execute(
        select(Bot).options(selectinload(Bot.commands), selectinload(Bot.history)).where(Bot.id == bot_id)
    )
    bot = result.scalar_one()
    return _bot_to_response(bot)


@app.delete("/api/bots/{bot_id}")
async def delete_bot(bot_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a bot registry entry."""
    query = select(Bot).where(Bot.id == bot_id)
    result = await db.execute(query)
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    await db.delete(bot)
    await db.commit()
    return {"message": "Bot deleted"}


# ============== Ingestion Endpoints ==============

telegram_auth_manager = TelegramAuthManager()


def _raise_telegram_auth_error(error: TelegramAuthError):
    headers = {}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
        headers=headers or None,
    )


@app.get(
    "/api/telegram-auth/status",
    response_model=TelegramAuthStatusResponse,
)
async def get_telegram_auth_status():
    """Return whether the persisted Telegram user session is authorized."""
    try:
        return await telegram_auth_manager.get_status()
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)


@app.post(
    "/api/telegram-auth/request-code",
    response_model=TelegramAuthStatusResponse,
)
async def request_telegram_auth_code(payload: TelegramPhoneRequest):
    """Ask Telegram to send a verification code to a validated phone number."""
    try:
        return await telegram_auth_manager.request_code(payload.phone)
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)


@app.post(
    "/api/telegram-auth/submit-code",
    response_model=TelegramAuthStatusResponse,
)
async def submit_telegram_auth_code(payload: TelegramCodeRequest):
    """Submit a Telegram verification code for the active authorization attempt."""
    try:
        return await telegram_auth_manager.submit_code(payload.code)
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)


@app.post(
    "/api/telegram-auth/submit-password",
    response_model=TelegramAuthStatusResponse,
)
async def submit_telegram_auth_password(payload: TelegramPasswordRequest):
    """Complete Telegram two-step verification when the account requires it."""
    try:
        return await telegram_auth_manager.submit_password(payload.password)
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)


@app.post(
    "/api/telegram-auth/cancel",
    response_model=TelegramAuthStatusResponse,
)
async def cancel_telegram_auth(_payload: TelegramAuthCancelRequest):
    """Discard the current in-memory authorization attempt."""
    return await telegram_auth_manager.cancel()


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

    try:
        auth_status = await telegram_auth_manager.get_status()
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)
    if not auth_status["authorized"]:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "telegram_auth_required",
                "message": auth_status["message"],
                "state": auth_status["state"],
            },
        )
    
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


# ============== Member Endpoints ==============

member_fetch_status = {
    "running": False,
    "total": 0,
    "processed": 0,
    "message": ""
}


@app.get("/api/channels/{channel_id}/members", response_model=List[MemberResponse])
async def get_members(
    channel_id: int,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get saved members for a channel/group."""
    query = select(GroupMember).where(GroupMember.channel_id == channel_id)

    if search:
        tokens = _search_tokens(search)
        member_filters = []
        for token in tokens:
            pattern = f"%{token}%"
            member_filters.append(or_(
                GroupMember.first_name.ilike(pattern),
                GroupMember.last_name.ilike(pattern),
                GroupMember.username.ilike(pattern),
                GroupMember.phone.ilike(pattern),
                cast(GroupMember.user_id, String).ilike(pattern),
            ))
        if member_filters:
            query = query.where(and_(*member_filters))

    query = query.order_by(GroupMember.first_name)
    result = await db.execute(query)
    return result.scalars().all()


@app.get("/api/channels/{channel_id}/members/status")
async def get_member_fetch_status():
    """Get current member fetch status."""
    return member_fetch_status


@app.post("/api/channels/{channel_id}/members/fetch", response_model=MemberFetchResponse)
async def fetch_members(
    channel_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Fetch members from Telegram via MTProto and save to DB."""
    if member_fetch_status["running"]:
        raise HTTPException(status_code=409, detail="Member fetch already running")

    try:
        auth_status = await telegram_auth_manager.get_status()
    except TelegramAuthError as error:
        _raise_telegram_auth_error(error)
    if not auth_status["authorized"]:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "telegram_auth_required",
                "message": auth_status["message"],
                "state": auth_status["state"],
            },
        )

    # Verify channel exists
    channel_query = select(Channel).where(Channel.id == channel_id)
    channel_result = await db.execute(channel_query)
    channel = channel_result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    background_tasks.add_task(run_member_fetch_task, channel_id)
    return MemberFetchResponse(success=True, message=f"Fetching members for {channel.name}...")


async def run_member_fetch_task(channel_id: int):
    """Background task for member fetching."""
    global member_fetch_status
    member_fetch_status = {"running": True, "total": 0, "processed": 0, "message": "Connecting..."}

    async with AsyncSessionLocal() as db:
        try:
            fetcher = TelegramIngestion(db)
            result = await fetcher.fetch_members(channel_id, member_fetch_status)
            member_fetch_status.update({
                "running": False,
                "message": f"Done: {result['members_added']} added, {result['members_updated']} updated ({result['total']} total)"
            })
        except Exception as e:
            member_fetch_status.update({
                "running": False,
                "message": f"Error: {str(e)}"
            })


@app.get("/api/channels/{channel_id}/members/export")
async def export_members(
    channel_id: int,
    format: str = "json",
    db: AsyncSession = Depends(get_db)
):
    """Export members as JSON or CSV."""
    query = select(GroupMember).where(GroupMember.channel_id == channel_id).order_by(GroupMember.first_name)
    result = await db.execute(query)
    members = result.scalars().all()

    if not members:
        raise HTTPException(status_code=404, detail="No members found for this channel")

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["user_id", "first_name", "last_name", "username", "phone", "is_bot", "is_premium", "status", "fetched_at"])
        for m in members:
            writer.writerow([m.user_id, m.first_name, m.last_name, m.username, m.phone, m.is_bot, m.is_premium, m.status, m.fetched_at.isoformat()])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=members_{channel_id}.csv"}
        )
    else:
        import json
        data = [
            {
                "user_id": m.user_id,
                "first_name": m.first_name,
                "last_name": m.last_name,
                "username": m.username,
                "phone": m.phone,
                "is_bot": m.is_bot,
                "is_premium": m.is_premium,
                "status": m.status,
                "fetched_at": m.fetched_at.isoformat(),
            }
            for m in members
        ]
        content = json.dumps(data, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=members_{channel_id}.json"}
        )


# ============== Health Check ==============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============== Static Files (production) ==============

# Mount built frontend if available (Docker production mode)
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
