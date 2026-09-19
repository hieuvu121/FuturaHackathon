"""Where the LLM enters. Owner: Track B.

Sends each ranked file to the model with a fixed prompt asking for qualitative
design problems metrics cannot capture: business logic in controllers,
inconsistent modelling of one concept, misplaced abstractions, over-engineering,
domain-naive naming.

EVERY observation must cite file and lines. Returns RAW candidates -- unvalidated.
"""

from pathlib import Path

from ...config import Settings
from ...schemas.findings import Finding

SCAN_PROMPT = """You are reviewing one source file for qualitative design problems
that static metrics cannot capture. Report only what you can point at.

Look for: business logic living in controllers/routers, one domain concept modelled
inconsistently across the file, abstractions at the wrong level, over-engineering for
requirements that do not exist, and naming that reveals no domain understanding.

For every observation you MUST cite the exact file path and a line range that exists
in the file shown. Do not report style, formatting, or anything a linter would catch.
"""


def scan_file(settings: Settings, root: Path, rel_path: str) -> list[Finding]:
    raise NotImplementedError
