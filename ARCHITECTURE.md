# 🏗️ Architecture Documentation

## System Overview

Telegram Channel Manager is a full-stack web application that helps users organize their Telegram channels through an intelligent tagging system with a modern dark-themed interface.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         React Frontend (Port 3000)                    │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │   │
│  │  │ Channel  │  │   Tag    │  │  Ingestion   │       │   │
│  │  │   List   │  │ Manager  │  │    Panel     │       │   │
│  │  └──────────┘  └──────────┘  └──────────────┘       │   │
│  │                                                        │   │
│  │  Features:                                            │   │
│  │  • Single-click tagging                               │   │
│  │  • Real-time search & filtering                       │   │
│  │  • Dark mode (OLED optimized)                         │   │
│  │  • Optimistic UI updates                              │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP/REST API
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                    BACKEND SERVICES                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │       FastAPI Application (Port 8000)                 │   │
│  │                                                        │   │
│  │  Endpoints:                                           │   │
│  │  • /api/channels  - Channel CRUD & filtering          │   │
│  │  • /api/tags      - Tag management                    │   │
│  │  • /api/ingestion - MTProto sync                      │   │
│  │                                                        │   │
│  │  Components:                                          │   │
│  │  ┌────────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │  Database  │  │ Telethon │  │  Models  │        │   │
│  │  │   Layer    │  │  Client  │  │ Schemas  │        │   │
│  │  └────────────┘  └──────────┘  └──────────┘        │   │
│  └────────────┬─────────────┬────────────────────────────┘   │
└───────────────┼─────────────┼──────────────────────────────┘
                │             │
                │             └──────────────┐
                ▼                            ▼
┌───────────────────────────┐  ┌────────────────────────────┐
│   DATA PERSISTENCE        │  │   EXTERNAL API             │
│                           │  │                            │
│  ┌─────────────────────┐  │  │  ┌──────────────────────┐ │
│  │   SQLite Database   │  │  │  │  Telegram MTProto    │ │
│  │                     │  │  │  │    (Telethon)        │ │
│  │  Tables:            │  │  │  │                      │ │
│  │  • channels         │  │  │  │  Operations:         │ │
│  │  • tags             │  │  │  │  • Fetch dialogs     │ │
│  │  • channel_tags     │  │  │  │  • Get chat info     │ │
│  │    (junction)       │  │  │  │  • Handle sessions   │ │
│  └─────────────────────┘  │  │  └──────────────────────┘ │
└───────────────────────────┘  └────────────────────────────┘
```

## Component Breakdown

### 1. Frontend Layer (React)

**Technology Stack:**
- React 18.2 with Hooks
- Vite (build tool & dev server)
- Native Fetch API (HTTP client)
- CSS Variables (theming)

**Components:**

#### `App.jsx`
- Main application shell
- Tab navigation (Channels, Tags, Ingestion)
- Global state management for tags
- Theme provider

#### `ChannelList.jsx`
- Displays paginated channel list
- Single-click inline tag toggling (v2.0)
- Real-time search filtering
- Tag-based filtering
- Direct Telegram links for public channels
- Optimistic UI updates

#### `TagManager.jsx`
- Tag CRUD operations
- Color picker (12 presets)
- Tag listing with statistics

#### `IngestionPanel.jsx`
- MTProto sync control
- Progress tracking
- Status indicators

**State Management:**
- React useState/useEffect hooks
- Local component state
- No external state management library

**Styling:**
- CSS-in-JS (inline styles for dynamic colors)
- CSS modules (App.css)
- Dark mode theme with CSS variables
- OLED-optimized color palette

### 2. Backend Layer (FastAPI)

**Technology Stack:**
- FastAPI (async web framework)
- Uvicorn (ASGI server)
- SQLAlchemy (ORM)
- Pydantic (data validation)
- Telethon (Telegram client)

**API Structure:**

```python
app/
├── main.py              # FastAPI app, routes, CORS
├── database.py          # SQLAlchemy setup, async session
├── models.py            # ORM models (Channel, Tag, ChannelTag)
├── schemas.py           # Pydantic schemas for validation
└── telethon_client.py   # Telegram MTProto client wrapper
```

**Key Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/channels` | List channels with optional filters |
| POST | `/api/channels/{id}/tags/{tag_id}` | Add tag to channel |
| DELETE | `/api/channels/{id}/tags/{tag_id}` | Remove tag from channel |
| GET | `/api/tags` | List all tags |
| POST | `/api/tags` | Create new tag |
| PUT | `/api/tags/{id}` | Update tag |
| DELETE | `/api/tags/{id}` | Delete tag |
| POST | `/api/ingestion/start` | Start MTProto sync |
| GET | `/api/ingestion/status` | Get sync status |

