# ARCHITECTURE

Reference spec: runtime flow, folder tree, and module responsibilities.

---

## 1. Runtime Flow

```
User connects GitHub
   ↓
User selects 3-5 repositories
   ↓
POST /repos/{id}/analyze  →  BackgroundTask
   ↓
[INGEST]
   clone (shallow)
   ↓ filter out vendor / generated / build / lock / unmodified forks
   ↓ parse with tree-sitter  → function list
   ↓ compute metrics         → complexity, call graph, test mapping
   ↓ read git log            → churn, hotspots, last_modified
   ↓ git blame (optional)    → author_ratio
   ↓
repo_map.json  — ALL functions, metadata + pointers only, no source code
   ↓
[ANALYZE]
   rank files by complexity × churn × size
   ↓ take top 20-30 files
   ↓ LLM scans each file           → raw findings
   ↓ validator drops any finding whose file:lines does not exist
   ↓
findings.json
   ↓
   scorer (rubric + metrics + findings)
   ↓
scores.json  →  skills enter "touched" tier
   ↓
[RECALL]
   selector filters repo_map:
     last_modified 1-3 months ago
     AND complexity high
     AND has_test = false
     AND author_ratio > 0.5
     AND prefer functions carrying high-severity findings
   ↓ 5 target functions
   ↓ load source at file:lines + called functions + creating commit diff (~3k tokens)
   ↓ generator produces 5 question types
   ↓ user answers
   ↓ grader scores (unit tests for debug type, rubric for open answers)
   ↓
skills promoted to "verified" tier
   ↓
[ROADMAP]
   verified skills − demand skills (market.json)
   ↓ rank by: job-ad frequency × proximity to what was already touched
   ↓
three buckets: Revise / Deepen / Learn New
   ↓
[SHARE]  exports "verified" tier only
```

Key invariants:

- `repo_map.json` holds **every** function, unfiltered. Filtering happens at query time, per purpose.
- It stores **pointers** (`file:lines:commit`), never source code. The clone is kept on disk for reading.
- Ingest is deterministic (tree-sitter + git). The LLM only enters at the ANALYZE stage.
- No RAG, no vector DB. Retrieval is structured filtering over `repo_map`.
- Roadmap must still produce output when market demand data is `None`.

---

## 2. Folder Tree

```
project/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── deps.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   ├── repo_map.py
│   │   │   ├── findings.py
│   │   │   ├── scores.py
│   │   │   ├── market.py
│   │   │   ├── recall.py
│   │   │   └── roadmap.py
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── repos.py
│   │   │   ├── analysis.py
│   │   │   ├── recall.py
│   │   │   ├── roadmap.py
│   │   │   └── code.py
│   │   │
│   │   ├── services/
│   │   │   ├── ingest/
│   │   │   │   ├── github.py
│   │   │   │   ├── clone.py
│   │   │   │   ├── filter.py
│   │   │   │   ├── parser.py
│   │   │   │   ├── metrics.py
│   │   │   │   ├── gitlog.py
│   │   │   │   └── blame.py
│   │   │   │
│   │   │   ├── analyze/
│   │   │   │   ├── ranker.py
│   │   │   │   ├── scanner.py
│   │   │   │   ├── validator.py
│   │   │   │   └── scorer.py
│   │   │   │
│   │   │   ├── recall/
│   │   │   │   ├── selector.py
│   │   │   │   ├── generator.py
│   │   │   │   ├── injector.py
│   │   │   │   └── grader.py
│   │   │   │
│   │   │   ├── roadmap/
│   │   │   │   ├── matcher.py
│   │   │   │   └── buckets.py
│   │   │   │
│   │   │   └── knowledge/
│   │   │       ├── base.py
│   │   │       ├── taxonomy/
│   │   │       │   ├── seeded.py
│   │   │       │   └── external.py
│   │   │       ├── demand/
│   │   │       │   ├── seeded.py
│   │   │       │   └── scraped.py
│   │   │       └── ladder/
│   │   │           ├── seeded.py
│   │   │           └── external.py
│   │   │
│   │   ├── models/
│   │   │   └── db.py
│   │   │
│   │   └── knowledge_data/
│   │       ├── dimensions.yaml
│   │       ├── questions.yaml
│   │       └── skills.yaml
│   │
│   ├── mock/
│   │   ├── repo_map.json
│   │   ├── findings.json
│   │   ├── scores.json
│   │   └── market.json
│   │
│   ├── cache/
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── lib/
│   │   ├── data.ts
│   │   └── types.ts
│   ├── components/
│   │   ├── CodeViewer.tsx
│   │   ├── DimensionCard.tsx
│   │   ├── EvidenceLink.tsx
│   │   ├── SourceBadge.tsx
│   │   └── QuestionCard.tsx
│   └── pages/
│       ├── connect.tsx
│       ├── profile.tsx
│       ├── recall.tsx
│       ├── roadmap.tsx
│       └── share/[id].tsx
│
└── data/
    ├── jobs_raw/
    └── market.json
```

