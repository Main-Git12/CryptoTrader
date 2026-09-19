# CryptoTrader dashboard

React + Vite + TypeScript. Read-only view over `/server`'s API: top
tickers by mention volume, and a per-ticker mention-volume + sentiment
trend over the last 24 hours. Renders nothing on its own — every number
on screen came from the API.

Colors follow the [dataviz skill](https://github.com/anthropics)'s
validated default palette (`src/theme.css`, `src/palette.ts`) — categorical
hues in fixed order, a blue/red diverging pair for sentiment polarity,
light/dark steps both independently validated (`node scripts/validate_palette.js`
in the skill, not eyeballed). Every chart ships a table view alongside it,
since three of the eight categorical hues (aqua, yellow, magenta) sit
below 3:1 contrast on the light surface — direct labels/tables are the
mitigation, not a "nice to have."

## Structure

```
src/
  App.tsx, main.tsx           Entry points
  theme.css                    Palette as CSS custom properties (light + prefers-color-scheme: dark)
  palette.ts                   Same palette as literal hex, for chart libraries that can't consume CSS vars
  hooks/useChartPalette.ts     Picks light/dark palette based on the OS preference
  types.ts                     TickerSummary/TimeSeriesPoint, mirroring the server
  lib/api.ts                    Typed fetch client
  components/                  (every component below has a matching *.test.tsx)
    Dashboard.tsx                Fetches and lays out the two sections below
    Disclaimer.tsx               "Informational only, not financial advice" banner
    TopTickersChart.tsx           Bar chart + table
    SentimentTrendChart.tsx       Ticker selector, mention-volume bars, sentiment line (diverging-colored points), table
```

## Local development

```bash
cp .env.example .env    # point VITE_API_BASE_URL at the server (npm run serve there)
npm install
npm run dev
```

## Checks

```bash
npm run typecheck   # tsc --noEmit
npm run lint          # eslint src
npm test               # vitest run (jsdom; ResizeObserver + matchMedia are polyfilled in src/test/setup.ts since jsdom has neither)
npm run build           # typecheck + production build
```

## Known issues

- Same `vitest`/`vite` dev-server-only advisories as the sibling
  YouEnjoyMyFamily repo (moderate/high, need a coordinated Vite 6+ bump);
  not fixed here for the same reason — see that repo's frontend README
  for the detailed writeup, it applies verbatim.
- `recharts` 2.x is EOL upstream (3.x is current); stayed on 2.x since it
  works and a major bump wasn't validated as part of this change.
- The production bundle is ~535KB minified (mostly `recharts`) — fine for
  now, but code-splitting is worth doing before this grows much further.