**Middleware:**
- CORS (configured for localhost development)
- Exception handlers
- Request logging

### 3. Data Layer (SQLite + SQLAlchemy)

**Database Schema:**

```sql
-- Channels table
CREATE TABLE channels (
    id INTEGER PRIMARY KEY,           -- Telegram channel ID
    bot_chat_id VARCHAR NOT NULL,     -- Formatted for bot API
    name VARCHAR NOT NULL,
    username VARCHAR,                 -- Public @username (nullable)
    type VARCHAR NOT NULL,            -- channel/group/supergroup
    participants_count INTEGER,
    is_verified BOOLEAN DEFAULT FALSE,
    is_megagroup BOOLEAN DEFAULT FALSE,
    about TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- Tags table
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR UNIQUE NOT NULL,
    color VARCHAR NOT NULL,          -- Hex color code
    created_at DATETIME NOT NULL
);

-- Many-to-many junction table
CREATE TABLE channel_tags (
    channel_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (channel_id, tag_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
```

**ORM Relationships:**
- Channel has many Tags (through `channel_tags`)
- Tag has many Channels (through `channel_tags`)

**Indexes:**
- Primary keys on all tables
- Foreign key indexes for joins
- Unique index on `tags.name`

### 4. External Integration Layer (Telegram)

**Telethon Client:**

```python
class TelegramClient:
    def __init__(self, api_id, api_hash, phone):
        self.client = TelegramClient('session', api_id, api_hash)

    async def fetch_channels(self):
        # Get all dialogs (chats)
        dialogs = await self.client.get_dialogs()

        # Filter for channels/groups
        channels = [d for d in dialogs
                   if isinstance(d.entity, (Channel, Chat))]

        return channels

    async def get_full_channel(self, entity):
        # Get detailed channel information
        full = await self.client(GetFullChannelRequest(entity))
        return full
```

**Rate Limiting:**
- Automatic backoff on Telegram rate limits
- Exponential retry strategy
- Progress tracking for long operations

**Session Management:**
- Persistent `.session` file
- Encrypted session storage
- Automatic reauth on expiry

## Data Flow

### 1. Channel Ingestion Flow

```
User clicks "Start Ingestion"
    │
    ▼
Frontend sends POST /api/ingestion/start
    │
    ▼
Backend initializes Telethon client
    │
    ▼
Authenticate with Telegram (if needed)
    │
    ▼
Fetch all dialogs via MTProto
    │
    ▼
Filter for channels/groups
    │
    ▼
For each channel:
    ├─ Get full channel info
    ├─ Format bot_chat_id
    ├─ Extract metadata
    └─ Upsert to database
    │
    ▼
Return status to frontend
    │
    ▼
Frontend displays updated channel list
```

### 2. Single-Click Tag Toggle Flow (v2.0)

```
User clicks tag button on channel
    │
    ▼
Frontend immediately updates UI (optimistic)
    │
    ├─ Add: Fill background with tag color
    └─ Remove: Clear background, show border only
    │
    ▼
Send POST/DELETE to /api/channels/{id}/tags/{tag_id}
    │
    ▼
Backend updates database
    │
    ├─ Success: Keep optimistic update
    └─ Failure: Revert UI change
    │
    ▼
User sees instant feedback (<16ms)
```

### 3. Filtering Flow

```
User types in search box OR clicks tag filter
    │
    ▼
Frontend triggers useEffect with search/tags
    │
    ▼
Construct query: /api/channels?search=X&tag_ids=1,2
    │
    ▼
Backend filters channels with SQLAlchemy
    │
    ├─ Text search: LIKE '%search%' on name
    └─ Tag filter: JOIN with channel_tags
    │
    ▼
Return filtered results
    │
    ▼
Frontend updates channel list in real-time
```

