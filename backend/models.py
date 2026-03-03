"""SQLAlchemy models for database."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, Text
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
