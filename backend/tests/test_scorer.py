"""Deterministic metric and finding scorer tests."""

from datetime import UTC, datetime

from app.schemas.findings import Finding
from app.schemas.repo_map import FunctionNode, RepoMap
from app.services.analyze.scorer import score


class FakeLadder:
    def dimensions(self):
        return [
            "code_structure",
            "testing",
            "error_handling",
            "domain_modelling",
            "version_control",
            "security_awareness",
        ]

    def levels(self, dimension):
        return {level: f"{dimension} level {level}." for level in range(1, 5)}

    def metric_thresholds(self, dimension):
        thresholds = {
            "code_structure": {
                "median_complexity": {1: ">15", 2: "8-15", 3: "4-8", 4: "<4"},
                "max_nesting_depth": {1: ">6", 2: "5-6", 3: "3-4", 4: "<3"},
            },
            "testing": {"test_coverage_ratio": {1: "<0.05", 2: "0.05-0.3", 3: "0.3-0.6", 4: ">0.6"}},
            "error_handling": {"empty_catch_count": {1: ">5", 2: "2-5", 3: "1", 4: "0"}},
            "domain_modelling": {"domain_inconsistency_findings": {1: ">5", 2: "2-5", 3: "1", 4: "0"}},
            "version_control": {
                "median_commit_size": {1: ">800", 2: "300-800", 3: "80-300", 4: "<80"},
                "refactor_ratio": {1: "<0.02", 2: "0.02-0.08", 3: "0.08-0.2", 4: ">0.2"},
            },
            "security_awareness": {"hardcoded_secret_count": {1: ">0", 2: "0", 3: "0", 4: "0"}},
        }
        return thresholds[dimension]

    def target_level(self, dimension, role, seniority):
        return 3


class FakeTaxonomy:
    IDS = {
        "python": "python",
        "clean code": "clean_code",
        "unit testing": "testing_unit",
        "debugging": "debugging",
        "data modelling": "data_modelling",
        "git": "git",
        "secure coding": "secure_coding",
    }

    def normalise(self, raw):
        return self.IDS.get(raw)

    def parents(self, skill_id):
        return []

    def name(self, skill_id):
        return skill_id


def _repo(functions):
    return RepoMap(
        repo="owner/project",
        language="python",
        analyzed_at=datetime.now(UTC),
        total_files=2,
        functions=functions,
    )


def _function(name, complexity, nesting, tested):
    return FunctionNode(
        name=name,
        file="app.py",
        lines=(1, 10),
        complexity=complexity,
        nesting_depth=nesting,
        loc=10,
        has_test=tested,
    )


def _finding(dimension):
    return Finding.model_validate(
        {
            "id": f"finding-{dimension}",
            "dimension": dimension,
            "severity": "medium",
            "observation": "Grounded observation.",
            "evidence": {"file": "app.py", "lines": [1, 2], "commit": "abc"},
            "confidence": 0.9,
        }
    )


def test_score_combines_metrics_findings_and_repository_history():
    repo = _repo([
        _function("simple", 2, 1, True),
        _function("complex", 10, 5, False),
    ])
    findings = [_finding("domain_modelling"), _finding("security_awareness")]

    scores = score(
        repo,
        findings,
        FakeLadder(),
        FakeTaxonomy(),
        {
            "empty_catch_count": 1,
            "hardcoded_secret_count": 0,
            "median_commit_size": 142,
            "refactor_ratio": 0.14,
            "commits_analyzed": 20,
        },
    )

    levels = {dimension.dimension: dimension for dimension in scores.dimensions}
    assert levels["code_structure"].level == 2  # nesting is the weaker metric
    assert levels["testing"].level == 3
    assert levels["error_handling"].level == 3
    assert levels["domain_modelling"].level == 3
    assert levels["version_control"].level == 3
    assert levels["security_awareness"].level == 2
    assert levels["security_awareness"].evidence == [findings[1].evidence]
    assert levels["version_control"].metric_basis["commits_analyzed"] == 20
    assert {skill.skill_id for skill in scores.skills} >= {"python", "git", "secure_coding"}
    assert all(skill.tier.value == "touched" for skill in scores.skills)


def test_score_does_not_reward_empty_repository_or_missing_history():
    scores = score(_repo([]), [], FakeLadder(), FakeTaxonomy())
    levels = {dimension.dimension: dimension.level for dimension in scores.dimensions}

    assert levels["code_structure"] == 1
    assert levels["testing"] == 1
    assert levels["version_control"] == 1


def test_hardcoded_secret_forces_lowest_security_level():
    scores = score(
        _repo([_function("safe", 1, 0, True)]),
        [],
        FakeLadder(),
        FakeTaxonomy(),
        {"hardcoded_secret_count": 1},
    )

    security = next(item for item in scores.dimensions if item.dimension == "security_awareness")
    assert security.level == 1
