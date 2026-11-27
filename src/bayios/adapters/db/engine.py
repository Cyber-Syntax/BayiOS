from __future__ import annotations

# Store and read timestamps in UTC; presentation converts to Europe/Istanbul.
UTC_CONNECT_ARGS: dict[str, str] = {"options": "-c timezone=UTC"}
