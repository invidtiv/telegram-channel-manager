"""SQLAlchemy models for database."""

from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Table, Text, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


# Association table for many-to-many relationship between channels and tags
channel_tags = Table(
    'channel_tags',
    Base.metadata,
    Column('channel_id', Integer, ForeignKey('channels.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)


class Channel(Base):
    """Telegram channel/group model."""
    __tablename__ = 'channels'
    
    id = Column(Integer, primary_key=True)
    bot_chat_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    username = Column(String, nullable=True)
    type = Column(String, nullable=False)  # 'channel', 'group', 'supergroup'
    participants_count = Column(Integer, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_megagroup = Column(Boolean, default=False)
    about = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tags = relationship("Tag", secondary=channel_tags, back_populates="channels")


class Tag(Base):
    """Tag model for categorizing channels."""
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    color = Column(String, default="#3B82F6")  # Hex color for UI
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    channels = relationship("Channel", secondary=channel_tags, back_populates="tags")


class GroupMember(Base):
    """Telegram group/channel member model."""
    __tablename__ = 'group_members'
    __table_args__ = (
        UniqueConstraint('channel_id', 'user_id', name='uq_channel_user'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, ForeignKey('channels.id'), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_bot = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    status = Column(String, nullable=True)  # online, offline, recently, last_week, last_month, long_time_ago
    fetched_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    channel = relationship("Channel", backref="members")


class Bot(Base):
    """Telegram bot registry entry."""
    __tablename__ = 'bots'

    id = Column(String, primary_key=True)
    token = Column(String, nullable=False)
    username = Column(String, nullable=False)
    display_name = Column(String, default="")
    description = Column(String, default="")
    about_text = Column(String, default="")
    avatar_url = Column(String, default="")
    project = Column(String, default="")
    environment = Column(String, default="development")
    status = Column(String, default="active")
    tags = Column(JSON, default=list)
    use_case = Column(String, default="")
    location = Column(String, default="")
    notes = Column(Text, default="")
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    commands = relationship("BotCommand", back_populates="bot", cascade="all, delete-orphan")
    history = relationship("BotHistory", back_populates="bot", cascade="all, delete-orphan")


class BotCommand(Base):
    """Registered command for a bot."""
    __tablename__ = 'bot_commands'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(String, ForeignKey('bots.id'), nullable=False, index=True)
    command = Column(String, nullable=False)
    description = Column(String, nullable=False)
    scope = Column(String, default="default")
    language_code = Column(String, nullable=True)

    # Relationships
    bot = relationship("Bot", back_populates="commands")


class BotHistory(Base):
    """Append-only history of bot registry changes."""
    __tablename__ = 'bot_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(String, ForeignKey('bots.id'), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    action = Column(String, nullable=False)
    field = Column(String, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    note = Column(String, nullable=True)

    # Relationships
    bot = relationship("Bot", back_populates="history")


class ScanRun(Base):
    """Token scan run metadata."""
    __tablename__ = 'scan_runs'

    id = Column(String, primary_key=True)
    mode = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)
    found_count = Column(Integer, default=0)
    registered_count = Column(Integer, default=0)
    unassigned_count = Column(Integer, default=0)
    warning = Column(String, nullable=True)


class TokenOccurrence(Base):
    """Discovered token occurrence from a scan."""
    __tablename__ = 'token_occurrences'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey('scan_runs.id'), nullable=False, index=True)
    token = Column(String, nullable=False)
    token_fingerprint = Column(String, nullable=False, index=True)
    bot_id = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False)
    source_label = Column(String, nullable=False)
    path = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    variable_name = Column(String, default="")
    container_name = Column(String, default="")
    risk = Column(String, default="")
    last_seen = Column(DateTime, nullable=False)
