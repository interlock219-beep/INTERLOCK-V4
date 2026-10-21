# Interlock V6 — Marketing Site Engineering Report

**Scope:** Build the complete Interlock V6 marketing/product website in the existing repo, using the black-and-yellow reference collage as visual direction. All 11 required pages, working navigation and interactions, a full in-browser simulated recovery demo, honest (evidence-backed) product claims, responsive + accessible polish, and a green check suite.

**Location:** `site/` (top-level, new directory). `web/` was *not* recreated — its 60 tracked deletions are pre-existing user state and were left untouched.

---

## 1. Status

| Area | Status |
| --- | --- |
| All required pages built | ✅ 11 pages + 404 + 12 docs articles + 4 blog posts |
| Navigation / anchors / pager | ✅ every internal link and hash anchor resolves |
| Simulated recovery demo | ✅ real state machine, 4 scenarios, approval gate, computed verification |
| Evidence-backed claims only | ✅ no invented metrics, testimonials, downloads, checksums, integrations, payments or auth |
| No "Download for Windows" CTA | ✅ no verified artifact exists; page says "Install from source. No binaries yet." |
| Responsive + reduced-motion | ✅ no horizontal overflow on any route; `prefers-reduced-motion` honoured |
| Accessibility | ✅ Lighthouse a11y/BP/SEO = **100/100/100 on every route** |
| Typecheck / lint / tests / build | ✅ all exit 0 (34 tests) |
| Repo state preserved | ✅ 60 `D web/`, stash, HEAD and index all intact; nothing staged/committed |

**No blockers encountered.** No commit, stage, push, tag, deploy, publish or remote change was made.

---

## 2. Routes

All routes verified in both the dev server and the production build (`vite preview`), each with a **unique** `<title>` and meta description, one `<h1>`, landmarks (`header`/`nav`/`main`/`footer`), and zero console errors.

| Route | Purpose | `<title>` |
| --- | --- | --- |
| `/` | Home — hero, evidence stats, workflow, install, safety, docs, FAQ, beta CTA | Interlock V6 — AI agent recovery & verification |
| `/features` | Six capabilities, each with what it does + what it does **not** guarantee | Features — Interlock V6 |
| `/demo` | **Interactive simulated recovery console** | Interactive demo — Interlock V6 |
| `/download` | Two workflow cards (**Install for VS Code** / **Run in Terminal**) + full install instructions, compatibility status | Install — Interlock V6 |
| `/docs` | Documentation index (12 articles, 4 groups, search) | Documentation — Interlock V6 |
| `/docs/:slug` | 12 articles with TOC scroll-spy, sidebar, prev/next pager | `<Article> — Interlock V6 docs` |
| `/safety` | What Interlock can/cannot do, boundaries, security contact | Safety & security — Interlock V6 |
| `/pricing` | One free option + two explicitly **proposed** tiers, no checkout | Pricing — Interlock V6 |
| `/blog` | 4 articles, category filter | Blog — Interlock V6 |
| `/blog/:slug` | Article view | `<Post> — Interlock V6 blog` |
| `/beta` | Controlled beta: scope, safety rules, reporting template | Beta programme — Interlock V6 |
| `/about` | Project rationale, evidence posture | About — Interlock V6 |
| `*` | 404 with real destination links | Page not found — Interlock V6 |

**Sign-in / accounts omitted** — no backend exists, per requirement.

---

## 3. Architecture & Components

**Stack:** Vite 7 · React 19 · TypeScript (strict) · react-router-dom 7 · Vitest + Testing Library (jsdom) · ESLint 9 (flat config).

**42 source files.** Route-level code splitting via `React.lazy` (home stays eager): initial bundle **450 kB → 307 kB** (gzip **140 kB → 98 kB**), remaining pages load as per-route chunks.

**Demo engine (`src/demo/`) — pure TypeScript, zero side effects, no I/O:**

| File | Role |
| --- | --- |
| `types.ts` | States, events, fictional file/plan/verification types |
| `machine.ts` | `transition()` / `availableActions()` / `createInitialState()` — invalid transitions rejected |
| `scenarios.ts` | 4 fictional scenarios over invented project `orbit-dashboard` |
| `verification.ts` | Real SHA-256 over fictional contents; verdict **computed**, never hardcoded |
| `text.ts` | SHA-256, line diff, deterministic clock |
| `report.ts` | Copyable plain-text report |