---

## 3. Module Responsibilities

### app/

**main.py** — Instantiates FastAPI, mounts all routers, configures CORS, exposes OpenAPI at `/docs`.

**config.py** — pydantic-settings loading `.env`: GitHub OAuth credentials, LLM keys and model names, `TARGET_LANGUAGE`, the three knowledge-source switches, data directory, mock mode.

**deps.py** — Shared FastAPI dependencies: database session, current authenticated user, per-repo access check.

### schemas/ — Pydantic models, single source of truth for every contract

**common.py** — `Evidence` (file, lines tuple, commit) and `Provenance` (source kind, source name, confidence, sample size, collection date). Every claim in the system carries one or both.

**repo_map.py** — `FunctionNode` (name, file, line range, complexity, LOC, has_test, calls, times_modified, last_modified, created_commit, author_ratio) and `RepoMap` (repo, language, analyzed_at, total_files, excluded_files, functions list).

**findings.py** — `Finding` (id, dimension, severity, observation text, mandatory `Evidence`, confidence).

**scores.py** — `DimensionScore` (dimension, level 1-4, rationale, evidence list, metric_basis dict showing which numbers drove the level), `SkillStatus` (skill_id, tier touched|verified, evidence), and `Scores` wrapping both.

**market.py** — `MarketSkill` (skill_id, nullable frequency, role, region, provenance). Frequency is nullable by design so the roadmap degrades instead of crashing.

**recall.py** — `Question` (id, type, target function reference, prompt, attached code context), `Answer` (raw submission), `GradeResult` (passed, score, feedback, resulting tier change).

**roadmap.py** — `RoadmapItem` (skill, bucket, reason, evidence, market frequency, priority score) and `Buckets` grouping them.

### routers/ — thin, delegate to services

**auth.py** — GitHub OAuth start and callback, token storage, session issuing.

**repos.py** — Lists the user's repositories for selection; `POST /repos/{id}/analyze` queues the pipeline as a BackgroundTask and returns immediately; `GET /repos/{id}/status` for frontend polling.

**analysis.py** — Serves `scores.json` and `findings.json` for a repo.

**recall.py** — `GET /repos/{id}/questions` returns generated questions; `POST /answers` submits an answer, runs grading, returns the result.

**roadmap.py** — Returns the three buckets for a repo, filtered by target role.

**code.py** — `GET /repos/{id}/code?file=&start=&end=` reads a slice of source from the cached clone for CodeViewer. Must resolve to an absolute path and verify it stays inside `cache/<user>/<repo>/` — this endpoint takes client input and reads from disk.

### services/ingest/ — deterministic, no LLM

**github.py** — OAuth token exchange, lists repositories via the GitHub API, reads fork status and metadata.

**clone.py** — Shallow clone into `cache/<user>/<repo>/`, with depth and size limits; handles re-clone and cleanup.

**filter.py** — Decides which files are the user's own work. Excludes dependency directories (`node_modules`, `vendor`, `venv`), generated code and scaffolding, build output, lock and minified files, and forks with no original commits. Returns kept paths plus the exclusion list for explainability.

**parser.py** — Runs tree-sitter over kept files for the target language, extracting every function and class with its file and line range.

**metrics.py** — Walks the syntax trees to compute cyclomatic complexity, nesting depth, LOC, and the call graph; detects test files and maps tests back to the functions they cover; flags empty catch blocks, swallowed exceptions, hardcoded secrets.

**gitlog.py** — Reads commit history to derive per-file churn, hotspots, commit size and cadence, refactor-versus-append behaviour, and attaches `times_modified` and `last_modified` to each function.

**blame.py** — Optional. Runs `git blame` and computes `author_ratio`, the share of lines in each function written by this user. Defaults to 1.0 when skipped.

The ingest package assembles all of the above into a validated `RepoMap` and persists it.

### services/analyze/ — where the LLM enters

**ranker.py** — Orders files by `complexity × churn × size` and returns the top 20-30 as the scan set. Uses `repo_map` metadata only; no model calls.

**scanner.py** — Sends each ranked file to the LLM with a fixed prompt asking for qualitative design problems that metrics cannot capture (business logic in controllers, inconsistent modelling of one concept, misplaced abstractions, over-engineering, domain-naive naming). Requires every observation to cite `file` and `lines`. Returns raw `Finding` candidates.

