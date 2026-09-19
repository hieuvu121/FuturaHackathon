"""The anti-hallucination gate. Owner: Track B.

Rejects any finding whose cited file does not exist, or whose line range falls
outside that file. Dropped findings never reach storage or UI.

This file is the product's credibility. Test it first.
"""

from pathlib import Path

from ...schemas.findings import Finding


def validate(root: Path, findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """Returns (kept, dropped). Log the dropped ones; never serve them."""
    raise NotImplementedError