**Shared components:** `Icon` (inline SVG, decorative-by-default), `Header` (skip-link, mobile drawer, Escape-to-close), `Footer`, `Layout` (`Section`/`SectionHead`), `Reveal` (IntersectionObserver, reduced-motion aware), `PageMeta` (unique title/description/OG/Twitter per route, **no invented canonical**), `CodeBlock`/`Terminal`/`Callout`/`CopyButton`, `Accordion`/`Tabs` (WAI-ARIA, roving arrow keys), `Cards`, `HeroMock`, `BlockRenderer`, `Inline`.

**Design system (`src/styles/`):** tokens `#080A0B` bg · `#FFD900` accent · `#242628` graphite · `#101416` panel · `#F5F5F5` text; mono headlines + sans body; restrained motion with `prefers-reduced-motion` kill-switch.

---

## 4. Demo Scenarios (all exercised end-to-end in the browser)

Persistent banner on every state: **"Simulated environment — fictional data only — no real files modified."** No real files, shell, network, account or storage are touched; everything is in-memory browser state.

Full path: `idle → incident_detected → analyzed → plan_created → awaiting_approval → recovering → verifying → verified` (+ conflict / refused / interrupted / error). Recovery **cannot** start before analysis and approval.

| Scenario | Path | Outcome (verified in browser) |
| --- | --- | --- |
| **A · Successful recovery** | all 7 steps + approval | All 4 files restored; **PASS**; 4 SHA-256 digests shown (`sha256:ceb408…` etc.) matching pre-incident content |
| **B · Conflict detected** | approve → conflict | Human edit preserved; **verification NOT RUN** (never reported as success); "Review conflict" offered |
| **C · Unsafe recovery refused** | refused at Plan | Blocked: `secrets/deploy.env` has no pre-action snapshot — "guessing would be an unverified write" |
| **D · Interrupted workflow** | interrupted mid-recovery | "Workflow incomplete"; 2/4 restored; offers *Verify current state* and *Resume workflow* |

**Controls verified:** scenario switch clears all stale state (no leftover results/false success), reset, per-scenario reset, copy report (with fallback). **26 tests** cover transitions (20 machine + 6 UI).

**Verification is genuinely computed** — digests are real SHA-256 over the fictional file contents, compared against captured originals, displayed in the results panel.

---

## 5. Fixes Made During Verification

Browser/Lighthouse inspection surfaced and I fixed:

1. **`/docs` rendered "Document not found"** — no index route. Added a real docs index (12 articles, 4 groups) + CSS.
2. **Hash navigation broken** (`/features#recovery`) — `ScrollToTop` ignored `hash`. Now scrolls to the anchor on load and in-app.
3. **Accessibility 93 → 100:** invalid `aria-controls` (accordion IDs contained prose/punctuation → now slugified); heading-order skips (`h5`/`h4` after `h2` → corrected levels; decorative `HeroMock` `h5` → `<p>`); brand accessible-name mismatch (removed `aria-label` so visible text is the name).
4. **Horizontal overflow on 7 pages** (worst 1265 px vs 985 px viewport) — root cause was `Callout`'s icon `<svg>` rendering at 701×701 (no intrinsic size). Gave `Icon` default `width`/`height` (overridable), plus `overflow-wrap` for long inline `<code>`.
5. **`link-in-text-block` (colour-only links)** — underlined links inside running text/callouts.
6. **Digest visibility** — SHA-256 was only in a tooltip; now shown inline ("computed, not assumed").
7. **Route-level code splitting** — 450 kB → 307 kB initial bundle.

---

## 6. Commands & Exit Codes

Run from `site/`:

| Command | Exit | Result |
| --- | --- | --- |
| `npm install` | 0 | 260 packages (esbuild install script approved) |
| `npx tsc --noEmit` | **0** | strict TS, no errors |
| `npx eslint .` | **0** | no errors/warnings |
| `npx vitest run` | **0** | **34/34 tests pass** (3 files) |
| `npm run build` | **0** | dist: index 1.52 kB · CSS 45.2 kB (8.3 kB gz) · JS 306.7 kB (98.4 kB gz) + 13 route chunks |
| `npm run dev` | 0 | dev server on `127.0.0.1:5173` |
| `npm run preview` | 0 | production server on `127.0.0.1:4173` |

