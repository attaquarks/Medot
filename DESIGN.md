---
name: Medot Desktop Console
description: The Day-Runner — a ring-binder personal planner console for overseeing Me., a personal AI companion on WhatsApp.
colors:
  paper: "#f6f1e4"
  paper-deep: "#efe7d2"
  ivory: "#fbf7ec"
  paper-bright: "#fffdf6"
  ink: "#22303c"
  ink-soft: "#4d5b66"
  pencil: "#5d5748"
  rubric: "#7a2e2e"
  rubric-deep: "#5f2323"
  manila: "#c9b99a"
  manila-hover: "#d2c3a6"
  manila-deep: "#b3a184"
  green: "#3f5643"
  amber-dot: "#d97706"
  rule: "rgba(34, 48, 60, 0.16)"
  rule-entry: "rgba(34, 48, 60, 0.28)"
  margin-rule: "rgba(122, 46, 46, 0.5)"
typography:
  wordmark:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.01em"
  page-title:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "27px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.015em"
  entry-title:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "16.5px"
    fontWeight: 700
    lineHeight: 1.55
  body:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  entry-sub:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  tab-label:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.55
  run-when:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "13.5px"
    fontWeight: 600
    lineHeight: 1.55
    fontFeature: "tnum"
  section-label:
    fontFamily: '"Libre Franklin", "Segoe UI", system-ui, sans-serif'
    fontSize: "12.5px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "0.08em"
rounded:
  tab: "8px 0 0 8px"
  control: "2px"
components:
  tab:
    backgroundColor: "{colors.manila}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tab}"
    padding: "8px 12px 8px 30px"
  tab-hover:
    backgroundColor: "{colors.manila-hover}"
  tab-active:
    backgroundColor: "{colors.ivory}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tab}"
    padding: "8px 12px 8px 30px"
  button-primary:
    backgroundColor: "{colors.rubric}"
    textColor: "#fdf9ef"
    rounded: "{rounded.control}"
    padding: "9px 20px"
  button-primary-hover:
    backgroundColor: "{colors.rubric-deep}"
  button-primary-disabled:
    backgroundColor: "{colors.manila}"
    textColor: "#4a4232"
    rounded: "{rounded.control}"
    padding: "9px 20px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 18px"
  button-ghost-hover:
    backgroundColor: "rgba(201, 185, 154, 0.35)"
  link:
    textColor: "{colors.rubric}"
  link-hover:
    textColor: "{colors.rubric-deep}"
  input:
    backgroundColor: "{colors.paper-bright}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  route-choice:
    backgroundColor: "{colors.paper-bright}"
    textColor: "{colors.ink}"
    padding: "16px 18px"
    width: "100%"
  qr:
    backgroundColor: "#fff"
    width: "220px"
    height: "220px"
    padding: "10px"
  status-dot:
    backgroundColor: "{colors.green}"
    width: "9px"
    height: "9px"
  status-dot-off:
    backgroundColor: "transparent"
    width: "9px"
    height: "9px"
  section-label:
    textColor: "{colors.rubric}"
  entry:
    textColor: "{colors.ink}"
    padding: "14px 2px 16px"
  run-row:
    textColor: "{colors.ink}"
    padding: "9px 2px"
  run-row-tentative:
    textColor: "{colors.pencil}"
    padding: "9px 2px"
  sheet:
    backgroundColor: "{colors.ivory}"
    textColor: "{colors.ink}"
    padding: "36px 40px"
    width: "560px"
---

# Design System: Medot Desktop Console

## Overview

**Creative North Star: "The Day-Runner"**

The console is one bound planner — the book where a person's companion Me. is planned and recorded — and it refuses the category default of a sidebar-of-cards admin panel. Navigation is a stack of physical manila tab dividers with punched holes; the active tab is pulled forward out of the page edge. Content sits on a cream ruled page with a burgundy margin rule, and everything on the page is written like print: hairline rules separate entries instead of card borders, running times right-align like a planner's time column, and anything not yet real is written in pencil.

The density is comfortable print, not dashboard: 15px body text on a 28px ruled pitch, one warm archival paper ground, and only two working inks — slate-navy for reading, burgundy for acting. States are honest by construction: a row is either connected (solid green dot, real timestamp), tentative (pencil-gray italic, hollow dot, plain words about when it arrives), or an error (burgundy-deep text, `role="alert"`). Nothing animates except the tab press.

