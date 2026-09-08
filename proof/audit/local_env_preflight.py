"""Inspect a deliberately selected dotenv file without loading or using secrets.

This is NOT a credentials validator or a deployment gate. It has no network
client, imports no app modules, changes no environment, and reports only fixed
field names/statuses. In particular it never adopts ANTICIPY_OWNER_ID as a test
account. Keep team credentials outside the checkout: legacy overnight gates
automatically load .env.local and some operate on live accounts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


# File-format recognition, not a classifier of human language.
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
FIELDS = (
    "ANTICIPY_PB", "ANTICIPY_BACKEND_URL", "ANTICIPY_SERVICE_TOKEN",
    "ANTICIPY_INTERNAL_KEY", "ANTICIPY_OWNER_ID", "TWO_HANDS_OWNER",
    "OPENROUTER_API_KEY", "GEMINI_API_KEY", "DEEPGRAM_API_KEY",
    "BRAVE_API_KEY", "CAPSOLVER_API_KEY", "COMPOSIO_API_KEY",
    "SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY", "SENDBLUE_FROM_NUMBER",
    "SENDBLUE_WEBHOOK_SECRET", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
    "ANTICIPY_AUTH_SECRET", "ANTICIPY_VAULT_KEY",
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
    "ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8",
    "APP_STORE_CONNECT_KEY_ID", "APP_STORE_CONNECT_ISSUER_ID",
)


def parse(text: str) -> tuple[dict[str, str], set[str], list[int]]:
    """Parse simple dotenv syntax as DATA; never source/expand/evaluate it.

    Multiline values/interpolation are deliberately unsupported. Ambiguous or
    duplicate assignments cannot qualify a field as configured. No diagnostic
    includes input text, arbitrary variable names, or exception messages.
    """
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    invalid: list[int] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not NAME.fullmatch(name):
            invalid.append(number)
            continue
        if name in values:
            duplicates.add(name)
        # Permit whole-value quotes and trailing comments. Find an unescaped
        # closing quote; reject shell concatenation rather than interpreting it.
        if value.startswith(("'", '"')):
            quote = value[0]
            escaped = False
            end = None
            for index, char in enumerate(value[1:], 1):
                if char == quote and not escaped:
                    end = index
                    break
                escaped = char == "\\" and not escaped
            tail = value[end + 1:].strip() if end is not None else ""
            if end is None or (tail and not tail.startswith("#")):
                invalid.append(number)
                values[name] = ""
                continue
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if re.search(r"\$(?:[({]|[A-Za-z_])|`", value):
            invalid.append(number)
            values[name] = ""
            continue
        values[name] = value
    return values, duplicates, invalid


def endpoint_kind(value: str) -> str:
    if not value:
        return "missing"
    try:
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return "unapproved_url_shape"
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return "invalid_url"
        # urlsplit defers malformed/out-of-range port validation until access.
        port = parsed.port
        if port == 0:
            return "invalid_url"
        if parsed.path not in ("", "/"):
            return "unapproved_url_shape"
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return "local_only"
        if value.rstrip("/") == "https://api.anticipy.ai":
            return "current_cloudflare_api_LIVE"
        return "other_origin_REVIEW_REQUIRED"
    except ValueError:
        return "invalid_url"


def inspect_env(path: Path) -> dict:
    report: dict = {
        "network_requests": 0,
        "credentials_loaded_into_environment": False,
        "credentials_authenticated": False,
        "test_owner_authorized": False,
        "deployment_ready": "NOT_ESTABLISHED_BY_THIS_CHECK",
    }
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return {**report, "file_status": "refused_nonregular_file"}
        # Inspect and read the SAME descriptor. A path replacement after lstat
        # must not bypass permissions/size checks. Nonblocking avoids a swapped
        # FIFO blocking before fstat; no-follow refuses a swapped symlink.
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags), "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return {**report, "file_status": "refused_nonregular_file"}
            if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                return {**report, "file_status": "refused_not_private_to_current_user"}
            if metadata.st_size > 1_000_000:
                return {**report, "file_status": "refused_oversized_file"}
            raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                return {**report, "file_status": "refused_oversized_file"}
            content = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return {**report, "file_status": "unreadable_or_missing"}
    values, duplicates, invalid = parse(content)
    statuses = {name: ("duplicate_REVIEW_REQUIRED" if name in duplicates else
                       "present_unvalidated" if values.get(name) else "missing_or_empty")
                for name in FIELDS}
    report.update(
        file_status="private_nonempty" if content.strip() else "private_empty",
        format_status="REVIEW_REQUIRED" if invalid or duplicates else "simple_dotenv",
        invalid_line_numbers=invalid,
        duplicate_assignment_count=len(duplicates),
        recognized_fields=statuses,
        other_field_count=len(set(values) - set(FIELDS)),
        endpoints={name: "duplicate_REVIEW_REQUIRED" if name in duplicates else
                   endpoint_kind(values.get(name, ""))
                   for name in ("ANTICIPY_PB", "ANTICIPY_BACKEND_URL")},
        owner_defaults="IGNORED_REQUIRE_EXPLICIT_FRESH_TEST_ACCOUNT",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    report = inspect_env(args.env_file)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if (report["file_status"] == "private_nonempty" and
                 report.get("format_status") == "simple_dotenv") else 2


if __name__ == "__main__":
    raise SystemExit(main())
