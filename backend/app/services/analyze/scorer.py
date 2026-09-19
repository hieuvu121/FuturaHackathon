"""Metrics + findings + rubric -> levels. Owner: Track B.

Emits a level 1-4 per dimension with rationale, evidence, and the metric_basis
behind each level. Also emits SkillStatus entries at the `touched` tier.
"""

from collections import defaultdict
from statistics import median

from ...schemas.findings import Finding
from ...schemas.repo_map import RepoMap
from ...schemas.scores import DimensionScore, SkillStatus, Scores, Tier
from ..knowledge.base import SkillLadder, SkillTaxonomy

DIMENSION_SKILLS = {
    "code_structure": "clean code",
    "testing": "unit testing",
    "error_handling": "debugging",
    "domain_modelling": "data modelling",
    "version_control": "git",
    "security_awareness": "secure coding",
}


def _count_level(value: int) -> int:
    return 1 if value > 5 else 2 if value >= 2 else 3 if value == 1 else 4


def _matches_threshold(value: float, condition: str) -> bool:
    condition = str(condition).strip()
    if condition.startswith(">"):
        return value > float(condition[1:])
    if condition.startswith("<"):
        return value < float(condition[1:])
    if "-" in condition:
        lower, upper = condition.split("-", 1)
        return float(lower) <= value <= float(upper)
    return value == float(condition)


def _metric_level(ladder: SkillLadder, dimension: str, metric: str, value: float) -> int:
    thresholds = ladder.metric_thresholds(dimension)[metric]
    for level in sorted(thresholds):
        if _matches_threshold(value, thresholds[level]):
            return level
    raise ValueError(f"No {dimension}.{metric} threshold matches {value}")


def _evidence(findings: list[Finding], dimension: str):
    seen: set[tuple[str, tuple[int, int], str | None]] = set()
    result = []
    for finding in findings:
        if finding.dimension != dimension:
            continue
        pointer = finding.evidence
        key = (pointer.file, pointer.lines, pointer.commit)
        if key not in seen:
            seen.add(key)
            result.append(pointer)
    return result


def _rationale(ladder: SkillLadder, dimension: str, level: int, basis: dict) -> str:
    criterion = ladder.levels(dimension)[level]
    metrics = ", ".join(f"{name}={value}" for name, value in basis.items())
    return f"{criterion} Metric basis: {metrics}."


def score(
    repo_map: RepoMap,
    findings: list[Finding],
    ladder: SkillLadder,
    taxonomy: SkillTaxonomy,
    repository_metrics: dict[str, float | int] | None = None,
) -> Scores:
    """Score all ladder dimensions without asking an LLM to choose levels."""
    repository_metrics = repository_metrics or {}
    functions = repo_map.functions
    finding_counts: dict[str, int] = defaultdict(int)
    for finding in findings:
        finding_counts[finding.dimension] += 1

    complexities = [function.complexity for function in functions]
    tested = sum(function.has_test for function in functions)
    bases: dict[str, dict[str, float | int | str]] = {
        "code_structure": {
            "median_complexity": median(complexities) if complexities else 0,
            "max_complexity": max(complexities, default=0),
            "max_nesting_depth": max((f.nesting_depth for f in functions), default=0),
            "functions_over_50_loc": sum(f.loc > 50 for f in functions),
        },
        "testing": {
            "test_coverage_ratio": round(tested / len(functions), 4) if functions else 0.0,
            "untested_high_complexity_functions": sum(
                not function.has_test and function.complexity >= 10 for function in functions
            ),
        },
        "error_handling": {
            "empty_catch_count": int(repository_metrics.get("empty_catch_count", 0)),
            "error_handling_findings": finding_counts["error_handling"],
        },
        "domain_modelling": {
            "domain_inconsistency_findings": finding_counts["domain_modelling"],
        },
        "version_control": {
            "median_commit_size": repository_metrics.get("median_commit_size", 0),
            "refactor_ratio": repository_metrics.get("refactor_ratio", 0),
            "commits_analyzed": int(repository_metrics.get("commits_analyzed", 0)),
        },
        "security_awareness": {
            "hardcoded_secret_count": int(repository_metrics.get("hardcoded_secret_count", 0)),
            "security_risk_findings": finding_counts["security_awareness"],
        },
    }

    if functions:
        code_level = min(
            _metric_level(
                ladder,
                "code_structure",
                "median_complexity",
                float(bases["code_structure"]["median_complexity"]),
            ),
            _metric_level(
                ladder,
                "code_structure",
                "max_nesting_depth",
                float(bases["code_structure"]["max_nesting_depth"]),
            ),
        )
    else:
        code_level = 1
    levels = {
        "code_structure": code_level,
        "testing": _metric_level(
            ladder,
            "testing",
            "test_coverage_ratio",
            float(bases["testing"]["test_coverage_ratio"]),
        ),
        "error_handling": min(
            _metric_level(
                ladder,
                "error_handling",
                "empty_catch_count",
                float(bases["error_handling"]["empty_catch_count"]),
            ),
            _count_level(int(bases["error_handling"]["error_handling_findings"])),
        ),
        "domain_modelling": _metric_level(
            ladder,
            "domain_modelling",
            "domain_inconsistency_findings",
            float(bases["domain_modelling"]["domain_inconsistency_findings"]),
        ),
        "version_control": min(
            _metric_level(
                ladder,
                "version_control",
                "median_commit_size",
                float(bases["version_control"]["median_commit_size"]),
            ),
            _metric_level(
                ladder,
                "version_control",
                "refactor_ratio",
                float(bases["version_control"]["refactor_ratio"]),
            ),
        ) if bases["version_control"]["commits_analyzed"] else 1,
        "security_awareness": min(
            _metric_level(
                ladder,
                "security_awareness",
                "hardcoded_secret_count",
                float(bases["security_awareness"]["hardcoded_secret_count"]),
            ),
            _count_level(int(bases["security_awareness"]["security_risk_findings"])),
        ),
    }

    dimensions = [
        DimensionScore(
            dimension=dimension,
            level=levels[dimension],
            rationale=_rationale(ladder, dimension, levels[dimension], bases[dimension]),
            evidence=_evidence(findings, dimension),
            metric_basis=bases[dimension],
        )
        for dimension in ladder.dimensions()
    ]

    evidence_by_dimension = {
        dimension: _evidence(findings, dimension) for dimension in DIMENSION_SKILLS
    }
    touched: dict[str, list] = {}
    language_skill = taxonomy.normalise(repo_map.language)
    if language_skill:
        touched[language_skill] = []
    for dimension, raw_skill in DIMENSION_SKILLS.items():
        skill_id = taxonomy.normalise(raw_skill)
        if skill_id:
            touched[skill_id] = evidence_by_dimension[dimension]

    skills = [
        SkillStatus(skill_id=skill_id, tier=Tier.TOUCHED, evidence=evidence)
        for skill_id, evidence in touched.items()
    ]
    return Scores(repo=repo_map.repo, dimensions=dimensions, skills=skills)