Confirmed rejections, observed in the shipped code: no card borders around content (print rules only), no decorative motion, no second type family, no amber outside the wordmark's period, no fake progress or data, no radius beyond tabs and 2px controls.

**Key Characteristics:**
- Navigation as physical manila tab dividers with punched holes; the active tab pulled 6px forward on ivory
- Cream ruled page (28px pitch, `rgba(34,48,60,0.16)` lines) with a burgundy margin rule at 40px from the page edge
- Entries separated by hairline print rules (`--rule`, `--rule-entry`), never card borders
- Right-aligned running times: tabular numerals, weight 600, 13.5px, soft ink
- Pencil-gray italic (`#5d5748`) for tentative and not-yet rows
- Burgundy reserved for action and authority: buttons, links, section labels, the margin rule
- No decorative motion — the only transition is the tab's 80ms transform press
- Libre Franklin variable (100–900), self-hosted so the packaged app works offline

## Colors

Warm archival paper grounds with slate-navy ink, plus two working inks — burgundy rubric for action, planner green for live status — and manila for the physical binder furniture.

### Primary
- **Burgundy Rubric** (#7a2e2e): the working ink of action and authority. Primary buttons, text links, uppercase section labels, the page's margin rule (as a 50% wash `rgba(122,46,46,0.5)`), the text-selection wash (22%), and the route-choice hover border.
- **Deep Rubric** (#5f2323): the hover step of rubric (buttons, links) and the color of error text (`.error`).

### Secondary
- **Planner Green** (#3f5643): live status only — the solid status dot on connected rows and the `.ok-note` confirmation text ("Paired — Me. is listening on WhatsApp.").
- **Amber Period** (#d97706): the dot of the "Medot." wordmark and nothing else. A standing brand commitment kept recognizable.

### Neutral
- **Cream Page** (#f6f1e4): the open page ground, where all content sits.
- **Binder Board** (#efe7d2): the ground behind the page — body background, tab rail, and the punched holes in the tabs.
- **Raised Ivory** (#fbf7ec): paper that lifts off the page — centered sheets (sign-in, onboarding, runtime-down) and the pulled-forward active tab.
- **Fresh Sheet** (#fffdf6): the face of writable things — text and password inputs and route-choice rows.
- **Slate-Navy Ink** (#22303c): all primary text; also the base ink of the feint rules (`rgba(34,48,60,0.16)` and `0.28`).
- **Soft Ink** (#4d5b66): secondary text — sublines, entry subs, running times, rail footer — tinted from the ink, kept at ≥4.5:1 contrast on paper.
- **Pencil** (#5d5748): the not-yet. Tentative rows and the hollow status-dot ring.
- **Manila** (#c9b99a): resting tab dividers and the disabled button face.
- **Sunlit Manila** (#d2c3a6): tab hover, one step lighter.
- **Manila Edge** (#b3a184): the structural 1px border of paper objects — tabs, ghost buttons, inputs, sheets, the QR frame — and the thin scrollbar thumb.
- **Feint Rule** (`rgba(34, 48, 60, 0.16)`): the page's ruled lines and separators between running rows.
- **Entry Rule** (`rgba(34, 48, 60, 0.28)`): the stronger hairline under entries.
- **Margin Rule** (`rgba(122, 46, 46, 0.5)`): the 1.5px burgundy vertical line on the open page and on centered sheets.

### Named Rules
**The Rubric Rule.** Burgundy is for action and authority — buttons, links, section labels, the margin rule — never for body text. Its deep step (#5f2323) is the only voice errors get.

**The One Dot Rule.** Amber appears exactly once in the whole console: the period of "Medot.". Any other amber is a defect.

**The Pencil Rule.** Anything not yet real is written in pencil: gray-brown #5d5748, italic, with a hollow dot and plain words ("not connected", "arrives with milestone 3", "soon"). Never fake data, never a red alarm for a missing milestone.

## Typography

**Display Font:** Libre Franklin (variable, weight 100–900, self-hosted `libre-franklin-var.woff2`, `font-display: swap`) with "Segoe UI", system-ui, sans-serif fallback
**Body Font:** the same Libre Franklin — one family carries the entire console
**Label/Mono Font:** none. The `<code>` elements in Settings file paths fall through to the browser's default monospace — unstyled in the shipped CSS; incidental, not a token.

**Character:** a sturdy humanist grotesque with print-era plainness. Slightly negative tracking on the wordmark and page titles gives headings the tight set of a printed planner header; everything else is set loose and large for an elderly, non-technical reader (15px base, 1.55 line-height).

### Hierarchy
- **Wordmark** (700, 24px, -0.01em): "Medot." with the amber period; top of the rail and first line of every centered sheet.
- **Page title** (700, 27px, 1.55, -0.015em): one per page, 6px above its subline.
- **Entry title** (700, 16.5px): the head of an entry ("Me. — your companion", "WhatsApp").
- **Body** (400, 15px, 1.55): default text; page sublines capped at 62ch.
- **Entry sub** (400, 14px, soft ink): descriptions under entry titles.
- **Tab label** (600, 14.5px; 700 when active): rail navigation.
- **Running time** (600, 13.5px, tabular numerals, soft ink): the right-aligned `.when` column.
- **Section label** (700, 12.5px, 0.08em, uppercase, burgundy): the "RECENT ACTIVITY" eyebrow above entry groups.

Supporting sizes as built: field labels 13.5px/600 (14px above, 6px below); form errors 13.5px deep rubric; confirmation note 14px/600 planner green; muted notes 13.5px soft ink; rail footer 12.5px soft ink.

### Named Rules
**The Tabular-Time Rule.** Every running time sits right-aligned at the end of its row — tabular numerals (`font-variant-numeric: tabular-nums`), weight 600, 13.5px, soft ink — like a planner's time column. Timestamps render as `YYYY-MM-DD · HH:MM:SS` (the ISO `T`/`Z` swapped for a middot).

**The One-Family Rule.** Libre Franklin is the only typeface and it ships inside the app. No webfont CDNs; the packaged console must render correctly offline.

## Layout

The shell is a full-height flex row: a fixed 216px rail (the binder edge) and the open page.

- **Rail** (216px, `--paper-deep`): padding 26px top/bottom, 22px left; wordmark on top (padding 0 14px 18px), then the tab stack at a 6px gap; a plain-language footer pinned to the rail's bottom (`margin-top: auto`, 12.5px soft ink) noting that closing the window keeps Me. running.
- **Page** (`--paper`): flex 1, scrolls vertically (`overflow-y: auto`, thin scrollbar with a `--manila-deep` thumb). Feint rules run at a 28px pitch — 27px clear, then a 1px `rgba(34,48,60,0.16)` line — as a `repeating-linear-gradient` bound to the content (`background-attachment: local`). The burgundy margin rule is a 1.5px vertical line at 40px from the page's left edge, full height. Padding: 34px top, 48px right, 48px bottom, 58px left (content clears the margin rule). A 1px `--manila-deep` border on the page's left edge is its spine; `--shadow` lifts it off the board.
- **Content column** (`page-inner`): max-width 760px. Entries stack in a grid with a 14px gap starting 26px below the page heading; no entry's children exceed 70ch.
- **Centered sheets** (sign-in, onboarding, connecting, runtime-down): ruled paper fills the window (same 28px pitch, 72px/32px outer padding); a single 560px ivory sheet carries the wordmark, heading, and form, with its own margin rule at 26px and 36px/40px padding.

There are no responsive breakpoints — this is a fixed desktop window (Tauri); only the page column scrolls.

## Elevation & Depth

Depth is paper lying on a desk, and it comes from two ink-tinted shadows plus layering — never from borders on content. The binder board (`--paper-deep`) is the desk; the open page and centered sheets lift off it with `--shadow`; the active tab, pulled forward, lifts too. Entries are flat: depth on the page is created by the ruled lines, the margin rule, and hairline separators, not by boxes.

### Shadow Vocabulary
- **sheet** (`--shadow`: `2px 4px 12px rgba(34, 48, 60, 0.14)`): the open page, centered sheets, and the pulled-forward active tab — paper at rest above the desk.
- **press** (`--shadow-press`: `1px 2px 5px rgba(34, 48, 60, 0.18)`): the resting tabs — a thin paper edge, tighter than the sheet shadow.
- **hole inset** (`inset 0 1px 1px rgba(34, 48, 60, 0.35)`): the punched hole in each tab, die-cut into the paper.

### Named Rules
**The Paper-Lift Rule.** Shadows mark physical paper only — page, sheet, pulled-forward tab. Buttons, inputs, entries, and the QR frame stay flat; nothing floats on hover.

**The Print-Rule Rule.** Content is separated by hairline print rules — `1px solid var(--rule-entry)` under entries, `1px solid var(--rule)` between running rows, dropped on the last row — never by bordered cards. A planner page has no card borders.

## Shapes

Square by default. Exactly two radii exist: controls (buttons, inputs, focus outlines) bend 2px, and tabs bend 8px on their left corners only (`8px 0 0 8px`) so they read as dividers sliding out of the page's edge — their right side disappears into the page. The punched hole is a 9px circle. Borders are 1px: `--manila-deep` for paper structure (tabs, ghost buttons, inputs, sheets, QR frame), `--rubric-deep` on the primary button, and the hairline rules that do the separating are translucent inks, not borders. The only gradient in the console is the ruled-line texture itself.

## Components

### Tab divider (signature)
- **Shape:** left-rounded divider (`8px 0 0 8px`), min-height 42px, padding 8px 12px 8px 30px, 1px `--manila-deep` border with no right border, `--shadow-press`.
- **Punched hole:** a 9px `::before` circle at left 11px, filled with the board color `--paper-deep` and an inset shadow, vertically centered.
- **Rest:** manila, ink label at 14.5px/600. **Hover:** one step lighter (`#d2c3a6`). **Press:** `translateX(-2px)`.
- **Active** (`aria-current="page"`): ivory face, full `--shadow`, label at 700, pulled `translateX(6px)` forward out of the page edge.
- **Motion:** the tab is the only animated element in the app — `transition: transform 80ms ease-out`, press and pull only.

### Entries and running rows
- **Entry:** a flat section on the ruled page — padding 14px 2px 16px, `border-bottom: 1px solid var(--rule-entry)`, children capped at 70ch. Entry title 16.5px/700, entry sub 14px soft ink; inner row stack (`entry-rows`) starts 8px below.
- **Run-row:** flex row on the text baseline, 14.5px, gap 14px, padding 9px 2px, `border-bottom: 1px solid var(--rule)` (none on the last). `.what` takes the remaining width; `.when` is fixed to the right edge — the running-time column.
- **Tentative** (`.run-row.tentative`): both cells in pencil `#5d5748`, italic; pairs with the hollow status dot. Used for "not connected", "arrives with milestone N", and the "soon" rows.

### Status dot
- 9px circle on the text baseline, 8px right margin: solid planner green when connected, transparent with a 1.5px pencil ring when off (`.status-dot.off`). Always `aria-hidden` — the row text carries the state in words.

### Section label
- Uppercase burgundy eyebrow (12.5px/700, 0.08em tracking, margin 30px 0 4px) introducing an entry group ("Recent activity", "Specialist spaces").

### Buttons
- **Shape:** near-square corners (2px), no shadows.
- **Primary** (`.btn`): burgundy `--rubric` face, warm ivory text `#fdf9ef`, 1px `--rubric-deep` border, 700 at 14.5px, padding 9px 20px. Hover deepens to `--rubric-deep`. Disabled: manila face, manila-deep border, `#4a4232` text, `cursor: not-allowed`.
- **Ghost** (`.btn-ghost`): transparent face, ink text, 1px `--manila-deep` border, 600 at 14px, padding 8px 18px. Hover: a 35% manila wash.
- **Link action** (`.link`): a burgundy underlined text button (700, underline offset 3px, 2px/1px padding); hover deepens to `--rubric-deep`. Carries row-level actions (Connect, Set up, Sign out, Skip for now, Try again).
- **Route choice** (`.route-choice`): a full-width, left-aligned choice row — fresh-sheet face, 1px manila-deep border, padding 16px 18px; strong line 15.5px, description 13.5px soft ink 3px below. Hover shifts the border to `--rubric` — the only hover that changes a border.

### Inputs / Fields
- **Style:** fresh-sheet face `#fffdf6`, 1px `--manila-deep` border, 2px radius, padding 10px 12px, full width, inherits the family (text and password today).
- **Focus:** the global focus treatment with the outline pulled to `outline-offset: 0` so it hugs the field's own border.
- **Labels / errors:** 13.5px/600 labels (`field-label`, margin 14px 0 6px, bound via `htmlFor`); errors render under the field as 13.5px deep-rubric text with `role="alert"`.

### QR frame
- 220px square image on pure white for scannability, 1px `--manila-deep` border, 10px inner padding, centered (`qr-wrap` padding 18px 0 6px). When pairing completes, the image is replaced by the planner-green confirmation note.

### Centered sheet
- The onboarding/sign-in container: 560px ivory sheet, 1px `--manila-deep` border, full `--shadow`, 36px/40px padding, burgundy margin rule at 26px, wordmark inside. Sits on the ruled paper ground.

### Wordmark
- "Medot." at 24px/700, -0.01em, with the amber period (`#d97706`). Appears once per view: top of the rail, or first line of a centered sheet.

### State vocabulary (as built)
- **Connected** — plain `.run-row` in ink, solid `.status-dot` (green), real `connected_at` timestamp in the `.when` column.
- **Tentative / not yet** — `.run-row.tentative`: pencil-gray italic in both cells, `.status-dot.off` hollow ring, honest copy ("not connected", "arrives with milestone 3", "soon").
- **Error** — `.error` text (13.5px deep rubric, `role="alert"`) for form and API failures. Route-level errors keep the row tentative and append "· connection error — try connecting again"; they never turn a row red.
- **Loading / busy** — words only: the button label swaps ("Waiting for Google…", "Show QR"), the sheet says "Opening your day-runner…", Settings says "Opening the workspace…"; the trigger disables to the manila face. No spinners anywhere.

## Do's and Don'ts

### Do:
- **Do** separate entries with hairline print rules: `border-bottom: 1px solid var(--rule-entry)` under entries, `var(--rule)` between running rows, none on the last.
- **Do** right-align every running time in the `.when` column — tabular numerals, 600, 13.5px, soft ink.
- **Do** keep burgundy for action: buttons (`--rubric`, hover `--rubric-deep`), links, section labels, the margin rule.
- **Do** write not-yet states in pencil — italic `#5d5748`, hollow dot, plain words about when it arrives.
- **Do** show the solid green dot only when the thing is genuinely connected; hollow ring means off.
- **Do** keep the keyboard floor as built: 2px solid `--rubric` focus outline at 2px offset (0 on inputs), `aria-current="page"` on tabs, `aria-hidden` dots with meaning in the row text, `role="alert"` errors, labels bound with `htmlFor`, `nav aria-label="Main"`.
- **Do** keep soft ink ≥4.5:1 on paper for all secondary text and the 15px/1.55 base for large-type-friendly reading.
- **Do** use 1px `--manila-deep` borders on paper objects (tabs, ghost buttons, inputs, sheets, QR) and keep content max-widths (760px column, 70ch entries, 62ch sublines).

### Don't:
- **Don't** box content in cards — no borders around entries or runs; the page's print rules do the separating.
- **Don't** add decorative motion — no hover easing, fades, or spinners. The only transition in the app is the tab's `transform 80ms ease-out` press/pull.
- **Don't** use amber anywhere except the wordmark's period.
- **Don't** introduce a second type family; Libre Franklin ships self-hosted and must survive offline.
- **Don't** put shadows on controls or content — shadows belong to physical paper only (page, sheet, pulled-forward tab).
- **Don't** fake progress or data; unbuilt capabilities render as pencil rows naming their milestone.
- **Don't** exceed 2px radius on controls — only tabs bend, 8px on the left corners.
- **Don't** render a not-yet state as an error: pencil is for pending, deep-rubric text is for real failures.

## Evidence

Derived entirely from the shipped build (no planned-but-unbuilt features recorded):

- `desktop/src/styles/console.css` — all tokens (`:root` custom properties), font-face, and every component rule cited above.
- `desktop/src/App.tsx` — shell (`shell`/`rail`/`page`), tab rail with `aria-current`, phase sheets (connecting, runtime_down), wordmark.
- `desktop/src/screens-onboarding.tsx` — SignIn and ConnectWhatsApp (route choices, API-key field, QR pairing, busy/error states).
- `desktop/src/screens-console.tsx` — Overview, Identities, Knowledge, Connectors, AI Providers, Activity, Settings; run-row/state vocabulary; `fmtWhen` timestamp format.
- `desktop/src/lib/api.ts` — `WaRoute`/`WaStatus` fields behind connected/tentative/error rows.
- `desktop/src/fonts/libre-franklin-var.woff2` — the self-hosted variable font.
- Capture set (finish review, 2026-11-02): `.impeccable/review/prev-signin.png`, `prev-connect.png`, `prev-overview.png`, `prev-overview_off.png`, `prev-identities.png`, `prev-knowledge.png`, `prev-connectors.png`, `prev-providers.png`, `prev-activity.png`, `prev-settings.png` (10 files) — visually confirm the recorded system.
- Context: `.impeccable/surfaces/desktop-src-app-tsx.md` (direction contract) and `PRODUCT.md` (brand commitments: wordmark amber dot, plain language, WCAG AA floor).
