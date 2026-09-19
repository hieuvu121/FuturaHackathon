"""Groups the forward-looking buckets into concept nodes for the roadmap diagram.

The diagram shows concepts on a spine; a concept box carries the concept only
and the personalised detail lives behind a click. This module decides three
things and nothing else:

  * which concept a skill hangs off  -- its nearest taxonomy root
  * what standing the user has in it -- verified / familiar / new
  * what they should do next about it -- the `focus` line

`focus` is derived, never guessed: it reads the tier the evidence earned, the
file that earned it, and the taxonomy distance to work the user has already
done. No model is called here, so the diagram cannot fail mid-demo. Market
frequency is appended only when a source actually has a number -- an unknown
stays unknown, exactly as in buckets.py.
"""

from ...schemas.market import MarketSkill
from ...schemas.roadmap import (
    Buckets,
    ConceptSkill,
    NodeStatus,
    RoadmapConcept,
    RoadmapGraph,
    RoadmapItem,
)
from ...schemas.scores import SkillStatus
from ..knowledge.base import SkillTaxonomy
from .buckets import build

UNGROUPED = "general"

# One line per taxonomy root, written for a reader deciding where to spend a week.
CONCEPT_SUMMARY: dict[str, str] = {
    "programming_languages": "The languages you write in, and the next one worth adding.",
    "programming_concepts": "The fundamentals your code leans on whichever language you pick.",
    "backend": "Server-side work: the services, frameworks and runtime behaviour behind an app.",
    "frontend": "What users actually touch -- markup, styling, components and browser behaviour.",
    "mobile": "Shipping to phones, where the constraints differ from the web.",
    "data": "Storing, shaping and querying the data your services depend on.",
    "testing": "Proving the code does what you believe it does.",
    "devops": "Getting the code off your machine and keeping it running.",
    "cloud": "The platforms your services run on and what they charge you for.",
    "security": "The failure modes an attacker looks for before you do.",
    "api_design": "The contracts between services, and how they survive change.",
    "version_control": "How work is tracked, reviewed and recovered.",
    "collaboration": "The practice around the code: review, docs and delivery.",
    UNGROUPED: "Skills that sit outside the seeded taxonomy.",
}


def _humanise(value: str) -> str:
    return value.replace("_", " ").strip() or "engineering"


def _ancestors(skill_id: str, taxonomy: SkillTaxonomy | None) -> set[str]:
    """Every skill at or above `skill_id`, including itself."""
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


def _concept_of(skill_id: str, taxonomy: SkillTaxonomy | None) -> str:
    """The nearest taxonomy root, breadth-first so the shortest climb wins.

    `fastapi` has parents [python, backend]; backend is a root one step up while
    programming_languages is two, so FastAPI hangs off Backend rather than off
    Programming Languages. Ties fall to the order skills.yaml lists parents in,
    which puts the primary parent first.
    """
    if taxonomy is None:
        return UNGROUPED
    try:
        if not taxonomy.parents(skill_id):
            return skill_id
    except KeyError:
        return UNGROUPED

    seen = {skill_id}
    frontier = [skill_id]
    while frontier:
        next_frontier: list[str] = []
        for current in frontier:
            try:
                parents = taxonomy.parents(current)
            except KeyError:
                parents = []
            for parent in parents:
                if parent in seen:
                    continue
                seen.add(parent)
                try:
                    if not taxonomy.parents(parent):
                        return parent
                except KeyError:
                    continue
                next_frontier.append(parent)
        frontier = next_frontier
    return UNGROUPED


def _concept_name(concept_id: str, taxonomy: SkillTaxonomy | None) -> str:
    if concept_id == UNGROUPED:
        return "Other"
    if taxonomy is not None:
        try:
            return taxonomy.name(concept_id)
        except KeyError:
            pass
    return concept_id.replace("_", " ").title()


def _related_names(
    skill_id: str,
    known: dict[str, str],
    taxonomy: SkillTaxonomy | None,
) -> list[str]:
    """Known skills this one builds on -- a shared ancestor is enough.

    Django shares `python` with work already done, so it is not a cold start.
    Flutter shares nothing with a Python portfolio, so it is.
    """
    if taxonomy is None:
        return []
    candidate = _ancestors(skill_id, taxonomy)
    names = [
        name
        for other_id, name in known.items()
        if other_id != skill_id and candidate & _ancestors(other_id, taxonomy)
    ]
    return sorted(set(names))


