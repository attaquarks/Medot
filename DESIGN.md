---
name: Medot Desktop Console
description: A clean standard desktop-console design — white surfaces on soft gray, one blue accent, standard sidebar, aligned cards. The platform's own UI voice.
colors:
  ground: "#f9fafb"
  surface: "#ffffff"
  ink: "#111827"
  ink-soft: "#4b5563"
  ink-faint: "#6b7280"
  border: "#e5e7eb"
  border-strong: "#d1d5db"
  accent: "#2563eb"
  accent-hover: "#1d4ed8"
  accent-tint: "#eff6ff"
  success: "#16a34a"
  danger: "#b91c1c"
  wordmark-amber: "#d97706"
type:
  family: '"Segoe UI", "Segoe UI Variable", system-ui, sans-serif'
  body: "15px / 1.55, weight 400"
  page-title: "26px / 700, -0.015em tracking"
  card-title: "16px / 700"
  secondary: "14px / 400, ink-soft"
  meta: "13.5px tabular-nums, ink-faint"
  section-label: "13px / 700, 0.02em, ink-soft"
  wordmark: "22px / 700, amber period"
radius:
  card: 10px
  control: 8px
  sheet: 14px
elevation:
  card: "0 1px 3px rgba(17,24,39,.08), 0 1px 2px rgba(17,24,39,.04)"
motion: "none decorative; native control feedback only"
---

# Medot Desktop Console — Design System

## Thesis

A management console for a family product reads like the category it belongs
to: white surfaces on a soft-gray ground, a standard left sidebar, aligned
cards, one blue accent, the platform's own UI voice (Segoe UI on Windows —
zero web-font dependency, native on the shipped OS). Expression lives in
precision, not theme.

## Named rules

1. **One Accent Rule** — blue carries actions and active states only; status
   colors (green success, red danger) appear only where they carry meaning.
2. **Native Voice Rule** — Segoe UI/system stack everywhere; no web fonts
   (offline-safe, CSP-safe, native-feeling).
3. **Card Discipline** — white bordered cards on the gray ground; hairline
   row separators inside cards; tabular numerals for every timestamp.
4. **Honest States Rule** — every screen shows real runtime state; unbuilt
   milestones say when they arrive; never fake data.

## Layout

- Left rail 232px (wordmark + 7 nav buttons + footer note); content column
  max 780px on the gray ground.
- Pre-console phases render a centered 560px white sheet.

## Component inventory (as built)

`shell/rail/tab` (sidebar + nav buttons, `aria-current`), `page/page-inner`,
`entries/entry` (white cards), `entry-title/-sub`, `run-row` (`.what` left /
`.when` right, tabular), `status-dot(.off)`, `section-label`, `btn` /
`btn-ghost`, `link`, inputs, `field-label`, `error`, `ok-note`, `qr-wrap`,
`centered/sheet`, `route-choice`, `status-lines`, `code`.

## Evidence

Built and verified in `desktop/src/styles/console.css` (single stylesheet,
tokens first), `desktop/src/App.tsx`, `screens-onboarding.tsx`,
`screens-console.tsx`, dev-only harness `desktop/preview.html`. The owner
replaced the previous "Day-Runner" themed world on 2026-11-03 with this
standard design; captures in `.impeccable/review/`.
