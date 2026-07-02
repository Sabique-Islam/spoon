import re
from html import unescape

from app.config import get_settings


def truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def html_to_text(html: str) -> str:
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return unescape(re.sub(r"\s+", " ", text)).strip()
