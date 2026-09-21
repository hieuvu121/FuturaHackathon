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

import functools
from pathlib import Path
import re

import yaml

from ...schemas.common import Evidence
from ...schemas.findings import Finding
from ...schemas.market import MarketSkill
from ...schemas.roadmap import (
    Buckets,
    ConceptSkill,
    LearningResource,
    NodeStatus,
    Proficiency,
    RoadmapConcept,
    RoadmapGraph,
    RoadmapItem,
    RoadmapStage,
)
from ...schemas.scores import SkillStatus
from ..knowledge.base import SkillTaxonomy
from .buckets import build

UNGROUPED = "general"

MASTERY = {NodeStatus.VERIFIED: 1.0, NodeStatus.FAMILIAR: 0.5, NodeStatus.NEW: 0.0}

# Recall levels run 1-4, so the hardest drill passed is a quarter-step measure.
RECALL_LEVELS = 4
# Tried and missed every level: not nothing, since the code exists, but close to it.
MISSED_EVERYTHING = 0.1
# Verification takes a level 3 pass, so a verified skill never reads below that.
VERIFIED_FLOOR = 0.75


# Where the person's level changes, on the 0-1 mastery scale the bars already use.
# Reading the label off the bar's own number means the two can never disagree.
#   below 50%   Beginner       nothing shown yet, or recall found only "can name it"
#   50% - 99%   Intermediate   can explain it / reason about it, or has written it (untested)
#   100%        Expert         cleared the hardest recall level, "design with it"
INTERMEDIATE_AT = 0.5
EXPERT_AT = 1.0


def proficiency_of(mastery: float) -> Proficiency:
    if mastery >= EXPERT_AT:
        return Proficiency.EXPERT
    if mastery >= INTERMEDIATE_AT:
        return Proficiency.INTERMEDIATE
    return Proficiency.BEGINNER


def recall_mastery(status: NodeStatus, passed: set[int], failed: set[int]) -> float:
    """How far along a skill is, once recall has actually tested it.

    Status alone is a guess: "familiar" means the user wrote the code, not that
    they understand it. A graded drill is evidence, so where one exists it
    replaces the guess -- upwards or downwards. Untested skills keep the
    status default.
    """
    if not passed and not failed:
        return MASTERY[status]
    if passed:
        earned = max(passed) / RECALL_LEVELS
    else:
        earned = 0.0 if status is NodeStatus.NEW else MISSED_EVERYTHING
    return max(earned, VERIFIED_FLOOR) if status is NodeStatus.VERIFIED else earned

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


RECALL_LEVEL_NAMES = {1: "name it", 2: "explain it", 3: "reason about it", 4: "design with it"}
MAX_RESOURCES = 3
RESOURCES_FILE = Path(__file__).resolve().parents[2] / "knowledge_data" / "learning_resources.yaml"


def _sentence(observation: str) -> str:
    """The scanner's first sentence, whole. The detail view has room `focus` does not."""
    return re.split(r"(?<=[.!?])\s", observation.strip())[0].rstrip(".")


