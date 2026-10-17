from pathlib import Path
import re

RESERVED_CHARS = re.compile(r'[<>:"/\\|?*]')
CONTROL_CHARS = re.compile(r"[\x00-\x1f]")
WHITESPACE = re.compile(r"\s+")
RESERVED_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"COM{suffix}" for suffix in ("\u00b9", "\u00b2", "\u00b3")),
    *(f"LPT{number}" for number in range(1, 10)),
    *(f"LPT{suffix}" for suffix in ("\u00b9", "\u00b2", "\u00b3")),
}


def sanitize_filename(value: str, fallback: str = "track") -> str:
    cleaned = RESERVED_CHARS.sub("_", value)
    cleaned = CONTROL_CHARS.sub("_", cleaned)
    cleaned = WHITESPACE.sub(" ", cleaned).strip(" .")
    base, separator, remainder = cleaned.partition(".")
    if base.upper() in RESERVED_DEVICE_NAMES:
        cleaned = f"{base}_{separator}{remainder}"
    return cleaned or fallback


def resolve_mp3_path(output_dir: Path, title: str, artist: str | None = None) -> Path:
    safe_title = sanitize_filename(title)
    safe_artist = sanitize_filename(artist, fallback="") if artist else ""
    stem = f"{safe_artist} - {safe_title}" if safe_artist else safe_title
    candidate = output_dir / f"{stem}.mp3"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{stem} ({suffix}).mp3"
        suffix += 1
    return candidate
