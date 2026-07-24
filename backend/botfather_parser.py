"""Parser for Telegram Desktop BotFather chat history export."""

import re
import uuid
from datetime import datetime

TOKEN_REGEX = re.compile(r"\d{6,10}:[A-Za-z0-9_-]{35}")
USERNAME_REGEX = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{5,32})")


def _message_text_to_str(text):
    """Convert Telegram export message text (string or mixed array) to plain string."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return ""


def _extract_username_from_text_or_entities(text, entities):
    """Extract a Telegram username from plain text or entity objects."""
    username_match = USERNAME_REGEX.search(text)
    if username_match:
        return username_match.group(1)

    mention_match = re.search(r"@([A-Za-z0-9_]{5,32})", text)
    if mention_match:
        return mention_match.group(1)

    for entity in entities or []:
        if isinstance(entity, dict):
            if entity.get("type") in ("link", "text_link"):
                link_text = entity.get("text", "")
                m = USERNAME_REGEX.search(link_text)
                if m:
                    return m.group(1)
            if entity.get("type") == "mention":
                mention_text = entity.get("text", "")
                m = re.match(r"@([A-Za-z0-9_]{5,32})", mention_text)
                if m:
                    return m.group(1)
    return ""


def parse_botfather_history(data, project="botfather"):
    """Return created bots and deleted usernames from BotFather chat history.

    Returns a dict with:
      - bots: list of bot dicts compatible with import_bots
      - deleted_usernames: list of usernames that were deleted via /deletebot
    """
    messages = data.get("messages", []) if isinstance(data, dict) else []
    bots = []
    deleted_usernames = []
    seen_tokens = set()

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("from") != "BotFather":
            continue

        text = _message_text_to_str(message.get("text", ""))
        entities = message.get("text_entities", [])

        # Delete event: "You have deleted <name> @username"
        if "You have deleted" in text:
            username = _extract_username_from_text_or_entities(text, entities)
            if username and username not in deleted_usernames:
                deleted_usernames.append(username)
            continue

        # Creation / token refresh event
        if "HTTP API" not in text and "token" not in text.lower():
            continue

        token_match = TOKEN_REGEX.search(text)
        if not token_match:
            continue
        token = token_match.group(0)
        if token in seen_tokens:
            continue

        username = _extract_username_from_text_or_entities(text, entities)
        if not username:
            username = f"bot{token.split(':')[0]}"

        seen_tokens.add(token)
        date_str = message.get("date")
        parsed_date = None
        if date_str:
            try:
                parsed_date = datetime.fromisoformat(date_str)
            except ValueError:
                parsed_date = None

        bots.append({
            "id": str(uuid.uuid4()),
            "token": token,
            "username": username,
            "displayName": username,
            "description": "",
            "aboutText": "",
            "avatarUrl": "",
            "project": project,
            "environment": "production",
            "status": "active",
            "tags": ["botfather"],
            "useCase": "",
            "location": "",
            "notes": f"Imported from BotFather chat history on {date_str or 'unknown'}",
            "settings": {
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
            "createdAt": parsed_date,
            "updatedAt": parsed_date,
        })

    return {"bots": bots, "deleted_usernames": deleted_usernames}
