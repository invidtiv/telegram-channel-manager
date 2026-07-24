"""Pydantic schemas for API requests/responses."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Any, Literal
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


# ============== Telegram Authorization Schemas ==============

class TelegramPhoneRequest(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9]\d{6,14}$", max_length=16)

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value):
        if isinstance(value, str):
            return "".join(character for character in value if character not in " -()")
        return value


class TelegramCodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{1,10}$", max_length=10)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value):
        if isinstance(value, str):
            return "".join(value.split())
        return value


class TelegramPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class TelegramAuthCancelRequest(BaseModel):
    pass


class TelegramAuthStatusResponse(BaseModel):
    authorized: bool
    state: Literal[
        "authorized",
        "phone_required",
        "code_required",
        "password_required",
    ]
    message: str
    expires_in: Optional[int] = None


# ============== Member Schemas ==============

class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    is_bot: bool = False
    is_premium: bool = False
    status: Optional[str] = None
    fetched_at: datetime


class MemberFetchResponse(BaseModel):
    success: bool
    message: str
    members_added: int = 0
    members_updated: int = 0
    total: int = 0


# ============== Filter Schemas ==============

class ChannelFilter(BaseModel):
    tag_ids: Optional[List[int]] = None
    search: Optional[str] = None
    type: Optional[str] = None


# ============== Bot Command Schemas ==============

class BotCommandBase(BaseModel):
    command: str
    description: str
    scope: str = "default"
    language_code: Optional[str] = None


class BotCommandCreate(BotCommandBase):
    pass


class BotCommandResponse(BotCommandBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_id: str


# ============== Bot History Schemas ==============

class BotHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    action: str
    field: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    note: Optional[str] = None


# ============== Bot Settings Schemas ==============

class BotSettings(BaseModel):
    privacy_mode: bool = True
    inline_mode: bool = False
    inline_placeholder: str = ""
    inline_feedback_enabled: bool = False
    inline_geo_enabled: bool = False
    can_join_groups: bool = True
    can_join_channels: bool = False
    requires_admin_rights: bool = False
    supports_inline_queries: bool = False
    business_mode_enabled: bool = False
    menu_button_type: str = "default"
    web_app_url: str = ""
    payments_enabled: bool = False
    payment_provider: str = ""
    commands: List[BotCommandCreate] = []


# ============== Bot Schemas ==============

class BotBase(BaseModel):
    token: str
    username: str
    display_name: Optional[str] = ""
    description: Optional[str] = ""
    about_text: Optional[str] = ""
    avatar_url: Optional[str] = ""
    project: Optional[str] = ""
    environment: Optional[str] = "development"
    status: Optional[str] = "active"
    tags: Optional[List[str]] = []
    use_case: Optional[str] = ""
    location: Optional[str] = ""
    notes: Optional[str] = ""
    settings: Optional[BotSettings] = None


class BotCreate(BotBase):
    pass


class BotUpdate(BaseModel):
    token: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    about_text: Optional[str] = None
    avatar_url: Optional[str] = None
    project: Optional[str] = None
    environment: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    use_case: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    settings: Optional[BotSettings] = None


class BotResponse(BotBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
    commands: List[BotCommandResponse] = []
    history: List[BotHistoryEntry] = []


class BotListFilter(BaseModel):
    search: Optional[str] = None
    project: Optional[str] = None
    environment: Optional[str] = None
    status: Optional[str] = None
    tag: Optional[str] = None


# ============== Scan / Inventory Schemas ==============

class TokenOccurrenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: str
    source_label: str
    path: Optional[str] = None
    line: Optional[int] = None
    variable_name: Optional[str] = None
    container_name: Optional[str] = None
    risk: Optional[str] = None
    last_seen: datetime


class InventoryToken(BaseModel):
    token_fingerprint: str
    token: Optional[str] = None
    bot_id: str
    status: str
    registry_entry_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    project: Optional[str] = None
    occurrence_count: int = 0
    duplicate: bool = False
    risks: List[str] = []
    occurrences: List[TokenOccurrenceResponse] = []


class ScanRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    found_count: int
    registered_count: int
    unassigned_count: int
    warning: Optional[str] = None


class ScanInventory(BaseModel):
    latest_run: Optional[ScanRunResponse] = None
    totals: dict
    scan_roots: List[str] = []
    docker_scan_enabled: bool = False
    tokens: List[InventoryToken] = []


class ScanRequest(BaseModel):
    mode: str = "full"


class BotAssignRequest(BaseModel):
    token_fingerprint: str
    project: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    environment: Optional[str] = "development"
    notes: Optional[str] = None


class BotImportResponse(BaseModel):
    success: bool
    added: int
    skipped: int = 0
    deleted: int = 0
    errors: List[str] = []