## Security Architecture

### 1. Authentication Layer
- **Telegram Session**: Encrypted `.session` file
- **API Keys**: Stored in `.env` (never committed)
- **CORS**: Configured for specific origins

### 2. Data Protection
- **SQL Injection**: Prevented via SQLAlchemy ORM
- **XSS**: Mitigated by React's automatic escaping
- **CSRF**: N/A (no cookie-based auth)

### 3. Secure Communication
- **External Links**: `rel="noopener noreferrer"` attribute
- **HTTPS**: Recommended for production deployment

## Performance Optimizations

### Frontend

1. **Optimistic UI Updates**
   - Instant feedback without waiting for server
   - Rollback on failure

2. **React Performance**
   - Functional components with hooks
   - Minimal re-renders via `useEffect` dependencies
   - No unnecessary state updates

3. **CSS Performance**
   - CSS variables for theming (no runtime JS)
   - Hardware-accelerated transitions (`transform`, `opacity`)
   - Efficient selectors

### Backend

1. **Async/Await**
   - Non-blocking I/O with FastAPI
   - Concurrent request handling

2. **Database Optimization**
   - Indexed foreign keys
   - Eager loading for relationships (`selectinload`)
   - Connection pooling

3. **Caching Strategy**
   - Potential for Redis cache (future)
   - In-memory tag list cache

## Scalability Considerations

### Current Limitations (SQLite)

- **Concurrent Writes**: Limited (single writer)
- **Max Connections**: ~1000 concurrent readers
- **Database Size**: Recommended < 1GB

### Migration Path for Production

```
SQLite (Development)
    │
    ▼
PostgreSQL (Production)
    │
    ├─ Connection pooling
    ├─ MVCC for concurrency
    └─ Better scalability

Optional Additions:
    ├─ Redis for caching
    ├─ Celery for background tasks
    └─ Load balancer for multiple backend instances
```

## Deployment Architecture

### Development

```
┌─────────────┐     ┌──────────────┐
│   Vite      │     │   Uvicorn    │
│  (Port 3000)│────▶│  (Port 8000) │
└─────────────┘     └──────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │    SQLite    │
                    │    (File)    │
                    └──────────────┘
```

### Production (Recommended)

```
                    ┌──────────────┐
                    │    Nginx     │
                    │  (Port 80/   │
                    │   443)       │
                    └───────┬──────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        ┌───────▼──────┐      ┌────────▼─────┐
        │  Static      │      │   FastAPI    │
        │  Files       │      │   (Gunicorn) │
        │  (React)     │      │  (Multiple   │
        │              │      │   workers)   │
        └──────────────┘      └───────┬──────┘
                                      │
                              ┌───────▼──────┐
                              │  PostgreSQL  │
                              │   (Docker)   │
                              └──────────────┘
```

## Monitoring & Logging

### Current Implementation

- Console logging in backend
- Browser DevTools in frontend
- FastAPI automatic error responses

### Production Recommendations

1. **Application Monitoring**
   - Sentry for error tracking
   - New Relic / DataDog for APM

2. **Logging**
   - Structured JSON logs
   - Log aggregation (ELK stack)
   - Log rotation

3. **Metrics**
   - Prometheus for metrics collection
   - Grafana for visualization
   - Custom dashboards for:
     - Request latency
     - Tag operation frequency
     - Ingestion performance

## Future Architecture Improvements

### v2.1
- [ ] **Redis Cache**: Tag list caching
- [ ] **WebSockets**: Real-time ingestion progress
- [ ] **Background Tasks**: Async ingestion with Celery

### v3.0
- [ ] **PostgreSQL**: Migration from SQLite
- [ ] **Microservices**: Separate ingestion service
- [ ] **API Gateway**: Centralized routing
- [ ] **GraphQL**: Alternative to REST API
- [ ] **Docker Compose**: Complete stack deployment

---

**Document Version**: 2.0.0
**Last Updated**: 2026-03-03
**Author**: Generated with Claude Code
