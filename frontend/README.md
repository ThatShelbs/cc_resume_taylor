# Resume Taylor frontend

Vite + React + TypeScript + Tailwind, with Radix primitives. It talks to the Python
backend over a token-protected REST API and Server-Sent Events.

```text
src/
  main.tsx, App.tsx       providers, and the route table
  features/<screen>/      one folder per screen
    XPage.tsx             the page (what the router renders)
    components/           pieces only this screen uses
    hooks/                hooks only this screen uses
    *.ts                  small pure logic next to its test (e.g. draft.ts, stages.ts)
  components/
    ui/                   one file per Radix/shadcn-style building block (button, dialog, tabs, ...)
    layout/               the app shell, command menu, theme toggle, logo
    shared/               pieces used by several screens (PageHeader, Callout, TemplatePicker, ...)
  lib/
    api/                  client.ts (fetch + token), queries.ts (react-query hooks), sse.ts,
                          types.ts (response shapes), schema.d.ts (generated: npm run gen:api)
    routes.ts             every URL path in one place
    theme.tsx, utils.ts, useDebounced.ts
```

Imports use the `@/` alias for anything outside the current folder and `./` for siblings.
Tests sit next to the code as `*.test.ts[x]`.

```bash
npm install
npm run dev        # hot reload; pair with: python -m resume_taylor --dev
npm run check      # typecheck + lint + tests
npm run build      # writes dist/, which is committed so users don't need Node.js
```

After changing a Pydantic request model on the server, run `npm run gen:api`.