def _missing(
    item: RoadmapItem,
    status: NodeStatus,
    related: list[str],
    gap: Finding | None,
    passed: set[int],
    failed: set[int],
    from_survey: bool = False,
) -> str:
    """What stands between the user and this skill, in plain sentences.

    Assembled from what is actually known -- whether they have written code
    with it, what the scanner found in that code, and how recall went -- so it
    never claims a weakness there is no evidence for. No model is called.
    """
    name = item.skill_name
    parts: list[str] = []

    if status is NodeStatus.NEW and from_survey:
        parts.append(f"{name} is on the path to this role, and you have not worked with it yet.")
    elif status is NodeStatus.NEW:
        parts.append(
            f"None of your analysed repositories use {name}, so there is nothing yet "
            "to show you can work with it."
        )
        if related:
            parts.append(
                f"It sits close to {_join(related)}, which you already use, "
                "so you are not starting from zero."
            )
    elif status is NodeStatus.FAMILIAR and from_survey:
        parts.append(
            f"You said you have used {name}, but nothing has checked it yet -- "
            "there is no code of yours here to look at."
        )
    elif status is NodeStatus.FAMILIAR:
        parts.append(
            f"Your code uses {name}, but nothing has yet checked that you understand it "
            "rather than having got it working."
        )
    else:
        parts.append(f"You have shown you understand {name}.")

    if gap is not None:
        opener = (
            "A problem in your own code points here"
            if status is NodeStatus.NEW
            else "The scanner found a weak spot"
        )
        parts.append(f"{opener}: {_sentence(gap.observation)} ({_reference(gap.evidence)}).")

    if passed and failed:
        parts.append(
            f"In recall you could {RECALL_LEVEL_NAMES[max(passed)]} but not yet "
            f"{RECALL_LEVEL_NAMES[min(failed)]}, so that step is the gap to close."
        )
    elif failed:
        parts.append(
            f"In recall you could not yet {RECALL_LEVEL_NAMES[min(failed)]}, "
            "so start from the fundamentals below."
        )
    elif passed and max(passed) < RECALL_LEVELS:
        parts.append(
            f"In recall you could {RECALL_LEVEL_NAMES[max(passed)]}; the next step is to "
            f"{RECALL_LEVEL_NAMES[max(passed) + 1]}."
        )
    elif passed:
        parts.append(
            "You cleared the hardest recall level, so what is left is depth through harder projects."
        )
    elif status is not NodeStatus.NEW:
        parts.append("Answer its recall questions to find out exactly where your understanding stops.")
    return " ".join(parts)


@functools.lru_cache(maxsize=1)
def _resource_table() -> dict[str, list[LearningResource]]:
    if not RESOURCES_FILE.is_file():
        return {}
    payload = yaml.safe_load(RESOURCES_FILE.read_text(encoding="utf-8")) or {}
    return {
        skill_id: [LearningResource.model_validate(row) for row in rows]
        for skill_id, rows in (payload.get("resources") or {}).items()
    }


