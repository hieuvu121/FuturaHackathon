"""Metrics + findings + rubric -> levels. Owner: Track B.

Emits a level 1-4 per dimension with rationale, evidence, and the metric_basis
behind each level. Also emits SkillStatus entries at the `touched` tier.
"""

from ...schemas.findings import Finding
from ...schemas.repo_map import RepoMap
from ...schemas.scores import Scores
from ..knowledge.base import SkillLadder, SkillTaxonomy


def score(
    repo_map: RepoMap,
    findings: list[Finding],
    ladder: SkillLadder,
    taxonomy: SkillTaxonomy,
) -> Scores:
    raise NotImplementedError
