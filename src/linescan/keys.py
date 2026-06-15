"""Tiny helper to poll for the operator's 'q' (quit) key.

The original used the ``keyboard`` package, which needs elevated privileges on
some platforms. It is imported lazily once and treated as optional: if it is
unavailable, quit-by-key simply never fires and tools stop via their normal
exit paths instead.
"""

from __future__ import annotations

from typing import Any

_keyboard: Any = None
_loaded = False


def quit_pressed() -> bool:
    """Return ``True`` while the operator is holding the 'q' key."""
    global _keyboard, _loaded
    if not _loaded:
        _loaded = True
        try:
            import keyboard

            _keyboard = keyboard
        except Exception:  # pragma: no cover - optional dependency / privileges
            _keyboard = None
    return bool(_keyboard is not None and _keyboard.is_pressed("q"))
