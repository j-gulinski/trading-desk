# Styling — SCSS architecture, tokens, layout mechanics

No CSS framework, no CSS-in-JS, no utility classes. Plain SCSS with a token layer, one partial
per component, and a handful of modern CSS features doing work that would otherwise need
JavaScript.

## 1. The system in five steps

```text
1. tokens      CSS custom properties on :root — colors, spacing, sizes, fonts
2. reset       box-sizing, body, scrollbars — a dozen lines, not a library
3. layout      the app shell: sidebar + content column
4. components  one partial per component, forwarded from a barrel
5. responsive  container queries first, media queries only for the shell
```

```scss
// main.scss — the whole entry point
@use "variables";   // 1
@use "layout";      // 3
@use "components";  // 4  (a barrel of @forward)
```

`_components.scss` is a barrel: 23 `@forward "components/<name>"` lines, one per component
partial. Adding a component means adding a file and one line — and the barrel doubles as an
inventory of what the app is made of.

## 2. Tokens — the design system in 48 lines

```scss
:root {
  --bg-app: #0b0d12;      --bg-panel: #12161e;     --bg-elevated: #151a23;
  --border: #252c38;      --border-strong: #394455;
  --text-primary: #eef1f7; --text-secondary: #a5adba; --text-muted: #7f8b9a;
  --accent: #9788ee;      --accent-rgb: 151, 136, 238;
  --pos: #52cf8c;         --neg: #ef747f;   --warn: #e8b45b;   --info: #6aa6e8;
  --sp-1: 4px; … --sp-6: 32px;
  --sidebar-width: 210px; --panel-width: 440px;    --panel-width-wide: 620px;
}
```

Four decisions inside that block:

- **CSS custom properties, not SCSS variables.** SCSS variables are compiled away; custom
  properties exist at runtime, so a theme, a media query, or a container can override them
  without recompiling. It also means `--panel-width` is readable by both the panel and the
  content column that must reserve space for it — one number, two consumers, no drift.
- **Named by role, not by value.** `--text-muted`, not `--grey-400`. The name says where it goes.
- **A six-step spacing scale.** Every gap and pad is one of six values, which is what makes
  unrelated screens look like one product.
- **`--accent-rgb` next to `--accent`.** Translucent variants need channels:
  `rgba(var(--accent-rgb), 0.13)`. The same trick for `--pos-rgb`, `--neg-rgb`, `--warn-rgb` —
  every tinted badge background is a 11–13% wash of its own text color.

## 3. Layout — the shell, and the one property that prevents an overflow bug

```scss
.app-shell { display: flex; min-height: 100vh; }

.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;                 // never squeeze the nav
  position: sticky; top: 0;
  height: 100vh; height: 100dvh;  // dvh wins where supported: mobile browser chrome
}

.content {
  flex: 1;
  min-width: 0;                   // ← the important one
  container: page / inline-size;
}
```

**`min-width: 0` is the fix for the classic flex overflow bug.** A flex item's default
`min-width: auto` means it refuses to shrink below its content — so one wide table would push the
whole page wider than the viewport and produce a horizontal scrollbar on `<body>`, dragging the
sidebar off screen. With `min-width: 0`, the content column can be narrower than its content, and
the table's own wrapper scrolls instead:

```scss
.data-table-wrap { overflow-x: auto; }
.data-table      { width: 100%; }        // plus an inline min-width from the column count
```

**Wide financial tables scroll; they do not compress.** A squeezed price column is worse than a
scrollbar.

## 4. The panel push, and `:has()`

The side panel is fixed to the right, and the page makes room for it — without any JavaScript
measuring or class-toggling:

```scss
.content {
  transition: padding-right 0.2s ease;
  &:has(.side-panel)        { padding-right: var(--panel-width); }
  &:has(.side-panel--wide)  { padding-right: var(--panel-width-wide); }
}
```

`:has()` is the parent selector: *"a `.content` that contains a `.side-panel`"*. React renders
the panel; CSS notices and reserves the space. No state, no resize observer, no layout effect.
Below 900 px the reservation is dropped and the panel becomes a full-width overlay, because a
page that narrow has nothing to give.

The entry animation lives in the panel and is suppressed by a class when one panel replaces
another:

```scss
.side-panel { animation: side-panel-in 0.2s ease; }
.side-panel--no-enter { animation: none; }
```

## 5. Container queries — sizing by the container, not the window

```scss
.content { container: page / inline-size; }

@container page (max-width: 620px) { … }
@container page (max-width: 960px) { … }
```

Ten stylesheets use `@container`, and only the shell uses `@media`. The reason is the side panel:
when it opens, the content column loses 440 px while the *window* stays exactly the same size. A
media query cannot see that; a container query can. The filter bar wraps, cards go single-column,
and stat rows restack — all because their container narrowed, whichever cause narrowed it.

**Rule of thumb: `@media` for the app frame (sidebar, top bar, page padding), `@container` for
everything inside the content column.**

## 6. Numbers, tables, and status color

Financial data has typographic requirements ordinary UI does not:

```scss
.data-table__cell--num { text-align: right; }
.intent-feed__time     { font-variant-numeric: tabular-nums; }
```

