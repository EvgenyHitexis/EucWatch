"""Versioned configuration backup review, without wheel/session state.

Only schema 1 exists in this application. Compatible application updates retain
that schema's meaning and fixed identities; no undocumented historical format
is guessed or silently reset. Additional schemas require an explicit migration.
"""

import json
from copy import deepcopy
from typing import Any

from .configuration import VERSION, validate_configuration
from .persistence import MAX_CONFIG_BYTES


def export(config: dict[str, Any]) -> dict[str, Any]:
    return validate_configuration(config)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration field: {key}")
        result[key] = value
    return result


def migrate(content: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Known-schema normalization preserves every field's existing meaning."""
    if (
        not isinstance(content, dict)
        or type(content.get("version")) is not int
        or content["version"] != VERSION
    ):
        raise ValueError("Unsupported configuration version; owner review required")
    return validate_configuration(content), {
        "from": VERSION,
        "to": VERSION,
        "changes": [],
    }


def prepare(content: Any, base_revision: int) -> dict[str, Any]:
    if not isinstance(content, str):
        raise TypeError("Configuration import must contain JSON text")
    try:
        encoded = content.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Configuration import must contain valid UTF-8") from exc
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("Configuration exceeds the supported size (32 KiB)")
    try:
        parsed = json.loads(content, object_pairs_hook=_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid configuration JSON: {exc}") from exc
    normalized, migration = migrate(parsed)
    return {
        "content": normalized,
        "base_revision": base_revision,
        "migration": migration,
    }


def replacement(preview: dict[str, Any], current_revision: int) -> dict[str, Any]:
    if preview["base_revision"] != current_revision:
        raise ValueError(
            "Saved configuration changed after preview; review the import again"
        )
    proposed = deepcopy(preview["content"])
    proposed["revision"] = current_revision + 1
    return validate_configuration(proposed)