**validator.py** — Rejects any finding whose cited file does not exist or whose line range falls outside the file. Dropped findings never reach storage or UI. This is the anti-hallucination gate.

**scorer.py** — Combines quantitative metrics from `repo_map` with validated findings, applies the rubric from `dimensions.yaml`, and emits a level 1-4 per dimension with rationale, evidence, and the metric basis behind each level. Also emits `SkillStatus` entries at the `touched` tier.

### services/recall/

**selector.py** — Queries `repo_map` for recall targets: last modified 1-3 months ago, high complexity, no test coverage, author_ratio above threshold, preferring functions that carry high-severity findings. Returns ranked targets with their assembled code context (the function, its callees, the creating commit diff).

**generator.py** — Produces the five question types from a target and its context: recall, justify-a-choice, transfer, debug, extend. Reference answers come from `questions.yaml`.

**injector.py** — For debug questions: takes a function with passing tests, asks the LLM to introduce a realistic bug, then runs the test suite to confirm the bug actually fails a test. Regenerates if it does not. Returns the broken code, the fix, and the grading tests.

**grader.py** — Grades submissions: unit tests for debug and extend types, rubric-based model grading for open answers. Promotes skills from `touched` to `verified` on transfer-level success or above, and pushes failed skills into the Revise bucket.

### services/roadmap/

**matcher.py** — Normalises the user's skills through the taxonomy provider and joins them against the demand provider by role and region.

**buckets.py** — Assigns each skill to Revise (touched, not verified), Deepen (touched and verified), or Learn New (never touched, in demand). Ranks items by job-ad frequency weighted by proximity to what the user has already touched. Must produce a sensible ordering when frequency is `None`.

### services/knowledge/ — swappable data sources

**base.py** — Protocol definitions for the three providers: `SkillTaxonomy` (normalise a raw string to a skill id, return parent skills), `DemandSource` (frequency of a skill for a role and region), `SkillLadder` (level definitions per skill, target levels per role and seniority).

**taxonomy/seeded.py** — Reads `skills.yaml`, a hand-curated set of 80-120 skills with aliases.
**taxonomy/external.py** — Placeholder for a standard taxonomy (Lightcast Open Skills, ESCO, O\*NET, or the Australian Skills Classification).

**demand/seeded.py** — Hand-written frequencies for demo continuity.
**demand/scraped.py** — Reads `market.json` produced from scraped job ads.

**ladder/seeded.py** — Reads `dimensions.yaml`, the team's own competency ladder.
**ladder/external.py** — Placeholder for a standard framework such as SFIA.

Which implementation loads is decided by `.env`, never by code changes.

### models/

**db.py** — SQLAlchemy tables: users, repos, analyses (repo_map / findings / scores as JSON), questions, answers, skill_status. Distinct from `schemas/`; do not share classes between the two.

### knowledge_data/ — edited by the research role, no code changes required

**dimensions.yaml** — Six dimensions × four levels with observable criteria, plus the mapping from metric thresholds to levels.
**questions.yaml** — Templates and reference answers for the five question types.
**skills.yaml** — The seeded skill taxonomy with aliases.

### frontend/

**lib/data.ts** — The single switch between mock JSON and the live API. No component knows which is in use.
**lib/types.ts** — Generated from the OpenAPI schema; never hand-written.

**components/CodeViewer.tsx** — Renders a source slice with the relevant lines highlighted. Every score, finding and recommendation in the app links into it. The most load-bearing component in the product.
**components/DimensionCard.tsx** — One dimension, its 1-4 level, rationale, and evidence links.
**components/EvidenceLink.tsx** — Turns an `Evidence` object into a clickable jump into CodeViewer.
**components/SourceBadge.tsx** — Renders `Provenance` so any market figure shows where it came from and on what sample size.
**components/QuestionCard.tsx** — Presents a question with its code context and the input mode appropriate to its type.

**pages/connect.tsx** — GitHub connect and repository selection.
**pages/profile.tsx** — Capability map across six dimensions, touched versus verified tiers, repository overview.
**pages/recall.tsx** — The revision loop; framed as revision, never as an exam. No failing grade, no ranking.
**pages/roadmap.tsx** — The three buckets, each item citing specific code and market evidence, filterable by target role.
**pages/share/[id].tsx** — Public profile exposing the verified tier only, with evidence links intact.

### data/

**jobs_raw/** — Collected job advertisements, unprocessed.
**market.json** — Skill frequency by role and region, with provenance attached.