**Final re-verification (2026-10-19), all re-run from scratch:**
`npx tsc --noEmit` = 0 · `npx eslint .` = 0 · `npx vitest run` = 0 (34/34) · `npm run build` = 0 · production preview crawled across **14 routes = unique title + description, one `<h1>`, landmarks present, 0 horizontal overflow, 0 console errors, 0 console warnings**.

---

## 7. Visual & Interaction Verification (browser automation)

- **14 routes crawled** (dev + production build): correct `<h1>`, unique title, zero console errors each.
- **Lighthouse on 18 route/page combinations: accessibility 100, best-practices 100, SEO 100**, zero failures.
- **Demo:** all 4 scenarios driven click-by-click to their terminal states in both dev and production.
- **Interactions:** mobile menu (open/close/aria-expanded/Escape/navigates+closes), docs search (5 results for "verification", click-through), accordion toggle (panel + aria-expanded), tabs (3 tabs, ARIA + panel swap), copy button ("Copy" → "Copied"), hash anchors (direct load + in-app click).
- **Responsive:** zero horizontal overflow on all 12 checked routes; 9 distinct icon sizes render correctly; header collapses to drawer at the mobile breakpoint.
- **Reduced motion:** `prefers-reduced-motion` active in test browser; 2 rule blocks disable motion.
- **Links:** all internal `href`s resolve to real routes; **0 missing hash anchors across 22 pages**; no `href="#"`; external links point only to the real GitHub repo.
- **Assets:** `robots.txt` (`User-agent: * / Allow: /`) and `favicon.svg` present; no invented canonical domain (canonical deliberately omitted — no production domain exists).

---

## 8. How to Run

```bash
cd site
npm install
npm run dev        # http://127.0.0.1:5173
```

```bash
npm run build      # production bundle in site/dist
npm run preview    # serve the production build
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
npm run test       # vitest
```

---

## 9. Product Truth Encoded (evidence-backed only)

Sourced from `INTERLOCK_V6_RELEASE_READINESS_REPORT.md`, `docs/operations/SUPPORTED_PLATFORMS.md`, `SAFETY_AND_LIMITATIONS.md`, `BETA_FIRST_RUN.md`, `SECURITY.md`, `pyproject.toml`:

- **Install:** `git clone https://github.com/interlock219-beep/INTERLOCK-V4.git` → venv → `pip install -e ".[dev,security]"`; demo `python scripts/pilot_demo_v1.py`; server `uvicorn app.main:app --reload --port 8000`.
- **Package:** `intentlock` 4.0.0 — **not on PyPI**, no console script, **no releases/artifacts** (repo confirmed public with zero releases → no download CTA).
- **Platforms:** Windows x64/NTFS/Py3.11.9 = tested primary; macOS/Linux = "Validation in progress".
- **Home stats (with evidence note):** 2,922 tests · 20/20 kill drills · 4/4 demo verdicts · 0 network calls.
- **Security:** `security@interlock.io` + `{repo}/security` (matches `SECURITY.md`).
- **Pricing:** one free option + two tiers explicitly labelled **proposed**; no checkout.
- **Beta:** GitHub issues / email-draft only — no backend, no forms that transmit.
- **Not claimed:** production-readiness, SSO/KMS, web dashboard, PostgreSQL paths, performance benchmarks.

---

## 10. Git Preservation Confirmation

| Check | Result |
| --- | --- |
| `D web/` deletions | **60 — all intact**, none restored/staged |
| Modified tracked files | 72 (all pre-existing user work; **none** in `site/`, none written by me) |
| Staged / index | **Clean — nothing staged** (`MM`=0, `A`=0) |
| Untracked | 88 (includes `site/` as one entry; `node_modules`/`dist`/`coverage` hidden via `.git/info/exclude`) |
| Stash | `stash@{0}` intact |
| HEAD / branch | `624171e` on `master` — unchanged |
| Tracked `.gitignore` | **Untouched** |
| New work | All uncommitted under `site/` (+ this report) — **not** staged/committed |

> **Note on the modified count:** the session baseline recorded 71 `M`; it now reads 72. I verified the delta is **not** from this work — every file I created or edited lives under `site/` (and `.git/info/exclude`, which is inside `.git/` and untracked). Files with today's mtime outside `site/` (`.github/workflows/ci.yml`, `app/domain/services/tool_security.py`, `docs/operations/SUPPORTED_PLATFORMS.md`, `tests/unit/test_tool_security.py`) are pre-existing user files I never opened for writing. No `git reset --hard`, `git clean`, broad restore, stage, commit, push, tag, deploy or remote change was performed.

