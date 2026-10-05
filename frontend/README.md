# Front end

React 19 + TypeScript (strict) + Vite. The complaint handler's screens: the queue, a case with its
deadlines, the AI's suggestions and the decisions on them, and a form to log a complaint.

## Develop

```bash
npm install
npm run dev        # http://127.0.0.1:5173, forwards /api to the backend on 127.0.0.1:8000
```

The backend can run in Docker (`docker compose up` in the repository root) or without it:
`python -m app.devtools.local_stack` in `backend/` (see the main README).

## Check

```bash
npm run lint       # oxlint
npm run typecheck  # tsc, strict
npm test           # vitest + Testing Library, against a fake API
npm run build
```

## The API contract

`openapi.json` is exported from the backend (`python -m app.export_openapi ../frontend/openapi.json`)
and `npm run gen:api` turns it into `src/api/schema.d.ts`. Every call in `src/api` is typed from it:
if the backend renames a field, the front end stops compiling. CI checks both files are up to date.

## Layout

```
src/
  api/      typed client (auth header, error messages), query hooks, query cache settings
  auth/     token in sessionStorage, sign in, route guard
  cases/    queue, case detail, new complaint, and their components
  shared/   labels, UK date formatting, layout
  test/     fake API, test data, render helper
```

## Security

- All complaint and AI text is rendered as text by React, never as HTML.
- The token lives in `sessionStorage` (gone when the tab closes) and is only kept once the API has
  accepted it. Any `401` signs the user out and clears every cached case.
- In Docker, nginx serves the app with a strict Content-Security-Policy and forwards `/api`, so the
  browser talks to one origin and the API needs no CORS settings.
