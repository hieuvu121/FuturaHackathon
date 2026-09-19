"""Aggregate completed repository analyses into one user capability portfolio."""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.db import Analysis, PortfolioRepo, Repo, SkillStatusRow, User
from ..schemas.common import Evidence
from ..schemas.findings import Finding
from ..schemas.portfolio import PortfolioProfile, PortfolioRepoSummary
from ..schemas.repo_map import RepoMap
from ..schemas.scores import DimensionScore, Scores, SkillStatus, Tier
from .storage import latest_analysis


def owned_selected_repos(db: Session, github_login: str) -> list[Repo]:
    return list(
        db.scalars(
            select(Repo)
            .join(PortfolioRepo, PortfolioRepo.repo_id == Repo.id)
            .join(User, PortfolioRepo.user_id == User.id)
            .where(User.github_login == github_login, Repo.user_id == User.id)
            .order_by(PortfolioRepo.selected_at, Repo.id)
        ).all()
    )


def replace_selection(
    db: Session,
    github_login: str,
    repo_ids: list[str],
) -> list[Repo]:
    try:
        numeric_ids = list(dict.fromkeys(int(repo_id) for repo_id in repo_ids))
    except ValueError as exc:
        raise ValueError("Repository ids must be numeric") from exc
    if not 3 <= len(numeric_ids) <= 5:
        raise ValueError("Select between 3 and 5 distinct repositories")
    owner = db.scalar(select(User).where(User.github_login == github_login))
    if owner is None:
        raise LookupError("User not found")
    repos = list(
        db.scalars(
            select(Repo)
            .where(Repo.user_id == owner.id, Repo.id.in_(numeric_ids))
            .order_by(Repo.id)
        ).all()
    )
    if {repo.id for repo in repos} != set(numeric_ids):
        raise LookupError("One or more repositories are unavailable")
    db.execute(delete(PortfolioRepo).where(PortfolioRepo.user_id == owner.id))
    db.add_all(PortfolioRepo(user_id=owner.id, repo_id=repo_id) for repo_id in numeric_ids)
    db.commit()
    by_id = {repo.id: repo for repo in repos}
    return [by_id[repo_id] for repo_id in numeric_ids]


def _summary(repo: Repo, analysis: Analysis | None) -> PortfolioRepoSummary:
    return PortfolioRepoSummary(
        id=str(repo.id),
        full_name=repo.full_name,
        language=repo.language,
        stage=analysis.stage if analysis else "not_started",
        progress=analysis.progress if analysis else 0,
    )


def selection_summaries(db: Session, repos: list[Repo]) -> list[PortfolioRepoSummary]:
    return [_summary(repo, latest_analysis(db, repo.id)) for repo in repos]


def _portfolio_evidence(raw: dict | Evidence, repo_id: int) -> Evidence:
    evidence = raw if isinstance(raw, Evidence) else Evidence.model_validate(raw)
    return evidence.model_copy(update={"repo_id": str(repo_id)})


def build_profile(db: Session, github_login: str) -> PortfolioProfile:
    repos = owned_selected_repos(db, github_login)
    if not repos:
        raise LookupError("No repositories are selected")

    analyses: list[tuple[Repo, Analysis, RepoMap, Scores]] = []
    for repo in repos:
        analysis = latest_analysis(db, repo.id)
        if analysis and analysis.repo_map and analysis.scores is not None:
            analyses.append(
                (
                    repo,
                    analysis,
                    RepoMap.model_validate(analysis.repo_map),
                    Scores.model_validate(analysis.scores),
                )
            )
    if not analyses:
        raise LookupError("The selected portfolio has no completed analysis")

    dimensions: dict[str, list[tuple[DimensionScore, int, int]]] = defaultdict(list)
    skills: dict[str, dict] = defaultdict(lambda: {"tiers": set(), "evidence": []})
    findings: list[Finding] = []
    total_files = total_functions = excluded_files = 0

    for repo, analysis, repo_map, scores in analyses:
        weight = max(len(repo_map.functions), 1)
        total_files += repo_map.total_files
        total_functions += len(repo_map.functions)
        excluded_files += len(repo_map.excluded_files)
        for dimension in scores.dimensions:
            dimensions[dimension.dimension].append((dimension, weight, repo.id))
        for raw in analysis.findings or []:
            finding = Finding.model_validate(raw)
            findings.append(
                finding.model_copy(
                    update={
                        "id": f"{repo.id}:{finding.id}",
                        "evidence": _portfolio_evidence(finding.evidence, repo.id),
                    }
                )
            )

    aggregate_dimensions: list[DimensionScore] = []
    for dimension_id, rows in dimensions.items():
        weight_total = sum(weight for _, weight, _ in rows)
        level = round(sum(item.level * weight for item, weight, _ in rows) / weight_total)
        evidence: list[Evidence] = []
        for item, _, repo_id in rows:
            evidence.extend(_portfolio_evidence(pointer, repo_id) for pointer in item.evidence)
        aggregate_dimensions.append(
            DimensionScore(
                dimension=dimension_id,
                level=max(1, min(4, level)),
                rationale=(
                    f"Function-weighted portfolio level across {len(rows)} repositories. "
                    + " ".join(item.rationale for item, _, _ in rows)
                ),
                evidence=evidence,
                metric_basis={
                    "repositories_analyzed": len(rows),
                    "functions_weighted": weight_total,
                },
            )
        )

    selected_ids = [repo.id for repo in repos]
    for row in db.scalars(
        select(SkillStatusRow).where(
            SkillStatusRow.user_id == repos[0].user_id,
            SkillStatusRow.repo_id.in_(selected_ids),
        )
    ).all():
        item = skills[row.skill_id]
        item["tiers"].add(Tier(row.tier))
        item["evidence"].extend(
            _portfolio_evidence(evidence, row.repo_id) for evidence in (row.evidence or [])
        )

    aggregate_skills = [
        SkillStatus(
            skill_id=skill_id,
            tier=Tier.VERIFIED if Tier.VERIFIED in item["tiers"] else Tier.TOUCHED,
            evidence=item["evidence"],
        )
        for skill_id, item in sorted(skills.items())
    ]
    return PortfolioProfile(
        repositories=selection_summaries(db, repos),
        total_files=total_files,
        total_functions=total_functions,
        excluded_files=excluded_files,
        scores=Scores(
            repo="portfolio",
            dimensions=sorted(aggregate_dimensions, key=lambda item: item.dimension),
            skills=aggregate_skills,
        ),
        findings=findings,
    )
