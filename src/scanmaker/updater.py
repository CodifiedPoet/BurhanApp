"""Background update checker using GitHub Releases API."""

import json
import urllib.request
import urllib.error
from threading import Thread

from scanmaker import __version__

_REPO = "CodifiedPoet/BurhanApp"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_TIMEOUT = 5  # seconds


def _parse_version(tag: str) -> tuple[int, ...]:
    """Convert 'v2.0.0' or '2.0.0' to (2, 0, 0)."""
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def check_for_update(callback):
    """Check GitHub for a newer release in a background thread.

    *callback(tag, url)* is called on the thread if an update is found.
    Pass None, None if no update or on error.
    """

    def _worker():
        try:
            req = urllib.request.Request(
                _API_URL,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "BurhanApp-UpdateCheck"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            tag = data.get("tag_name", "")
            remote = _parse_version(tag)
            local = _parse_version(__version__)
            if remote > local:
                html_url = data.get("html_url", "")
                callback(tag, html_url)
            else:
                callback(None, None)
        except Exception:
            callback(None, None)

    t = Thread(target=_worker, daemon=True)
    t.start()
