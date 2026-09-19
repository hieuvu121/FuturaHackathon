# PLAN

Backend execution plan for the architecture in [OVERALL.md](./OVERALL.md).
Three backend tracks, five phases, conflict-free parallel branches.

> **Current scope:** backend only. The frontend is being developed independently.
> Treat `frontend/` as read-only and do not include UI work in these phases.

---

## 0. Read this first

**The one rule that makes parallel work possible:** Phase 0 created every backend
file in the OVERALL.md tree as a working stub. Nobody creates a shared file, and
nobody edits `main.py`. You only fill in bodies of files your track owns.

Three things are already true in this repo:

- `backend/app/schemas/` is **fully written**. It is the contract between all three
  tracks. Treat it as frozen — see [§6 Changing a contract](#6-changing-a-contract).
- `MOCK_MODE=true` makes every endpoint serve `backend/mock/*.json`. The whole app
  runs end to end, today, with no GitHub token and no API key.

Run it:

```bash
# backend
cd backend && cp .env.example .env
./.venv/bin/uvicorn app.main:app --reload        # http://localhost:8000/docs
```

Verify before starting work:

```bash
cd backend && ./.venv/bin/python -m pytest tests/ -q
```

---

## 1. Tracks and ownership

Each person owns a set of paths **exclusively**. If you need a change in someone
else's path, ask them — do not edit it. This is what keeps merges clean.

| Track | Person | Owns (exclusive write) | Never touches |
|---|---|---|---|
| **A — Ingest & Platform** | Dev 1 | `services/ingest/*`, `routers/{auth,repos,code}.py`, `models/db.py`, `deps.py` | `services/analyze`, `frontend/` |
| **B — Analyze & Recall** | Dev 2 | `services/analyze/*`, `services/recall/*`, `routers/{analysis,recall}.py` | `services/ingest`, `frontend/` |
| **D — Knowledge & Roadmap** | Dev 4 | `services/knowledge/*`, `services/roadmap/*`, `knowledge_data/*.yaml`, `backend/mock/*`, `data/`, `routers/roadmap.py`, `mock_store.py` | `services/ingest`, `services/analyze` |

**Shared, frozen, changed only by the process in §6:** `app/schemas/*`, `app/main.py`,
`app/config.py`.

Track D is the load-bearing one on day one: the mock fixtures *are* the demo until
Phase 2 lands, and the YAML files are the rubric everything else scores against.

---

## 2. Phases

Timings assume a ~2-day hackathon. Compress or stretch proportionally.

### Phase 0 — Foundation & contracts ✅ DONE

Already committed. Scaffolded backend tree, complete `schemas/`, all six routers
mounted and serving mock JSON, service stubs with typed signatures, SQLAlchemy
models, three YAML knowledge files, seven mock fixtures, and 17 passing tests.

**Exit criteria (met):** `pytest` green, `/health` returns `mock_mode: true`, and
every backend journey endpoint serves schema-valid mock JSON.

---

### Phase 1 — Mock-complete backend slice · ~4h · three tracks in parallel

**Goal: a demo-able backend API by end of day one.** Everything runs on mock
data. If Phases 2-3 slip, the API remains coherent and presentable through
`/docs`.

| Track | Deliverable |
|---|---|
| **A** | Real GitHub OAuth round trip + real repo listing. `clone.py` shallow-clones to `cache/<user>/<repo>/`. `filter.py` returns kept + excluded lists. `code.py` reads real slices — **write the `_safe_path` traversal test first.** |
| **B** | `validator.py` complete **with tests** — this is the credibility gate, build it before the scanner. Then `ranker.py` (pure metrics, no LLM). |
| **D** | Fill `skills.yaml` to 80–120 skills. Finish `dimensions.yaml` thresholds. Implement `taxonomy/seeded.py` and `demand/seeded.py` against the protocols. |

**Exit criteria:** all backend mock endpoints describe the complete journey,
contracts validate, real Phase 1 services have focused tests, and `pytest` is green.

---

### Phase 2 — Real implementations behind the same contracts · ~6h

Each track swaps its mock for the real thing. Because the contracts do not move,
tracks that are still on mock keep working.

| Track | Deliverable |
|---|---|
| **A** | `parser.py` (tree-sitter → `FunctionNode`), `metrics.py` (complexity, nesting, call graph, test mapping, smell flags), `gitlog.py` (churn, `times_modified`, `last_modified`, `created_commit`), `blame.py` (optional, defaults 1.0). `ingest/__init__.py` assembles a validated `RepoMap`. |
| **B** | `scanner.py` uses the provider selected by `LLM_PROVIDER` (`openai` default, `anthropic` fallback). OpenAI uses typed Structured Outputs; both providers produce raw `Finding` candidates that must pass through `validator.py`. `scorer.py` combines metrics + validated findings + `dimensions.yaml` → levels with `metric_basis` populated. |
| **D** | Build the roadmap evidence-first. `matcher.py` normalises real `SkillStatus` entries. `buckets.py` produces **Revise** and **Deepen** from repository evidence without depending on market data, then adds **Learn New** only from an available demand source. Implement and test the **`frequency is None` path** so unknown demand ranks by skill proximity rather than being dropped. Use seeded demand as the temporary source; keep Learn New explicitly provisional until a validated market source exists. Collect job ads into `data/jobs_raw/` independently so research cannot block the roadmap mechanics. |

**Exit criteria:** `MOCK_MODE=false` produces a real `repo_map.json`, real
validated `findings.json`, and a roadmap for one live GitHub repository.
Revise/Deepen items must cite repository evidence. Learn New may be empty or
seeded/provisional, must preserve provenance, and must still rank safely when
market frequency is unknown.

**Verified provider checkpoint (2026-09-20):** the authenticated live flow cloned
`hieuvu121/ragPullRequest`, ranked its Python files, scanned `indexer/tasks.py`
with `LLM_PROVIDER=openai` / `SCANNER_MODEL=gpt-5`, and returned 10 typed findings.
All 10 cited real file ranges and passed `validator.py`; none were dropped. The
real `RepoMap` assembly is also wired and verified against that repository (42
kept Python files and 106 definitions). Phase 2's persistence exit criterion now
depends on the storage/API branch. The non-persistent orchestration was verified
live with a one-file scan: 14 findings from `indexer/tasks.py` passed validation,
none were dropped, and the scorer returned six dimensions and seven touched
skills. The complete Phase 2 flow was then verified with another live scan and
an isolated database: stage `done`, progress 100, 106 functions, eight validated
findings, six dimensions, and seven persisted skill statuses. The HTTP analyze
trigger remains in Phase 3 because it runs this work as a background task.

---

### Phase 3 — Recall loop & integration · ~5h

| Track | Deliverable |
|---|---|
| **A** | Pipeline wired as a BackgroundTask with real stage/progress in the `analyses` table. Clone cleanup and size limits enforced. |
| **B** | `selector.py` (the five-condition filter), `generator.py` (five question types, ~3k-token context), `injector.py` (**bug injection verified by actually running the test suite**), `grader.py` (unit tests for debug/extend, rubric for open answers, touched→verified promotion). |
| **D** | Feed grader promotions back into the evidence-first roadmap so failed/touched skills appear in Revise and newly verified skills move to Deepen. Integrate a validated market-demand provider only if one is ready; every returned market figure retains its `Provenance`. |

**Exit criteria:** API calls connect a real repo → return scores → accept five
answers → promote a skill to verified → return it in a new roadmap bucket.

**Background-analysis checkpoint (2026-09-20):** the real worker completed an
isolated run against `hieuvu121/ragPullRequest` with stage `done`, progress 100,
106 functions, 11 validated findings, no stored error, and the successful clone
retained for code slices and recall. Unit coverage also verifies progress stages,
duplicate-run rejection, failure persistence, and failed-clone cleanup.

**Recall-selection checkpoint (2026-09-20):** the five-condition selector and
five deterministic question types are implemented. Context safely includes the
target, known callees, and available creating-commit diff, capped near 3k tokens.
The ownership-checked real endpoint persists its generated `QuestionRow` records.

**Recall-verification checkpoint (2026-09-20):** bug injection runs only against
an isolated repository copy after a passing baseline suite, clears bytecode
caches between attempts, and accepts a candidate only when the real suite fails.
Debug/extend submissions are test-graded; open answers are rubric-graded. A live
OpenAI transfer grade returned a typed passing result and a `python` promotion.
Answer results and touched-to-verified evidence are persisted transactionally.

**Roadmap-promotion checkpoint (2026-09-20):** the real roadmap endpoint builds
from persisted per-repository skill tiers. A passing transfer answer updates the
same skill from Revise to Deepen immediately; failed or unverified skills remain
in Revise, while Learn New retains its demand provenance and nullable frequency.

---

### Phase 4 — Demo prep & buffer · ~3h

Not optional. Reserve it.

- Pick and pre-warm **one** demo repository. Cache its analysis. Never demo a cold clone.
- `MOCK_MODE=true` as the fallback path, rehearsed. If the API key dies mid-demo, flip one env var.
- Keep both provider paths configured where possible. `LLM_PROVIDER=openai` is the
  verified default; `LLM_PROVIDER=anthropic` remains a code-compatible fallback.
- Seed one fully-verified profile so public API responses have realistic content.
- Cross-track backend bug bash. Everyone runs the complete API flow.
- README with setup steps.

---

## 3. Branches

One branch per deliverable, not per phase. Small branches merge cleanly; week-long
branches do not.

```
main                          always green, always demo-able
 ├─ feat/a1-github-auth       Track A, Phase 1
 ├─ feat/a2-clone-filter      Track A, Phase 1
 ├─ feat/a3-parser-metrics    Track A, Phase 2
 ├─ feat/a4-gitlog-blame      Track A, Phase 2
 ├─ feat/a5-repo-map-assembly Track A, Phase 2
 ├─ feat/phase2-analysis-pipeline Tracks A/B, Phase 2
 ├─ feat/phase2-persistence-api Track A, Phase 2
 ├─ feat/a6-background-analysis Track A, Phase 3
 │
 ├─ feat/b1-validator         Track B, Phase 1  ← build this first
 ├─ feat/b2-ranker            Track B, Phase 1
 ├─ feat/b3-scanner           Track B, Phase 2
 ├─ feat/b4-scorer            Track B, Phase 2
 ├─ feat/openai-scanner-provider  Track B, Phase 2, provider selection
 ├─ feat/b5-selector-generator Track B, Phase 3
 ├─ feat/b6-injector-grader   Track B, Phase 3
 │
 ├─ feat/d1-skills-yaml       Track D, Phase 1
 ├─ feat/d2-knowledge-seeded  Track D, Phase 1
 ├─ feat/d3-roadmap-buckets   Track D, Phase 2
 ├─ feat/d4-roadmap-promotion Track D, Phase 3
 ├─ feat/phase3-integration   Tracks A/B/D, Phase 3
 ├─ feat/demand-llm           optional; provisional demand fallback
 └─ feat/market-scraped       optional; validated only if ads get collected
```

Naming: `feat/<track-letter><number>-<short-slug>`. The letter tells everyone whose
branch it is at a glance.

Workflow:

```bash
git checkout main && git pull
git checkout -b feat/b1-validator
# ... work, committing as you go ...
cd backend && ./.venv/bin/python -m pytest tests/ -q      # must be green
git push -u origin feat/b1-validator
gh pr create --fill
```

Rules:

1. **Never commit to `main` directly.** `main` must always run the demo.
2. **Rebase on `main` before opening a PR**, not merge. Keeps history readable —
   which matters here, since this project scores people on exactly that.
3. **One reviewer, from another track.** Fifteen minutes, not an hour. The point is
   that a second person knows the code exists.
4. **Merge as soon as it is green.** A branch open longer than half a day is a
   merge conflict forming.
5. **If `pytest` is red on `main`, that is a stop-the-line event.** Fix before continuing.

---

## 4. Dependency order — who blocks whom

```
Phase 0 (schemas) ──► everyone            [done]

Track A parser+metrics ──► Track B scorer        (needs real complexity numbers)
Track A parser+metrics ──► Track B selector      (needs has_test, last_modified)
Track A clone          ──► Track B scanner       (needs files on disk to scan)
Track D skills.yaml    ──► Track B scorer        (needs skill ids to emit)
Track D dimensions.yaml──► Track B scorer        (needs the rubric)
Track B scorer         ──► Track D Revise/Deepen (needs real SkillStatus)
Demand source          ──► Track D Learn New     (optional; never blocks evidence buckets)
```

**Nobody is ever actually blocked**, because the mock fixtures satisfy every one of
these dependencies. If you are waiting on another track, you are meant to be
working against `backend/mock/*.json`. That is what it is for.

Track D should land `skills.yaml` and `dimensions.yaml` early in Phase 1 — two
other tracks read them.

---

## 5. Invariants — do not break these

From OVERALL.md §1. If a PR violates one, it does not merge.

1. `repo_map.json` holds **every** function, unfiltered. Filtering happens at query
   time, per purpose. Do not pre-filter at ingest.
2. `repo_map` stores **pointers** (`file:lines:commit`), never source code. The
   clone on disk is the source of truth for reading.
3. Ingest is **deterministic**. tree-sitter and git only. The LLM enters at ANALYZE
   and not one stage earlier.
4. **No RAG, no vector DB.** Retrieval is structured filtering over `repo_map`.
5. The roadmap **must still produce output** when market demand is `None`. There is
   a null frequency in `mock/market.json` specifically to keep you honest.
6. Every `Finding` carries `Evidence` that resolves. `validator.py` drops the rest,
   and dropped findings never reach storage or API responses.
7. Any public profile/export API returns the **verified tier only**.
8. Recall API feedback is **revision, never an exam**. No failing grade, no ranking.
9. `schemas/` and `models/db.py` do **not** share classes. API contract and storage
    are separate on purpose.

---

## 6. Changing a contract

`schemas/` is frozen because three backend tracks read it. When it genuinely must change:

1. Say so in the team channel **before** editing. Name the field and why.
2. Make the change on a branch named `contract/<what>`.
3. Update `backend/mock/*.json` in the same PR, or `tests/test_contracts.py` fails
   — that test exists to catch exactly this.
4. Every track pulls `main` immediately after it merges.

Additive changes (a new optional field) are cheap. Renames and type changes are
expensive. Prefer additive.

---

## 7. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM invents file paths and line numbers | **High** | `validator.py`, built in Phase 1 before the scanner, with tests. This is why it is Track B's first branch. |
| `injector.py` produces bugs no test catches | High | Verify by running the suite; regenerate up to `max_attempts`. If it stays flaky, cut debug/extend questions and ship three question types. |
| Live clone + analysis too slow to demo | Medium | Pre-warm one repo in Phase 4. Cache the analysis. Never clone cold on stage. |
| tree-sitter query complexity eats a day | Medium | Python only for the MVP (`TARGET_LANGUAGE=python`). Do not add a second language before Phase 4. |
| Market data never materialises | Medium | Ship evidence-backed Revise/Deepen. Learn New stays empty or explicitly seeded/provisional. Frequency is nullable by design; the roadmap ranks by proximity instead of crashing. |
| Demand source-of-truth decision drags on | **High** | Keep demand optional: build Revise/Deepen first and use seeded or empty Learn New until a provider is validated. Do not enable the incomplete chain. Forcing date in §10. |
| Selected LLM provider is exhausted or rate-limited mid-demo | Low | Switch `LLM_PROVIDER` when the alternate provider is funded; otherwise use the rehearsed `MOCK_MODE=true` fallback. |
| Merge conflicts stall the team | Low | Exclusive path ownership (§1) plus everything pre-created in Phase 0. |

---

## 8. Cut list — in this order, if time runs out

1. `blame.py` / `author_ratio` — already defaults to 1.0.
2. `demand/scraped.py` + job-ad collection — `seeded.py` covers the demo.
3. `extend` question type — keep recall, justify, transfer, debug.
4. `injector.py` and the `debug` type — keep the three rubric-graded types.
5. Multi-repo analysis — demo one repository well.

**Never cut:** `validator.py`, evidence-bearing response contracts, or verified-tier
filtering on any public export. Those are the product's credibility boundary.

---

## 9. Deviations from OVERALL.md

Small, deliberate, listed here so nobody thinks they are accidents.

- The scanner is no longer coupled only to Claude. `LLM_PROVIDER=openai` is the
  default because the live OpenAI Structured Outputs flow is verified; Anthropic
  remains selectable without changing the `scan_file` or `Finding` contracts.
- Provider response schemas are adapters, not public contracts. OpenAI emits a
  JSON-compatible two-item line list, which is converted back to the frozen
  `Evidence.lines: tuple[int, int]` contract before `validator.py` runs.

| Addition | Why |
|---|---|
| `backend/app/mock_store.py` | All six routers needed the same three-line JSON loader. Owned by Track D with the fixtures. |
| `backend/mock/{repos,questions,roadmap}.json` | OVERALL.md names four fixtures; the routers need three more to serve the full journey in mock mode. |
| `backend/tests/test_contracts.py` | Guards the fixtures against schema drift, which is the main way mock mode rots. |
| `demand/llm.py`, `demand/chained.py`, `SourceKind.ESTIMATED` | OVERALL.md offers seeded-or-scraped only. The demand decision is still open, so a third provider and a fallback chain keep it open without blocking anyone. See §10. |

---

## 10. Open decisions

Decisions nobody has made yet. Each one must have a safe implementation path so
no track is blocked while it stays open. Do not describe a configured provider
as running until its methods and integration tests are complete.

### 10.1 What is the roadmap's source of truth for market demand? — OPEN

The candidates, weakest to strongest:

| Source | Fidelity | Cost | Provenance shown to the user |
|---|---|---|---|
| `seeded` — hand-written table | Low | Minutes | `seeded`, confidence 0.6, n=400 |
| `llm` — model estimate | Low–medium | ~1h to build | `estimated`, confidence ≤ 0.4, **n=null** |
| `scraped` — real job ads in `data/jobs_raw/` | High | ~half a day, plus collection | `scraped`, confidence high, real n |
| `external` — Lightcast / ESCO / ASC | Highest | Access + integration; likely post-hackathon | `external` |

**Current implementation status:** evidence-first matching and bucket construction
work with seeded demand, and `DEMAND_SOURCE=seeded` is the safe default.
`ScrapedDemand`, `LLMDemand`, and `ChainedDemand.top_skills()` are still stubs, so
the chained provider remains opt-in and is not yet a safe runtime fallback.

**Immediate Phase 2 rule:** use `DEMAND_SOURCE=seeded` when exercising Learn New,
or return no Learn New items. Revise and Deepen must continue working either way.
Do not use an LLM estimate or a hand-written frequency as validated market data.

**Target after provider implementation:**
`DEMAND_SOURCE=chained`, `DEMAND_CHAIN=["scraped","llm","seeded"]`.

Once implemented, the chain takes the first source that answers for each skill. So a scraped
figure is used where the ads cover that skill; an LLM estimate fills gaps; the
seeded table is the floor. **Every row keeps the provenance of whichever source
actually answered**, so a mixed roadmap still shows the user, per item, which
numbers were measured and which were guessed. The API preserves that difference
in each row's `Provenance`.

Why this is safe to leave open:

- `buckets.py` depends on the `DemandSource` protocol, never on a concrete provider.
- Revise and Deepen depend on repository evidence, not market demand.
- Deciding later changes provider configuration, not roadmap contracts or stored
  skill statuses.
- `frequency` is nullable and invariant #5 requires graceful degradation, so even
  "all demand sources fail" remains a supported state.

Required Phase 2 tests (implemented in `tests/test_roadmap_services.py`):

1. touched but unverified → Revise;
2. verified → Deepen;
3. never touched + available demand → Learn New;
4. `frequency=None` still produces deterministic proximity ordering;
5. unavailable demand produces valid Revise/Deepen output without Learn New.

The service tests exercise real bucket construction, seeded `top_skills()`, alias
normalisation, evidence merging, provenance retention, unavailable demand, and
null-frequency proximity ordering. The generic chained `top_skills()` fallback
still belongs to the later chained-provider implementation.

Constraint on the LLM option: an estimate is **never** presented as a measurement.
`llm.py` clamps confidence to 0.4, sets `sample_size=None`, and stamps
`SourceKind.ESTIMATED`. It returns `None` rather than guessing when it has no basis.
A product whose entire argument is "claims must carry evidence" cannot ship an
unlabelled guess in its own roadmap.

- **Owner:** Track D.
- **Forcing date:** end of Phase 2. If no validated source exists, ship
  evidence-backed Revise/Deepen plus empty or visibly seeded/provisional Learn New.
  Do not ship the incomplete chained provider as though it were validated.

### 10.2 Skill taxonomy: seeded or standard? — OPEN

`TAXONOMY_SOURCE=seeded` is running. `taxonomy/external.py` is a stub for
Lightcast Open Skills / ESCO / O\*NET / the Australian Skills Classification.
Blocked on access, and 80–120 seeded skills is enough for a demo.
**Decide post-hackathon.** No forcing date.

### 10.3 Competency ladder: the team's own or SFIA? — OPEN

`LADDER_SOURCE=seeded` is running against `dimensions.yaml`. A standard framework
would carry more external weight but constrains the six dimensions to someone
else's model. **Decide post-hackathon.** No forcing date.

### How to add a decision here

Name the question, list the candidates with their real costs, state the default
that is already running, and set a forcing date or explicitly say there is none.
A decision with no running default is a blocker, and belongs in the risk register
(§7) instead.