def _evidence_reference(item: RoadmapItem) -> str | None:
    if not item.evidence:
        return None
    evidence = item.evidence[0]
    return f"{evidence.file}:{evidence.lines[0]}-{evidence.lines[1]}"


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _market_note(frequency: float | None, role: str) -> str:
    """Silence when the number is unknown. Never dress a gap up as a measurement."""
    if frequency is None:
        return ""
    return f" Named in {frequency:.0%} of sampled {_humanise(role)} ads."


def _focus(
    item: RoadmapItem,
    status: NodeStatus,
    related: list[str],
    role: str,
) -> str:
    name = item.skill_name
    if status is NodeStatus.VERIFIED:
        reference = _evidence_reference(item)
        where = f" in {reference}" if reference else ""
        body = (
            f"Verified{where}. You are past explaining {name} -- focus on depth: "
            "performance, edge cases and the trade-offs behind the design."
        )
    elif status is NodeStatus.FAMILIAR:
        reference = _evidence_reference(item)
        where = f" ({reference})" if reference else ""
        body = (
            f"You have written {name}{where} but nothing has checked it yet. "
            "You are past the basics -- focus on optimising what you already "
            "wrote and on the cases you have not had to handle."
        )
    elif related:
        body = (
            f"New to you, but it builds on {_join(related)}, which you already "
            f"work in. Skip the introductions and focus on what {name} does "
            "differently."
        )
    else:
        body = (
            f"New ground -- nothing in your code touches it. Start with the "
            f"fundamentals of {name}."
        )
    return body + _market_note(item.market_frequency, role)


def _to_node(
    item: RoadmapItem,
    status: NodeStatus,
    known: dict[str, str],
    taxonomy: SkillTaxonomy | None,
    role: str,
) -> ConceptSkill:
    related = _related_names(item.skill_id, known, taxonomy) if status is NodeStatus.NEW else []
    return ConceptSkill(
        skill_id=item.skill_id,
        skill_name=item.skill_name,
        status=status,
        focus=_focus(item, status, related, role),
        related_to=related,
        evidence=item.evidence,
        market_frequency=item.market_frequency,
        provenance=item.provenance,
        priority=item.priority,
    )


def graph_from_buckets(
    buckets: Buckets,
    taxonomy: SkillTaxonomy | None = None,
) -> RoadmapGraph:
    """Regroup an already-built roadmap. `revise` is reframed, never replayed.

    The diagram is forward-looking, so a touched-but-unverified skill appears as
    FAMILIAR with a next step, rather than as a backlog item to go back and fix.
    """
    known = {
        item.skill_id: item.skill_name
        for item in (*buckets.deepen, *buckets.revise)
    }
    staged: list[tuple[RoadmapItem, NodeStatus]] = [
        *((item, NodeStatus.VERIFIED) for item in buckets.deepen),
        *((item, NodeStatus.FAMILIAR) for item in buckets.revise),
        *((item, NodeStatus.NEW) for item in buckets.learn_new),
    ]

    grouped: dict[str, list[ConceptSkill]] = {}
    for item, status in staged:
        node = _to_node(item, status, known, taxonomy, buckets.role)
        grouped.setdefault(_concept_of(item.skill_id, taxonomy), []).append(node)

    concepts: list[RoadmapConcept] = []
    for concept_id, nodes in grouped.items():
        nodes.sort(key=lambda node: (-node.priority, node.skill_name))
        concepts.append(
            RoadmapConcept(
                concept_id=concept_id,
                concept_name=_concept_name(concept_id, taxonomy),
                summary=CONCEPT_SUMMARY.get(
                    concept_id, f"Where your {_concept_name(concept_id, taxonomy).lower()} work goes next."
                ),
                verified_count=sum(1 for n in nodes if n.status is NodeStatus.VERIFIED),
                familiar_count=sum(1 for n in nodes if n.status is NodeStatus.FAMILIAR),
                new_count=sum(1 for n in nodes if n.status is NodeStatus.NEW),
                priority=max(node.priority for node in nodes),
                skills=nodes,
            )
        )

    # Ungrouped skills are a fallback bucket, so they trail the real concepts
    # however in demand they look.
    concepts.sort(
        key=lambda concept: (
            concept.concept_id == UNGROUPED,
            -concept.priority,
            concept.concept_name,
        )
    )
    return RoadmapGraph(role=buckets.role, region=buckets.region, concepts=concepts)


def build_graph(
    skills: list[SkillStatus],
    demand: dict[str, MarketSkill | None],
    role: str,
    region: str,
    taxonomy: SkillTaxonomy | None = None,
) -> RoadmapGraph:
    """Bucket the skills the usual way, then regroup them by concept."""
    return graph_from_buckets(build(skills, demand, role, region, taxonomy), taxonomy)
