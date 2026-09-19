"""Every roadmap skill explains what is missing and points somewhere to learn it."""

from urllib.parse import urlparse

import yaml

from app.config import Settings
from app.schemas.common import Evidence
from app.schemas.findings import Finding
from app.schemas.roadmap import Bucket, Buckets, NodeStatus, RoadmapItem
from app.services.knowledge import get_taxonomy
from app.services.roadmap.concepts import RESOURCES_FILE, _resources, graph_from_buckets

SETTINGS = Settings()
KINDS = {"docs", "guide", "course", "practice", "reference"}


def _item(skill_id: str, name: str, bucket: Bucket) -> RoadmapItem:
    return RoadmapItem(skill_id=skill_id, skill_name=name, bucket=bucket, reason="", priority=0.5)


def _node(graph, skill_id):
    return next(s for c in graph.concepts for s in c.skills if s.skill_id == skill_id)


def test_resource_file_is_well_formed_and_only_names_real_skills():
    taxonomy = get_taxonomy(SETTINGS)
    table = yaml.safe_load(RESOURCES_FILE.read_text(encoding="utf-8"))["resources"]

    for skill_id, rows in table.items():
        assert taxonomy.normalise(skill_id) == skill_id, skill_id
        assert rows, skill_id
        for row in rows:
            assert row["title"].strip(), skill_id
            assert row["kind"] in KINDS, (skill_id, row["kind"])
            url = urlparse(row["url"])
            assert url.scheme == "https" and url.netloc, row["url"]


def test_every_skill_in_the_taxonomy_ends_up_with_resources():
    taxonomy = get_taxonomy(SETTINGS)
    skills = yaml.safe_load(
        (SETTINGS.knowledge_data_dir / "skills.yaml").read_text(encoding="utf-8")
    )

    for row in skills["skills"]:
        found = _resources(row["id"], taxonomy)
        assert 1 <= len(found) <= 3, row["id"]
        assert len({r.url for r in found}) == len(found), row["id"]


def test_a_skill_with_its_own_links_does_not_inherit_the_generic_ones():
    urls = [r.url for r in _resources("python", get_taxonomy(SETTINGS))]

    assert "https://docs.python.org/3/tutorial/" in urls
    assert "https://roadmap.sh/roadmaps" not in urls


def test_missing_text_is_built_from_evidence_findings_and_recall():
    taxonomy = get_taxonomy(SETTINGS)
    buckets = Buckets(
        role="software_engineer",
        region="AU",
        deepen=[_item("python", "Python", Bucket.DEEPEN)],
        revise=[_item("testing_unit", "Unit Testing", Bucket.REVISE)],
        learn_new=[_item("docker", "Docker", Bucket.LEARN_NEW)],
    )
    finding = Finding(
        id="f1",
        dimension="testing",
        severity="high",
        observation="Tests assert internal progress labels. They break on every refactor.",
        evidence=Evidence(file="tests/test_pipeline.py", lines=(10, 20)),
        confidence=0.9,
    )

    graph = graph_from_buckets(
        buckets, taxonomy, [finding], {"testing_unit": ({1}, {2}), "python": ({3, 4}, set())}
    )

    familiar = _node(graph, "testing_unit")
    assert familiar.status is NodeStatus.FAMILIAR
    assert "Your code uses Unit Testing" in familiar.missing
    assert "Tests assert internal progress labels (test_pipeline.py:10)" in familiar.missing
    assert "could name it but not yet explain it" in familiar.missing
    assert familiar.resources

    new = _node(graph, "docker")
    assert "None of your analysed repositories use Docker" in new.missing
    assert "recall" not in new.missing
    assert any("docker.com" in r.url for r in new.resources)

    assert "cleared the hardest recall level" in _node(graph, "python").missing


def test_untested_familiar_skill_is_pointed_at_recall():
    graph = graph_from_buckets(
        Buckets(role="r", region="AU", revise=[_item("git", "Git", Bucket.REVISE)]),
        get_taxonomy(SETTINGS),
    )

    assert "Answer its recall questions" in _node(graph, "git").missing
