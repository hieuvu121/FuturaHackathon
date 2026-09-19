"""Protocols for the three swappable knowledge sources. Owner: Track D.

Which implementation loads is decided by .env, never by code changes.
Consumers (scorer.py, matcher.py, buckets.py) depend on THESE protocols only --
never import a concrete provider directly.
"""

from typing import Protocol

from ...config import Settings
from ...schemas.market import MarketSkill


class SkillTaxonomy(Protocol):
    def normalise(self, raw: str) -> str | None:
        """'reactjs' -> 'react'. None when the string matches no known skill."""
        ...

    def parents(self, skill_id: str) -> list[str]:
        """'react' -> ['frontend', 'javascript']"""
        ...

    def name(self, skill_id: str) -> str: ...


class DemandSource(Protocol):
    def frequency(self, skill_id: str, role: str, region: str) -> MarketSkill | None:
        """None when this source has no data. Callers must degrade, not crash."""
        ...

    def top_skills(self, role: str, region: str, limit: int) -> list[MarketSkill]: ...


class SkillLadder(Protocol):
    def levels(self, dimension: str) -> dict[int, str]:
        """{1: 'criteria...', 2: ..., 3: ..., 4: ...}"""
        ...

    def dimensions(self) -> list[str]: ...

    def metric_thresholds(self, dimension: str) -> dict[str, dict[int, str]]: ...

    def target_level(self, dimension: str, role: str, seniority: str) -> int: ...


def get_taxonomy(settings: Settings) -> SkillTaxonomy:
    from .taxonomy import external, seeded

    return seeded.SeededTaxonomy(settings) if settings.taxonomy_source == "seeded" else external.ExternalTaxonomy(settings)


def _demand_impl(settings: Settings, name: str) -> DemandSource:
    from .demand import llm, scraped, seeded

    return {
        "seeded": seeded.SeededDemand,
        "scraped": scraped.ScrapedDemand,
        "llm": llm.LLMDemand,
    }[name](settings)


def get_demand(settings: Settings) -> DemandSource:
    """The demand source-of-truth is still undecided (plan.md §10).

    Until it is, the default is "chained": each source in settings.demand_chain
    is tried in order and the first to answer wins, so scraped data can land
    incrementally without anyone waiting on the decision.
    """
    from .demand.chained import ChainedDemand

    if settings.demand_source == "chained":
        return ChainedDemand(settings, [_demand_impl(settings, n) for n in settings.demand_chain])
    return _demand_impl(settings, settings.demand_source)


def get_ladder(settings: Settings) -> SkillLadder:
    from .ladder import external, seeded

    return seeded.SeededLadder(settings) if settings.ladder_source == "seeded" else external.ExternalLadder(settings)