- **Right-align every numeric column**, so digits line up by place value and magnitude is visible
  without reading.
- **`font-variant-numeric: tabular-nums`** (or the mono font) for anything that updates live —
  proportional digits change width as values change, making a live table shimmer.
- **Uppercase, letter-spaced, muted headers** with an optional smaller `headerNote` underneath
  ("open PnL", "on notional") — the label stays scannable while the clarification stays out of
  the way.
- **The table caption is visually hidden** (clipped, not `display: none`), so screen readers get
  a description a sighted user does not need.

Color carries meaning, and it is a closed set:

| Token | Means | Where |
| --- | --- | --- |
| `--pos` / `--neg` | profit / loss, up / down | `.delta--pos`, `.delta--neg` from `directionOf` |
| `--warn` | degraded, stale, warning severity | pills, sparklines |
| `--neg` | down, error, critical | pills, error rows |
| `--info` | live, informational | `LIVE` pills |
| `--text-muted` | unknown, flat, no value | `.delta--flat`, `—` |
| `--accent` | interactive and identity only | links, focus rings, the active nav item |

**Accent is never a data color.** If purple meant "good" somewhere, it could not also mean
"clickable" everywhere.

One component renders all of it — `StatusPill` — and its class is derived, not hardcoded:

```jsx
<span className={`pill pill--${level}${compact ? ' pill--compact' : ''}`}>
```

A `level` comes from a domain function (`serviceStatus.js`, `VALUATION_STATUS_LEVEL`,
`LEVEL_TONE` in `logLines.js`), so the *policy* of what counts as degraded lives in the domain
layer and the component only paints it.

## 7. Motion, and turning it off

Every animation is short (120–200 ms) and every one of them is disabled under
`prefers-reduced-motion`:

```scss
@media (prefers-reduced-motion: reduce) {
  .content     { transition: none; }
  .side-panel  { animation: none; }
  .data-table tbody tr { animation: none; }
}
```

Row-flash-on-update was built and then **removed** — not for accessibility but for performance:
it was the measured cause of long tasks at 447 rows. The general rule that came out of it:
*motion on a live data table has to justify itself against the render budget.*

## 8. Class naming and file boundaries

BEM-ish, no tooling, no CSS modules:

```text
.data-table                 block
.data-table__cell--num      block__element--modifier
.side-panel--wide           block--modifier
```

The convention buys two things without a build step: a class name says which component owns it,
so a global stylesheet stays navigable; and specificity stays flat (single class selectors),
so overrides are predictable and nothing needs `!important`.

Two rules keep the partials honest:

- **A component's styles live in its own partial**, named after the block. `_logs.scss` owns
  `.log-*`; if a class shows up in two partials, one of them is wrong.
- **A comment at the top of each partial says what it covers** — the only comments in the
  stylesheets, and the reason you can find a rule without grepping.

## 9. Accessibility, in the places it was cheap and real

Not a full audit — the deliberate baseline:

| Feature | Where |
| --- | --- |
| Semantic elements (`<aside>`, `<table>`, `<caption>`, `<nav>`, real `<button>`s) | Everywhere; the panel is an `<aside>` because it supplements the page |
| `aria-sort` on the active column, `scope="col"` on headers | `DataTable` |
| `role="alert"` + `aria-invalid` + `aria-describedby` on form errors | `NewTradePanel`, `BookFormPanel` |
| `role="status"` on live counts ("showing top 100 of 340") | Valuations, Logs |
| `:focus-visible` outlines using `--accent` | Buttons, links, the collapse toggle |
| 44 px touch targets below 760 px | Sidebar links |
| `aria-hidden` on decorative glyphs (carets, dots, sparklines) | Tables, pills, chips |

Deliberately not done: focus trapping in the panel, and a full keyboard model for tabs. Native
Tab behavior is left intact rather than half-reimplemented.

## 10. Two traps this project hit

**`text-transform: uppercase` applies to all of Unicode.** A summary label read
`return ≈ β × index + α`; the uppercase transform rendered it as `B × INDEX + A`, because Greek
has uppercase forms too. The fix was renaming the label — but the lesson is that CSS text
transforms are not ASCII-only, and any symbol in a transformed label needs checking.

**A bare `logs` line in `.gitignore` matches a directory anywhere.** It silently hid
`frontend/src/components/logs/` — and, macOS being case-insensitive, `views/Logs/` — from git.
Scope runtime paths to the repo root (`/logs/`). If a new file never appears in `git status`,
`git check-ignore -v <path>` names the pattern responsible.

## 11. Where the styles are

```text
styles/
  main.scss              entry: @use variables, layout, components + the reset
  _variables.scss        all design tokens
  _layout.scss           app shell, sidebar, topbar, page, the :has() panel push
  _components.scss       barrel of @forward
  components/
    _table.scss  _pill.scss  _value.scss  _side-panel.scss  _filter-bar.scss …
```

23 component partials, ~1 per component family. The build is Vite's built-in SCSS support —
`npm run build` produces a single ~58 KB stylesheet (9.4 KB gzipped) with no PostCSS config,
no purge step, and no runtime style engine.
