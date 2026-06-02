"""Shared comment-row model + target selection for reply verbs.

Pure logic over already-parsed UI nodes; no device access (testable with
fixture XML). Platform-specific `_parse_comment_rows(xml)` lives in each app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mobilecli.envelope import EmError, ErrorCode


@dataclass
class CommentRow:
    index: int  # 1-based, among currently-visible top-level comments
    text: str  # matchable text (username + body + meta)
    reply_node: dict[str, Any]  # the row's 回复 affordance node (bounds/cx/cy)
    content_node: dict[str, Any] | None = None  # comment-text node (XHS reply tap fallback)


def select_comment(
    rows: list[CommentRow],
    *,
    rank: int | None = None,
    match: str | None = None,
) -> CommentRow:
    """Pick exactly one comment row by rank (1-based) or by text substring match.

    Exactly one of rank/match must be given. Raises EmError otherwise / on miss.
    """
    if (rank is None) == (match is None):
        raise EmError(
            ErrorCode.UNKNOWN,
            "reply requires exactly one of --rank / --match",
            hint='pass --rank N or --match "keyword", not both / neither',
        )
    if rank is not None:
        if rank < 1 or rank > len(rows):
            raise EmError(
                ErrorCode.ELEMENT_NOT_FOUND,
                f"rank {rank} out of range (have {len(rows)} visible comments)",
                hint="scroll comments into view or lower --rank",
            )
        return rows[rank - 1]
    assert match is not None  # rank/match 互斥性已在上面校验
    for row in rows:
        if match in row.text:
            return row
    raise EmError(
        ErrorCode.ELEMENT_NOT_FOUND,
        f"no visible comment contains {match!r}",
        hint="keyword not found among currently-visible comments",
    )
