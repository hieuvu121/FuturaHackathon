"""Assigns and ranks the three buckets. Owner: Track D.

  Revise    = touched, not verified
  Deepen    = touched AND verified
  Learn New = never touched, in demand

Ranked by job-ad frequency weighted by proximity to what was already touched.
MUST produce a sensible ordering when frequency is None -- fall back to
proximity alone rather than dropping the item or crashing.
"""

from collections import defaultdict

from ...schemas.common import Evidence, SourceKind
from ...schemas.market import MarketSkill
from ...schemas.roadmap import Bucket, Buckets, RoadmapItem
from ...schemas.scores import SkillStatus, Tier
from ..knowledge.base import SkillTaxonomy


def _canonical(skill_id: str, taxonomy: SkillTaxonomy | None) -> str:
    if taxonomy is None:
        return skill_id
    return taxonomy.normalise(skill_id) or skill_id


def _skill_name(skill_id: str, taxonomy: SkillTaxonomy | None) -> str:
    if taxonomy is not None:
        try:
            return taxonomy.name(skill_id)
        except KeyError:
            pass
    return skill_id.replace("_", " ").title()


def _ancestors(skill_id: str, taxonomy: SkillTaxonomy | None) -> set[str]:
    if taxonomy is None:
        return {skill_id}
    found = {skill_id}
    pending = [skill_id]
    while pending:
        current = pending.pop()
        try:
            parents = taxonomy.parents(current)
        except KeyError:
            parents = []
        for parent in parents:
            if parent not in found:
                found.add(parent)
                pending.append(parent)
    return found


def _proximity(skill_id: str, known: set[str], taxonomy: SkillTaxonomy | None) -> float:
    if skill_id in known:
        return 1.0
    if not known:
        return 0.25
    candidate_graph = _ancestors(skill_id, taxonomy)
    known_graph = set().union(*(_ancestors(item, taxonomy) for item in known))
    if candidate_graph & known_graph:
        return 0.75
    return 0.25


def _priority(market: MarketSkill | None, proximity: float) -> float:
    if market is None or market.frequency is None:
        return round(proximity, 4)
    return round(market.frequency * proximity, 4)


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, tuple[int, int], str | None]] = set()
    result: list[Evidence] = []
    for evidence in items:
        key = (evidence.file, evidence.lines, evidence.commit)
        if key not in seen:
            seen.add(key)
            result.append(evidence)
    return result


def _known_reason(bucket: Bucket) -> str:
    if bucket == Bucket.DEEPEN:
        return "Verified by repository or recall evidence; deepen it through a harder application."
    return "Touched in repository evidence but not yet verified; revise it before advancing."


def _learn_reason(market: MarketSkill, proximity: float) -> str:
    source = market.provenance.source_kind
    provisional = source in {SourceKind.SEEDED, SourceKind.ESTIMATED}
    label = f"{source.value} provisional" if provisional else source.value
    if market.frequency is None:
        return (
            f"Not yet touched. {label.title()} demand frequency is unavailable; "
            f"ranked by taxonomy proximity ({proximity:.2f})."
        )
    qualifier = " Validate it against measured market data." if provisional else ""
    return (
        f"Not yet touched. {label.title()} demand frequency is {market.frequency:.0%}; "
        f"weighted by taxonomy proximity ({proximity:.2f}).{qualifier}"
    )


def build(
    skills: list[SkillStatus],
    demand: dict[str, MarketSkill | None],
    role: str,
    region: str,
    taxonomy: SkillTaxonomy | None = None,
) -> Buckets:
    grouped: dict[str, dict] = defaultdict(lambda: {"tiers": set(), "evidence": []})
    for status in skills:
        skill_id = _canonical(status.skill_id, taxonomy)
        grouped[skill_id]["tiers"].add(status.tier)
        grouped[skill_id]["evidence"].extend(status.evidence)

    market_by_skill: dict[str, MarketSkill | None] = {}
    for raw_skill_id, market in demand.items():
        skill_id = _canonical(raw_skill_id, taxonomy)
        canonical_market = market.model_copy(update={"skill_id": skill_id}) if market else None
        if skill_id not in market_by_skill or market_by_skill[skill_id] is None:
            market_by_skill[skill_id] = canonical_market

    known = set(grouped)
    revise: list[RoadmapItem] = []
    deepen: list[RoadmapItem] = []
    learn_new: list[RoadmapItem] = []

    for skill_id, status in grouped.items():
        market = market_by_skill.get(skill_id)
        bucket = Bucket.DEEPEN if Tier.VERIFIED in status["tiers"] else Bucket.REVISE
        item = RoadmapItem(
            skill_id=skill_id,
            skill_name=_skill_name(skill_id, taxonomy),
            bucket=bucket,
            reason=_known_reason(bucket),
            evidence=_dedupe_evidence(status["evidence"]),
            market_frequency=market.frequency if market else None,
            provenance=market.provenance if market else None,
            priority=_priority(market, 1.0),
        )
        (deepen if bucket == Bucket.DEEPEN else revise).append(item)

    for skill_id, market in market_by_skill.items():
        if skill_id in known or market is None:
            continue
        proximity = _proximity(skill_id, known, taxonomy)
        learn_new.append(
            RoadmapItem(
                skill_id=skill_id,
                skill_name=_skill_name(skill_id, taxonomy),
                bucket=Bucket.LEARN_NEW,
                reason=_learn_reason(market, proximity),
                evidence=[],
                market_frequency=market.frequency,
                provenance=market.provenance,
                priority=_priority(market, proximity),
            )
        )

    ordering = lambda item: (-item.priority, item.skill_id)
    revise.sort(key=ordering)
    deepen.sort(key=ordering)
    learn_new.sort(key=ordering)
    return Buckets(role=role, region=region, revise=revise, deepen=deepen, learn_new=learn_new)
