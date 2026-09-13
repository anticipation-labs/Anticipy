"""Real-schema fixture preparation for tests that undo additive migrations."""
from __future__ import annotations

import re


_SQL_TOKEN = re.compile(
    r"""'(?:[^']|'')*'|"(?:[^"]|"")*"|`(?:[^`]|``)*`|\[[^\]]*\]|--[^\r\n]*|/\*[\s\S]*?\*/"""
)


def schema_for_column_rewind(sql: str) -> str:
    """Keep executable schema SQL, replacing only lexical comments with space.

    Older SQLite misreads a comma in a comment before a removed final column:
    https://sqlite.org/forum/forumpost/c565425437dbab40c0af9fc0aaaa95df3a003085c02e82702bd7e9184389841b
    These fixtures undo migrations using DROP COLUMN, which production does
    not do. Do not edit the real schema or migration to accommodate that test
    setup bug. Quoted strings/identifiers are tokens too, so their comment-like
    contents, defaults, and escaped delimiters survive byte-for-byte. Retain
    whitespace/newlines so removing a comment never joins SQL tokens.
    """
    def replace(match: re.Match[str]) -> str:
        token = match.group()
        return re.sub(r"[^\r\n]", " ", token) if token.startswith(("--", "/*")) else token

    return _SQL_TOKEN.sub(replace, sql)