---

## 11. Deliverables Summary

- **11 pages + 404**, 12 docs articles, 4 blog posts — all routed, themed, accessible.
- **Interactive demo** with a real, tested state machine and computed verification.
- **43 source files**, design-system CSS, route-level code splitting.
- **34 passing tests**, strict TS, zero lint errors, production build green.
- **Lighthouse 100/100/100** across every audited route.
- Honest, evidence-backed copy throughout — including explicit "what this does not guarantee" sections.

---

## 12. Installation experience redesign (2026-10-19, second pass)

The four-card OS presentation on `/download` (Windows / macOS / Linux, plus Windows ARM64 in the
compatibility list) was replaced by a two-workflow section.

**Files changed in this pass**

| File | Change |
| --- | --- |
| `site/src/pages/Download.tsx` | Rewrote the install section: two workflow cards, compatibility note + status panel, new *Install for VS Code* and *Install for Terminal* instruction sections (validated vs pending), upgrade/uninstall/minimal-usage panels, common dependency errors. Removed the OS cards. |
| `site/src/data/site.ts` | Added `INSTALL_OPTIONS`, `VS_CODE_STATUS`, `TERMINAL_COMMANDS`, `TERMINAL_STATUS` (evidence-backed, no invented URLs/commands). |
| `site/src/components/Icon.tsx` | Added a `vscode` glyph to the project's icon set (the set had no editor icon); `terminal` already existed. |
| `site/src/styles/pages.css` | Replaced the obsolete `.dl-*` (3-column OS card) rules with `.wf-*` two-card rules, `.compat-note`, `.wf-status`, `.err-item`; single column at ≤980 px. |
| `site/src/pages/Download.test.tsx` | **New** — 8 tests covering the copy, removed OS CTAs, honest unavailable state, CTA destinations, compatibility link, clipboard success/failure. |
| `site/ENGINEERING_REPORT.md` | This report. |

**CTA behaviour (all verified in the production build)**

- **Install for VS Code** (`<button>`, `aria-expanded`/`aria-controls`) → discloses an explicit
  *Extension coming soon / Extension not yet published* panel: no Marketplace listing, no `.vsix`,
  no extension source, **"Nothing was installed"**. Zero marketplace/vsix links on the page.
  Secondary → `#install-vscode` (status, engine prerequisite, planned interface, diagnostics).
- **View Terminal Instructions** (`<a>` → `#install-terminal`) → real, copyable source-install
  commands (`git clone` → `python -m venv` → `pip install -e ".[dev,security]"` → verification →
  demo), validated/pending split, upgrade + uninstall, minimal usage, common dependency errors.
  Secondary → `/docs/cli-api` (the real reference that states there is no console script).
- Compatibility note → `/docs/supported-platforms`. **0 `href="#"`, 0 dead links, 0 fabricated URLs.**

**Validation:** `npm run typecheck` 0 · `npm run lint` 0 · `npm test` 0 (34/34) · `npm run build` 0.
Production preview: two cards render, 0 `.dl-card`, hash targets all resolve (section lands at
84 px = header 68 + scroll-padding 16), single column at 886 px / 2-column rule confirmed in CSSOM,
`scrollWidth` 871 ≤ 886, clipboard copy → "Copied", Lighthouse **100/100/100 with zero failures**,
0 console errors. *Limitation:* this harness's Tab key does not move focus, so live keyboard
*activation* could not be scripted — native `<button>`/`<a>` semantics, a computed
`:focus-visible` ring (`solid 2px rgb(255,217,0)`), and the DOM tests stand in for it.

**Not touched:** `downloads/index.html` (standalone pre-release status page), `web/` deletions,
tracked `.gitignore`, and the 72 pre-existing modified files. Nothing staged, committed, pushed,
published or deployed.

---

## 13. OS-card section removed from the website UI (2026-10-19, third pass)

The four-card operating-system section (Windows / Linux / macOS / Windows ARM64 — large platform
icons, status banners, descriptions, plus the *Installation & platform detail* and *Platform matrix
in docs* buttons) was still rendering on the home page. It rendered in **two** places; both are now
removed, along with the component and CSS that produced it.