def _resources(skill_id: str, taxonomy: SkillTaxonomy | None) -> list[LearningResource]:
    """The skill's own links, else its nearest ancestors', so nothing is left empty."""
    table = _resource_table()
    found: list[LearningResource] = []
    seen: set[str] = set()
    frontier, visited = [skill_id], {skill_id}
    while frontier and not found:
        parents: list[str] = []
        for current in frontier:
            for resource in table.get(current, []):
                if resource.url not in seen and len(found) < MAX_RESOURCES:
                    seen.add(resource.url)
                    found.append(resource)
            if taxonomy is not None:
                try:
                    parents.extend(p for p in taxonomy.parents(current) if p not in visited)
                except KeyError:
                    pass
        visited.update(parents)
        # The loop stops climbing once a level has links: a Python learner does
        # not need the generic "programming languages" list as well.
        frontier = parents
    return found


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
    recall: dict[str, tuple[set[int], set[int]]],
    from_survey: bool = False,
) -> ConceptSkill:
    related = _related_names(item.skill_id, known, taxonomy) if status is NodeStatus.NEW else []
    gap = gaps.get(item.skill_id)
    passed, failed = recall.get(item.skill_id, (set(), set()))
    mastery = recall_mastery(status, passed, failed)
    return ConceptSkill(
        skill_id=item.skill_id,
        skill_name=item.skill_name,
        status=status,
        focus=_focus(item, status, related, gap),
        mastery=mastery,
        proficiency=proficiency_of(mastery),
        proficiency_tested=bool(passed or failed),
        missing=_missing(item, status, related, gap, passed, failed, from_survey),
        resources=_resources(item.skill_id, taxonomy),
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
    recall: dict[str, tuple[set[int], set[int]]] | None = None,
    from_survey: bool = False,
) -> RoadmapGraph:
    """Regroup an already-built roadmap. `revise` is reframed, never replayed.

    The diagram is forward-looking, so a touched-but-unverified skill appears as
    FAMILIAR with a next step, rather than as a backlog item to go back and fix.

    `recall` maps skill_id -> (levels passed, levels failed) from the drill log.
    It moves the mastery bars only; which bucket a skill sits in stays decided
    by repository and verification evidence.
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
        node = _to_node(item, status, known, taxonomy, gaps, recall or {}, from_survey)
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
    concepts, stages = _staged(concepts)
    return RoadmapGraph(
        role=buckets.role,
        region=buckets.region,
        source="survey" if from_survey else "repos",
        concepts=concepts,
        stages=stages,
    )


# The order concepts are best learnt in. A tier holds what can be studied side by
# side; a later tier leans on the ones before it. This is a judgement about
# dependencies, written down once -- foundations, then the things you build,
# then the things that harden and ship them -- not something a model guesses.
LEARNING_TIERS: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "Learn first",
        "The foundations everything else leans on.",
        ("programming_languages", "programming_concepts", "version_control"),
    ),
    (
        "Then, in parallel",
        "Pick these up side by side; none of them blocks another.",
        ("backend", "frontend", "mobile", "data", "api_design"),
    ),
    (
        "Make it solid",
        "What turns working code into code you can trust and share.",
        ("testing", "security", "collaboration"),
    ),
    (
        "Ship and scale",
        "Running it for real, once there is something worth running.",
        ("devops", "cloud"),
    ),
]
LAST_TIER = ("Go further", "Skills that do not sit under one concept.")


def _staged(concepts: list[RoadmapConcept]) -> tuple[list[RoadmapConcept], list[RoadmapStage]]:
    """Number the concepts by learning tier, skipping tiers this roadmap has nothing in.

    Within a stage the concepts keep the order they arrived in, which is by
    priority, so the most useful of several parallel options is listed first.
    """
    tier_of = {cid: index for index, (_, _, ids) in enumerate(LEARNING_TIERS) for cid in ids}
    by_tier: dict[int, list[RoadmapConcept]] = {}
    for concept in concepts:
        by_tier.setdefault(tier_of.get(concept.concept_id, len(LEARNING_TIERS)), []).append(concept)

    staged: list[RoadmapConcept] = []
    stages: list[RoadmapStage] = []
    for number, tier in enumerate(sorted(by_tier), start=1):
        title, note = LEARNING_TIERS[tier][:2] if tier < len(LEARNING_TIERS) else LAST_TIER
        members = [concept.model_copy(update={"stage": number}) for concept in by_tier[tier]]
        staged.extend(members)
        stages.append(
            RoadmapStage(
                index=number,
                # Whatever comes first IS what to learn first, whichever tier it came from.
                title="Learn first" if number == 1 else title,
                note=note,
                concept_ids=[concept.concept_id for concept in members],
            )
        )
    return staged, stages


def tailor(graph: RoadmapGraph, hidden: set[str], keep_hidden: bool = False) -> RoadmapGraph:
    """Apply the user's own edits: skills they removed leave the roadmap.

    With `keep_hidden` they stay in the list, flagged, so the tailoring view can
    offer them back. Either way a concept's numbers describe only what is
    visible, and a concept with nothing visible left is dropped.
    """
    if not hidden:
        return graph
    concepts: list[RoadmapConcept] = []
    for concept in graph.concepts:
        skills = [
            skill.model_copy(update={"hidden": skill.skill_id in hidden}) for skill in concept.skills
        ]
        visible = [skill for skill in skills if not skill.hidden]
        if not visible and not keep_hidden:
            continue
        concepts.append(
            concept.model_copy(
                update={
                    "skills": skills if keep_hidden else visible,
                    "mastery": round(sum(s.mastery for s in visible) / len(visible), 4) if visible else 0.0,
                    "verified_count": sum(1 for s in visible if s.status is NodeStatus.VERIFIED),
                    "familiar_count": sum(1 for s in visible if s.status is NodeStatus.FAMILIAR),
                    "new_count": sum(1 for s in visible if s.status is NodeStatus.NEW),
                }
            )
        )
    concepts, stages = _staged(concepts)
    return graph.model_copy(update={"concepts": concepts, "stages": stages})


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
