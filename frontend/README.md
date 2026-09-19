# Retrace frontend

The frontend is a Next.js Pages Router application that runs entirely from mock JSON until the backend API is available.

## Run locally

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The root route redirects to `/connect`.

Useful checks:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

## Switch between mock and live data

`lib/data.ts` is the only mock/live boundary. Components never import mock files or call `fetch` directly.

Mock mode is the default:

```env
NEXT_PUBLIC_USE_MOCK=true
```

It loads the canonical JSON from `../backend/mock/`.

To use the backend:

```env
NEXT_PUBLIC_USE_MOCK=false
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart the development server after changing environment variables.

## Regenerate API types

`lib/types.ts` temporarily mirrors these backend schemas:

- `Evidence` and `Provenance`
- `FunctionNode` and `RepoMap`
- `Finding`
- `DimensionScore`, `SkillStatus`, and `Scores`
- `MarketSkill`
- `Question`, `Answer`, and `GradeResult`
- `RoadmapItem` and `Buckets`

When the backend OpenAPI endpoint is running, replace the temporary declarations:

```bash
npm run gen:types
```

After generation, update imports in `lib/data.ts` to the generated schema names and run the checks above.
