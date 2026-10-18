# Sentry for the desktop app (from Eric)

Project: `kumite-app` in Sentry org `university-of-maryland-ma`.

## 1. Get the DSN (never commit it)

If you're a member of the Sentry org and your Claude Code has the Sentry MCP, ask your agent to look it up: `find_dsns` for org `university-of-maryland-ma`, project `kumite-app`. Otherwise ask Eric. Keep it in your env config, not in the repo.

## 2. Install and initialize

`npm install @sentry/electron`

Main process:

```ts
import * as Sentry from "@sentry/electron/main";
Sentry.init({ dsn: process.env.SENTRY_DSN, environment: process.env.SENTRY_ENVIRONMENT ?? "development" });
```

Each renderer (overlay and main window):

```ts
import * as Sentry from "@sentry/electron/renderer";
Sentry.init({});
```

## 3. Source maps (hours 14–16)

Built apps are minified, so Sentry stack traces are unreadable without source maps. When the build works, run the `sentry-fix-stack-traces` skill in Claude Code (it wires `@sentry/vite-plugin` into the build), or ask Eric.

## 4. At the demo

The environment should be `demo` on the demo laptop.

`/team-status` closes these items automatically once `@sentry/electron`, a source-map upload (`@sentry/vite-plugin`, `sentryVitePlugin` or `sentry-cli`) and `SENTRY_ENVIRONMENT` appear in `app/` on any branch.
