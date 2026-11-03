import os

import requests

# Telegram rejects sendMessage payloads above 4096 characters with HTTP 400.
# The paper-trading report can exceed that, so it is split on line boundaries.
MAX_MESSAGE_LENGTH = 4000


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list:
    """Split text into Telegram-safe chunks without cutting lines in half."""
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return [text]

    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            # A single pathological line still has to be hard-split.
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current or not chunks:
        chunks.append(current)
    return chunks


def _post_chunk(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return True


def send_message(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM NOT CONFIGURED")
        return False

    try:
        for chunk in split_message(text):
            _post_chunk(token, chat_id, chunk)
        return True
    except Exception as exc:
        print(f"TELEGRAM ERROR | {exc}")
        return False
