"""Groups the forward-looking buckets into concept nodes for the roadmap diagram.

The diagram shows concepts on a spine; a concept box carries the concept only
and the personalised detail lives behind a click. This module decides four
things and nothing else:

  * which concept a skill hangs off  -- its nearest taxonomy root
  * what standing the user has in it -- verified / familiar / new
  * how far along they are           -- `mastery`, which drives the bars
  * what they should do next         -- the `focus` line

`focus` is derived, never guessed. Where the scanner found a real problem in
the user's code, the line names that problem and the file it lives in, so the
advice reads as "this is wrong here, learn this to fix it" rather than as a
generic syllabus. A skill the user has never touched can still be justified by
a gap in code they HAVE written -- an N+1 query in their data access is the
argument for learning query optimisation. No model is called here, so the
diagram cannot fail mid-demo.

Market frequency never enters the prose: it has its own bar and chip. Keeping
it out is what holds these lines short.
"""

import re

from ...schemas.common import Evidence
from ...schemas.findings import Finding
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

MASTERY = {NodeStatus.VERIFIED: 1.0, NodeStatus.FAMILIAR: 0.5, NodeStatus.NEW: 0.0}

MAX_PROBLEM_CHARS = 62

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

# Findings carry a scanner dimension, not a skill id. This is the join: which
# skills a problem in that dimension is an argument for learning.
DIMENSION_SKILLS: dict[str, set[str]] = {
    "code_structure": {
        "clean_code", "design_patterns", "system_design", "object_oriented_programming",
        "functional_programming", "microservices",
    },
    "testing": {
        "testing_unit", "testing_integration", "testing_e2e", "test_driven_development",
        "mocking", "property_testing", "frontend_testing", "contract_testing",
    },
    "error_handling": {"debugging", "clean_code", "observability", "incident_response"},
    "domain_modelling": {
        "data_modelling", "database_design", "orm", "sql", "postgresql", "mysql",
        "sqlite", "mongodb", "caching", "data_structures",
    },
    "version_control": {"git", "code_review", "agile_delivery"},
    "security_awareness": {
        "secure_coding", "owasp", "authentication", "oauth", "cryptography",
        "secrets_management", "threat_modelling", "dependency_security",
    },
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
    """Known skills this one builds on -- a shared ancestor is enough."""
    if taxonomy is None:
        return []
    candidate = _ancestors(skill_id, taxonomy)
    names = [
        name
        for other_id, name in known.items()
        if other_id != skill_id and candidate & _ancestors(other_id, taxonomy)
    ]
    return sorted(set(names))


def _reference(evidence: Evidence) -> str:
    """Basename only -- the evidence link carries the full path."""
    return f"{evidence.file.rsplit('/', 1)[-1]}:{evidence.lines[0]}"


def _problem(observation: str) -> str:
    """Compress a scanner observation into a phrase that fits on one line.

    The scanner writes prose; the diagram has room for a clause. Take the first
    sentence, drop the throat-clearing opener, and cut on a word boundary.
    """
    sentence = re.split(r"(?<=[.!?])\s", observation.strip())[0].rstrip(".")
    sentence = re.sub(
        r"^(this|the)\s+(module|function|file|code|method|class)\s+", "", sentence, flags=re.I
    )
    if len(sentence) <= MAX_PROBLEM_CHARS:
        return sentence
    head = sentence[:MAX_PROBLEM_CHARS]
    if "," in head:
        clause = head.rsplit(",", 1)[0]
        if len(clause) >= 24:
            return clause
    # Drop the partial word the slice left behind, or the line ends mid-token.
    return f"{head.rsplit(' ', 1)[0]}..."


def _severity_rank(finding: Finding) -> tuple[int, float]:
    order = {"high": 0, "medium": 1, "low": 2}
    return (order.get(finding.severity.value, 3), -finding.confidence)


def _assign_gaps(findings: list[Finding], skill_ids: list[str]) -> dict[str, Finding]:
    """Give each skill its own finding, dealt round-robin within a dimension.

    A dimension usually has far more findings than skills, so handing every
    skill the single most severe one would print the same sentence three times
    under one concept. Dealing them out keeps each node saying something new.
    Findings that survive compression intact are dealt first.
    """
    by_dimension: dict[str, list[Finding]] = {}
    for finding in findings:
        by_dimension.setdefault(finding.dimension, []).append(finding)
    for dimension, rows in by_dimension.items():
        rows.sort(key=lambda f: (len(_problem(f.observation)) > MAX_PROBLEM_CHARS, *_severity_rank(f)))

    assigned: dict[str, Finding] = {}
    for dimension, rows in by_dimension.items():
        claimants = [s for s in skill_ids if s in DIMENSION_SKILLS.get(dimension, ())]
        for index, skill_id in enumerate(sorted(claimants)):
            if rows:
                assigned[skill_id] = rows[index % len(rows)]
    return assigned


def _focus(
    item: RoadmapItem,
    status: NodeStatus,
    related: list[str],
    gap: Finding | None,
) -> str:
    """Short. Two parts: what is true of their code, then what to do about it."""
    name = item.skill_name
    if gap is not None:
        problem = _problem(gap.observation)
        where = _reference(gap.evidence)
        if status is NodeStatus.NEW:
            return f"{where}: {problem}. Learn {name} to fix it."
        if status is NodeStatus.VERIFIED:
            return f"{where}: {problem}. Harden it."
        return f"{where}: {problem}. Optimise it."

    if status is NodeStatus.VERIFIED:
        evidence = item.evidence[0] if item.evidence else None
        where = f"Proven in {_reference(evidence)}. " if evidence else ""
        return f"{where}Push into performance and edge cases."
    if status is NodeStatus.FAMILIAR:
        evidence = item.evidence[0] if item.evidence else None
        where = f"Written in {_reference(evidence)}, unchecked. " if evidence else ""
        return f"{where}Prove it, then cover the gaps."
    if related:
        return f"Builds on {_join(related)} -- learn what differs."
    return f"New ground. Start with {name} fundamentals."


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) > 3:
        names = names[:3]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _to_node(
    item: RoadmapItem,
    status: NodeStatus,
    known: dict[str, str],
    taxonomy: SkillTaxonomy | None,
    gaps: dict[str, Finding],
) -> ConceptSkill:
    related = _related_names(item.skill_id, known, taxonomy) if status is NodeStatus.NEW else []
    gap = gaps.get(item.skill_id)
    return ConceptSkill(
        skill_id=item.skill_id,
        skill_name=item.skill_name,
        status=status,
        focus=_focus(item, status, related, gap),
        mastery=MASTERY[status],
        gap_evidence=gap.evidence if gap is not None else None,
        related_to=related,
        evidence=item.evidence,
        market_frequency=item.market_frequency,
        provenance=item.provenance,
        priority=item.priority,
    )


def graph_from_buckets(
    buckets: Buckets,
    taxonomy: SkillTaxonomy | None = None,
    findings: list[Finding] | None = None,
) -> RoadmapGraph:
    """Regroup an already-built roadmap. `revise` is reframed, never replayed.

    The diagram is forward-looking, so a touched-but-unverified skill appears as
    FAMILIAR with a next step, rather than as a backlog item to go back and fix.
    """
    present = [
        item.skill_id
        for item in (*buckets.deepen, *buckets.revise, *buckets.learn_new)
    ]
    gaps = _assign_gaps(findings or [], present)
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
        node = _to_node(item, status, known, taxonomy, gaps)
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
                mastery=round(sum(node.mastery for node in nodes) / len(nodes), 4),
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
    findings: list[Finding] | None = None,
) -> RoadmapGraph:
    """Bucket the skills the usual way, then regroup them by concept."""
    return graph_from_buckets(build(skills, demand, role, region, taxonomy), taxonomy, findings)
