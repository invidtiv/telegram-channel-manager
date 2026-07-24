"""Token scanner ported from TGsecrets Node.js backend.

Scans configured filesystem roots and Docker containers for Telegram bot tokens,
compares them against the registered bot registry, and stores occurrences.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models import Bot, ScanRun, TokenOccurrence


TOKEN_REGEX = re.compile(r"[0-9]{8,10}:[A-Za-z0-9_-]{35}")
TOKEN_EXACT_REGEX = re.compile(r"^[0-9]{8,10}:[A-Za-z0-9_-]{35}$")

HOST_HOME = os.getenv("TGSECRETS_HOST_HOME", "/home/bsdev")
MOUNT_HOME = os.getenv("TGSECRETS_MOUNT_HOME", "/host/home/bsdev")
HOST_ETC = os.getenv("TGSECRETS_HOST_ETC", "/etc")
MOUNT_ETC = os.getenv("TGSECRETS_MOUNT_ETC", "/host/etc")

DEFAULT_SCAN_BASE = MOUNT_HOME if os.path.exists(MOUNT_HOME) else HOST_HOME

DEFAULT_SCAN_ROOTS = [
    f"{DEFAULT_SCAN_BASE}/BS",
    f"{DEFAULT_SCAN_BASE}/TS",
    f"{DEFAULT_SCAN_BASE}/projects",
    f"{DEFAULT_SCAN_BASE}/tigs",
    f"{DEFAULT_SCAN_BASE}/aichat",
    f"{DEFAULT_SCAN_BASE}/telegram-mcp-gateway",
    f"{DEFAULT_SCAN_BASE}/Bsclawdbot",
    f"{DEFAULT_SCAN_BASE}/.openclaw",
    f"{DEFAULT_SCAN_BASE}/.config/systemd/user",
    f"{(MOUNT_ETC if os.path.exists(MOUNT_ETC) else HOST_ETC)}/systemd",
    f"{(MOUNT_ETC if os.path.exists(MOUNT_ETC) else HOST_ETC)}/cron.d",
    f"{(MOUNT_ETC if os.path.exists(MOUNT_ETC) else HOST_ETC)}/crontab",
]

SCAN_ROOTS = [
    root.strip()
    for root in os.getenv("TGSECRETS_SCAN_ROOTS", ",".join(DEFAULT_SCAN_ROOTS)).split(",")
    if root.strip()
]

MAX_FILE_BYTES = int(os.getenv("TGSECRETS_SCAN_MAX_BYTES", 25 * 1024 * 1024))
ENABLE_DOCKER_SCAN = os.getenv("TGSECRETS_ENABLE_DOCKER_SCAN", "true").lower() != "false"

SKIPPED_DIR_NAMES = {
    ".cache", ".git", ".next", "backup", "backups", "build", "cache",
    "dist", "log", "logs", "node_modules", "tmp",
}

SKIPPED_PATH_FRAGMENTS = [
    "/.claude/", "/.codex/sessions/", "/.config/superpowers/", "/.gemini/",
    "/.github-forks-sync/", "/.openclaw/agents/", "/.openclaw/logs/",
    "/.openclaw/qmd_ingest/", "/.openclaw/sessions/", "/.openclaw/workspace/",
    "/.windsurf-server/", "/veritas-kanban/tasks/",
]

SKIPPED_EXTENSIONS = {
    ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".lock", ".mp3", ".mp4",
    ".pdf", ".png", ".svg", ".webm", ".zip",
}

RIPGREP_GLOBS = [
    "!**/node_modules/**", "!**/.git/**", "!**/dist/**", "!**/build/**",
    "!**/.next/**", "!**/.cache/**", "!**/cache/**", "!**/logs/**", "!**/log/**",
    "!**/backup/**", "!**/backups/**", "!**/tmp/**", "!**/archive/**",
    "!**/*.log", "!**/*.jsonl", "!**/*.md", "!**/package-lock.json",
    "!**/pnpm-lock.yaml", "!**/yarn.lock", "!**/*.png", "!**/*.jpg",
    "!**/*.jpeg", "!**/*.gif", "!**/*.svg", "!**/*.webm", "!**/*.mp4",
    "!**/*.pdf", "!**/*.zip", "!**/.claude/**", "!**/.codex/sessions/**",
    "!**/.config/superpowers/**", "!**/.gemini/**", "!**/.github-forks-sync/**",
    "!**/.openclaw/agents/**", "!**/.openclaw/logs/**", "!**/.openclaw/qmd_ingest/**",
    "!**/.openclaw/sessions/**", "!**/.openclaw/workspace/**", "!**/.windsurf-server/**",
    "!**/veritas-kanban/tasks/**", "!**/registry.sample.json", "!**/telegram_reference.json",
]


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _token_bot_id(token: str) -> str:
    return token.split(":", 1)[0]


def _to_display_path(path: str) -> str:
    if path.startswith(MOUNT_HOME):
        return f"{HOST_HOME}{path[len(MOUNT_HOME):]}"
    if path.startswith(MOUNT_ETC):
        return f"{HOST_ETC}{path[len(MOUNT_ETC):]}"
    return path


def _to_scan_path(display_path: str) -> str:
    if os.path.exists(MOUNT_HOME) and display_path.startswith(HOST_HOME):
        return f"{MOUNT_HOME}{display_path[len(HOST_HOME):]}"
    if os.path.exists(MOUNT_ETC) and display_path.startswith(HOST_ETC):
        return f"{MOUNT_ETC}{display_path[len(HOST_ETC):]}"
    return display_path


def _should_skip_path(path: str) -> bool:
    normalized = str(Path(path).as_posix())
    return any(fragment in normalized for fragment in SKIPPED_PATH_FRAGMENTS)


def _should_skip_file(path: str) -> bool:
    name = Path(path).name
    if name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "registry.sample.json", "telegram_reference.json"}:
        return True
    if Path(path).suffix.lower() == ".md":
        return True
    return Path(path).suffix.lower() in SKIPPED_EXTENSIONS


def _classify_risk(source: str) -> str:
    value = source.lower()
    risks = []
    if ".example" in value or "sample" in value:
        risks.append("example")
    if any(fragment in value for fragment in ["/backup", "/archive", "/tmp/", ".bak", ".backup", ".clobbered"]):
        risks.append("historical")
    if value.endswith(".db") or value.endswith(".sqlite"):
        risks.append("database")
    if "docker:" in value:
        risks.append("container-env")
    return ",".join(risks)


def _collect_files(root: str) -> List[str]:
    files = []
    stack = [root]
    while stack:
        current = stack.pop()
        if not current or _should_skip_path(current):
            continue
        try:
            p = Path(current)
            if not p.exists():
                continue
        except OSError:
            continue

        if p.is_file():
            try:
                if not _should_skip_file(str(p)) and p.stat().st_size <= MAX_FILE_BYTES:
                    files.append(str(p))
            except OSError:
                pass
            continue

        if not p.is_dir():
            continue

        try:
            entries = list(p.iterdir())
        except OSError:
            continue

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir() and entry.name in SKIPPED_DIR_NAMES:
                continue
            child = str(entry)
            if _should_skip_path(child):
                continue
            stack.append(child)
    return files


def _find_line(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def _scan_file(file_path: str) -> List[Dict[str, Any]]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return []

    display_path = _to_display_path(file_path)
    matches = []
    for match in TOKEN_REGEX.finditer(content):
        token = match.group(0)
        matches.append({
            "token": token,
            "token_fingerprint": _token_fingerprint(token),
            "bot_id": _token_bot_id(token),
            "source_type": "file",
            "source_label": f"{display_path}:{_find_line(content, match.start())}",
            "path": display_path,
            "line": _find_line(content, match.start()),
            "variable_name": "",
            "container_name": "",
            "risk": _classify_risk(display_path),
        })
    return matches


def _list_files_with_ripgrep(roots: List[str]) -> Optional[List[str]]:
    if not shutil.which("rg"):
        return None

    max_size = f"{max(1, MAX_FILE_BYTES // 1024 // 1024)}M"
    args = [
        "rg", "-l", "-a", "--hidden", "--max-filesize", max_size,
        *sum([["--glob", g] for g in RIPGREP_GLOBS], []),
        TOKEN_REGEX.pattern,
        *roots,
    ]
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if result.returncode == 1:
            return []
        return None
    except (subprocess.SubprocessError, OSError):
        return None


async def _scan_files(db: AsyncSession, mode: str) -> List[Dict[str, Any]]:
    files = []
    if mode == "recheck":
        result = await db.execute(
            select(TokenOccurrence.path)
            .where(TokenOccurrence.source_type == "file")
            .where(TokenOccurrence.path != "")
            .where(TokenOccurrence.path.isnot(None))
            .distinct()
        )
        files = [_to_scan_path(row[0]) for row in result.all()]
        if not files:
            mode = "full"

    if mode != "recheck":
        roots = [root for root in SCAN_ROOTS if os.path.exists(root)]
        rg_files = _list_files_with_ripgrep(roots)
        if rg_files is not None:
            files = rg_files
        else:
            nested = [_collect_files(root) for root in roots]
            files = [f for sub in nested for f in sub]

    occurrences = []
    for file_path in files:
        occurrences.extend(_scan_file(file_path))
    return occurrences


def _scan_docker() -> tuple:
    if not ENABLE_DOCKER_SCAN:
        return [], "Docker scan disabled"
    if not shutil.which("docker"):
        return [], "docker CLI not available"

    try:
        ps = subprocess.run(
            ["docker", "ps", "-aq"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return [], f"docker ps failed: {e}"

    if ps.returncode != 0:
        return [], (ps.stderr or ps.stdout or "docker ps failed").strip()

    container_ids = [c.strip() for c in ps.stdout.splitlines() if c.strip()]
    if not container_ids:
        return [], ""

    try:
        inspect = subprocess.run(
            ["docker", "inspect", *container_ids],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return [], f"docker inspect failed: {e}"

    if inspect.returncode != 0:
        return [], (inspect.stderr or inspect.stdout or "docker inspect failed").strip()

    try:
        data = json.loads(inspect.stdout)
    except json.JSONDecodeError:
        return [], "docker inspect returned invalid JSON"

    occurrences = []
    for container in data:
        container_name = container.get("Name", "")[1:] or str(container.get("Id", ""))[:12]
        for env in container.get("Config", {}).get("Env", []):
            for match in TOKEN_REGEX.finditer(env):
                token = match.group(0)
                variable_name = env.split("=", 1)[0] if "=" in env else "ENV"
                source_label = f"docker:{container_name}:env:{variable_name}"
                occurrences.append({
                    "token": token,
                    "token_fingerprint": _token_fingerprint(token),
                    "bot_id": _token_bot_id(token),
                    "source_type": "docker_env",
                    "source_label": source_label,
                    "path": "",
                    "line": None,
                    "variable_name": variable_name,
                    "container_name": container_name,
                    "risk": _classify_risk(source_label),
                })

        command_text = json.dumps({
            "Entrypoint": container.get("Config", {}).get("Entrypoint"),
            "Cmd": container.get("Config", {}).get("Cmd"),
        })
        for match in TOKEN_REGEX.finditer(command_text):
            token = match.group(0)
            source_label = f"docker:{container_name}:command"
            occurrences.append({
                "token": token,
                "token_fingerprint": _token_fingerprint(token),
                "bot_id": _token_bot_id(token),
                "source_type": "docker_command",
                "source_label": source_label,
                "path": "",
                "line": None,
                "variable_name": "",
                "container_name": container_name,
                "risk": _classify_risk(source_label),
            })

    return occurrences, ""


def _dedupe_occurrences(occurrences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for occ in occurrences:
        key = (
            occ["token_fingerprint"],
            occ["source_type"],
            occ["source_label"],
            occ.get("path", ""),
            occ.get("line") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(occ)
    return deduped


async def _insert_occurrences(db: AsyncSession, run_id: str, occurrences: List[Dict[str, Any]], seen_at: datetime):
    await db.execute(delete(TokenOccurrence))
    for occ in occurrences:
        db.add(TokenOccurrence(
            run_id=run_id,
            token=occ["token"],
            token_fingerprint=occ["token_fingerprint"],
            bot_id=occ["bot_id"],
            source_type=occ["source_type"],
            source_label=occ["source_label"],
            path=occ.get("path", "") or "",
            line=occ.get("line"),
            variable_name=occ.get("variable_name", "") or "",
            container_name=occ.get("container_name", "") or "",
            risk=occ.get("risk", "") or "",
            last_seen=seen_at,
        ))


async def build_inventory(db: AsyncSession) -> Dict[str, Any]:
    bots_result = await db.execute(select(Bot))
    bots = bots_result.scalars().all()

    registry_by_fingerprint = {}
    for bot in bots:
        if TOKEN_EXACT_REGEX.match(bot.token):
            registry_by_fingerprint[_token_fingerprint(bot.token)] = bot

    occurrences_result = await db.execute(
        select(TokenOccurrence).order_by(TokenOccurrence.token_fingerprint, TokenOccurrence.source_label)
    )
    occurrence_rows = occurrences_result.scalars().all()

    groups: Dict[str, Dict[str, Any]] = {}
    for row in occurrence_rows:
        if row.token_fingerprint not in groups:
            groups[row.token_fingerprint] = {
                "token_fingerprint": row.token_fingerprint,
                "token": row.token,
                "bot_id": row.bot_id,
                "occurrences": [],
                "risks": set(),
            }
        group = groups[row.token_fingerprint]
        group["occurrences"].append({
            "source_type": row.source_type,
            "source_label": row.source_label,
            "path": row.path or "",
            "line": row.line,
            "variable_name": row.variable_name or "",
            "container_name": row.container_name or "",
            "risk": row.risk or "",
            "last_seen": row.last_seen.isoformat(),
        })
        for risk in (row.risk or "").split(","):
            if risk.strip():
                group["risks"].add(risk.strip())

    tokens = []
    for group in groups.values():
        registered_bot = registry_by_fingerprint.get(group["token_fingerprint"])
        tokens.append({
            "token_fingerprint": group["token_fingerprint"],
            "token": group["token"],
            "bot_id": group["bot_id"],
            "status": "registered_found" if registered_bot else "unassigned_found",
            "registry_entry_id": registered_bot.id if registered_bot else "",
            "username": registered_bot.username if registered_bot else "",
            "display_name": registered_bot.display_name if registered_bot else "",
            "project": registered_bot.project if registered_bot else "",
            "occurrence_count": len(group["occurrences"]),
            "duplicate": len(group["occurrences"]) > 1,
            "risks": sorted(group["risks"]),
            "occurrences": group["occurrences"],
        })

    for bot in bots:
        if not TOKEN_EXACT_REGEX.match(bot.token):
            continue
        fingerprint = _token_fingerprint(bot.token)
        if fingerprint not in groups:
            tokens.append({
                "token_fingerprint": fingerprint,
                "bot_id": _token_bot_id(bot.token),
                "status": "registered_missing",
                "registry_entry_id": bot.id,
                "username": bot.username,
                "display_name": bot.display_name,
                "project": bot.project,
                "occurrence_count": 0,
                "duplicate": False,
                "risks": [],
                "occurrences": [],
            })

    tokens.sort(key=lambda t: (t["status"], t["bot_id"], t["token_fingerprint"]))

    latest_run_result = await db.execute(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()

    latest_run_data = None
    if latest_run:
        latest_run_data = {
            "id": latest_run.id,
            "mode": latest_run.mode,
            "started_at": latest_run.started_at.isoformat(),
            "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
            "status": latest_run.status,
            "found_count": latest_run.found_count,
            "registered_count": latest_run.registered_count,
            "unassigned_count": latest_run.unassigned_count,
            "warning": latest_run.warning,
        }

    return {
        "latest_run": latest_run_data,
        "totals": {
            "registered_bots": len(bots),
            "found_tokens": len([t for t in tokens if t["status"] != "registered_missing"]),
            "registered_found": len([t for t in tokens if t["status"] == "registered_found"]),
            "unassigned_found": len([t for t in tokens if t["status"] == "unassigned_found"]),
            "registered_missing": len([t for t in tokens if t["status"] == "registered_missing"]),
            "duplicate_tokens": len([t for t in tokens if t["duplicate"]]),
            "risky_tokens": len([t for t in tokens if t["risks"]]),
        },
        "scan_roots": [_to_display_path(r) for r in SCAN_ROOTS],
        "docker_scan_enabled": ENABLE_DOCKER_SCAN,
        "tokens": tokens,
    }


_scan_lock = False


async def run_scan(db: AsyncSession, requested_mode: str = "full") -> Dict[str, Any]:
    global _scan_lock
    if _scan_lock:
        raise RuntimeError("Scan already in progress")

    _scan_lock = True
    mode = "recheck" if requested_mode == "recheck" else "full"
    run_id = os.urandom(16).hex()
    started_at = datetime.utcnow()
    run = ScanRun(
        id=run_id,
        mode=mode,
        started_at=started_at,
        status="running",
    )
    db.add(run)
    await db.commit()

    try:
        file_occurrences = await _scan_files(db, mode)
        docker_occurrences, warning = _scan_docker()
        occurrences = _dedupe_occurrences(file_occurrences + docker_occurrences)
        finished_at = datetime.utcnow()
        await _insert_occurrences(db, run_id, occurrences, finished_at)

        inventory = await build_inventory(db)
        run.finished_at = finished_at
        run.found_count = inventory["totals"]["found_tokens"]
        run.registered_count = inventory["totals"]["registered_found"]
        run.unassigned_count = inventory["totals"]["unassigned_found"]
        run.warning = warning or ""
        run.status = "completed_with_warnings" if warning else "completed"
        await db.commit()
        return inventory
    except Exception as e:
        run.finished_at = datetime.utcnow()
        run.status = "failed"
        run.warning = str(e)
        await db.commit()
        raise
    finally:
        _scan_lock = False


async def resync_inventory(db: AsyncSession) -> Dict[str, Any]:
    """Rebuild inventory without running a new scan."""
    return await build_inventory(db)
