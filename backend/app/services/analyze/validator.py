"""The anti-hallucination gate. Owner: Track B.

Rejects any finding whose cited file does not exist, or whose line range falls
outside that file. Dropped findings never reach storage or UI.

This file is the product's credibility. Test it first.
"""

import logging
from pathlib import Path

from ...schemas.findings import Finding

logger = logging.getLogger(__name__)


def _line_count(path: Path) -> int:
    """Count physical lines without assuming that source files are UTF-8."""
    with path.open("rb") as source:
        return sum(1 for _ in source)


def validate(root: Path, findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Returns (kept, dropped). Log the dropped ones; never serve them."""
    root = root.resolve()
    kept: list[Finding] = []
    dropped: list[Finding] = []

    for finding in findings:
        evidence = finding.evidence
        reason: str | None = None

        try:
            source_path = (root / evidence.file).resolve()
            if not source_path.is_relative_to(root):
                reason = "evidence path escapes the repository"
            elif not source_path.is_file():
                reason = "evidence file does not exist or is not a file"
            else:
                start, end = evidence.lines
                if start < 1 or end < start:
                    reason = "evidence line range is not a valid inclusive 1-based range"
                elif end > _line_count(source_path):
                    reason = "evidence line range extends past the end of the file"
        except (OSError, RuntimeError) as exc:
            reason = f"evidence file could not be resolved or read: {exc}"

        if reason is None:
            kept.append(finding)
        else:
            dropped.append(finding)
            logger.warning("Dropped finding %s: %s", finding.id, reason)

    return kept, dropped
