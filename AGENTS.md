# AGENTS.md - Agent Workflow Guide

## Kanban Integration (MANDATORY)

All work MUST be tracked on the Veritas Kanban board.

### Board Access
- **URL**: http://vmi2916953.tail652dda.ts.net:3001
- **API**: http://vmi2916953.tail652dda.ts.net:3001/api/v1
- **API Key**: Store in `~/.config/veritas-kanban/api_key`

### Before Starting
1. Create a task:
   ```bash
   curl -X POST http://vmi2916953.tail652dda.ts.net:3001/api/v1/tasks \
     -H "X-API-Key: $KANBAN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"title": "Task title", "description": "Details", "projectId": "PROJECT_NAME", "status": "todo"}'
   ```

2. Move to "in-progress":
   ```bash
   PATCH /api/v1/tasks/{id} {"status": "in-progress"}
   ```

3. Start timer:
   ```bash
   POST /api/v1/tasks/{id}/time/start
   ```

### During Work
- Add progress comments via API
- Update task description if scope changes

### After Commit/Push
1. Stop timer: `POST /api/v1/tasks/{id}/time/stop`
2. Add final comment with commit hash
3. Mark done:
   ```bash
   PATCH /api/v1/tasks/{id} {
     "status": "done",
     "completionSummary": "What was done",
     "lessonsLearned": "Key insights"
   }
   ```


## Project: Personal Telegram
