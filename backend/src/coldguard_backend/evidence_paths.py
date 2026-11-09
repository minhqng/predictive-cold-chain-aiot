"""Pure portable filename checks; reject aliases without opening any device/path."""

import re

_RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"}


def portable_component(name: str) -> str:
    """Validate, never trim/rename, a single evidence path component."""
    if (not isinstance(name, str) or name in {"", ".", ".."} or name.endswith((".", " "))
        or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in name)):
        raise ValueError("evidence filename must be a portable, non-alias component")
    stem = name.partition(".")[0].rstrip(" ").upper()
    if stem in _RESERVED or re.fullmatch(r"(?:COM|LPT)[1-9\u00b9\u00b2\u00b3]", stem):
        raise ValueError("reserved device filename is not a portable evidence component")
    return name