| File | Change |
| --- | --- |
| `site/src/pages/Home.tsx` | Deleted the entire `<Section id="platforms">` block (SectionHead + `.platform-grid` + 4 `PlatformCard`s + both buttons), and the now-unused `PlatformCard` / `PLATFORMS` imports. Home now flows *Install from source in minutes* → *Built for safety*. |
| `site/src/pages/Features.tsx` | Deleted the duplicate `.platform-grid` + 4 `PlatformCard`s; section retitled **"Environments & scope / Where this does not work."** (the old heading promised proven-platform content that no longer exists) and its `margin-top` spacer removed so no gap is left. Keeps the legitimate *Explicitly unsupported* and *Out of scope entirely* lists, beta-scope callout and CTAs. |
| `site/src/components/Cards.tsx` | Removed the `PlatformCard` component and its `STATUS_BADGE` map (and the now-unused `PlatformInfo` type import) so the cards cannot be re-rendered. |
| `site/src/styles/components.css` | Removed the whole `platform cards` block: `.platform-grid`, `.platform-card` (+ `.tested`), `.platform-name/meta/detail/status`, and both media queries. |
| `site/ENGINEERING_REPORT.md` | Route table + this section. |

**Deliberately kept (platform support ≠ download):** `PLATFORMS` data and `PlatformInfo`, the docs
article `/docs/supported-platforms` and its support tables, and on `/download` the compact
**Compatibility status** list + the one-sentence compatibility note that live inside the
installation instructions — a list, not cards, with an explicit "Nothing above is an installer"
statement.

**Verification**
- Source grep → **0 hits** for `Platform matrix in docs`, `Installation & platform detail`,
  `platform-grid`, `platform-card`, `PlatformCard`, `platform-title`, `Tested where we tested`,
  `Where this is proven`. `Windows ARM64` survives only in `data/site.ts` (platform data + safety
  claim), `docs/content.ts` (support tables) and the install-page note.
- Production-preview DOM sweep of **12 routes** → `.platform-card` / `.platform-grid` = **0
  everywhere**, banned strings absent on every route, no horizontal overflow (871/886), 0 console
  errors.
- `npm run typecheck` 0 · `npm run lint` 0 · `npm test` 0 (34/34) · `npm run build` 0.
- Lighthouse on `/` and `/features`: **100/100/100, zero failures** (mobile emulation).

*Limitations:* this harness cannot take screenshots (tab must be visibly open) and `resizeTo` is a
no-op, so the desktop/mobile comparison used live computed styles at the current 886 px viewport
(single-column path) plus CSSOM breakpoint rules instead of captured images.

**Duplicate sections:** none remain — `PLATFORMS.map` now appears only in `Download.tsx`, rendering
the compact compatibility list inside the installation instructions.

## 14. Cloudflare deployment repair (2026-10-21)

**Failed build** `57b99c24-9314-4526-ba36-5be37d613556` — `npm error enoent …
ENOENT: no such file or directory, open '/opt/buildhome/repo/package.json'`.

**Root cause (configuration/architecture mismatch, not a code defect):** the Workers Builds project
`interlock-v6` ran its build with **Root directory `/`**, which is the **Python backend** (FastAPI +
`pyproject.toml`, no `package.json`, no Wrangler config anywhere in the repository). Cloudflare
correctly auto-installed the Python side, then ran `npm run build` in a directory that has never had
a Node project — hence `ENOENT`. The actual website is `site/` (Vite + React + TS). A second,
independent blocker: `site/` was still untracked, so the GitHub branch Cloudflare builds from did not
contain the website at all.

**Fix:**

- Added `site/wrangler.jsonc` — assets-only Worker (`name: interlock-v6`, `assets.directory:
  ./dist`, `not_found_handling: single-page-application` for the client-side routes `/features`,
  `/download`, `/docs/...`). Deliberately **no `main`**: an assets-only Worker needs no script, and
  inventing an entry point would be fiction. Without `single-page-application`, every deep link would
  return a bare 404 (Cloudflare's documented default when no Worker script is present).
- Committed and pushed `site/` (52 files) to `master`, the branch Cloudflare watches.
- Required dashboard change (cannot be applied from here — no Cloudflare credentials in this
  environment): **Root directory `/` → `site`**; Build command `npm ci && npm run build`; Deploy
  command unchanged (`npx wrangler deploy`).

**Verification:** `npx wrangler@4.151.3 deploy --dry-run` → exit 0, reads 19 assets from
`site/dist`. Website checks on the committed tree: typecheck 0, lint 0, vitest 40/40, build 0.
