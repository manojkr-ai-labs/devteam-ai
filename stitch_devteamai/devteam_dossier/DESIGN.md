---
name: DevTeam Dossier
colors:
  surface: '#fbf9f4'
  surface-dim: '#dcdad5'
  surface-bright: '#fbf9f4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3ee'
  surface-container: '#f0eee9'
  surface-container-high: '#eae8e3'
  surface-container-highest: '#e4e2dd'
  on-surface: '#1b1c19'
  on-surface-variant: '#4a463f'
  inverse-surface: '#30312e'
  inverse-on-surface: '#f3f1ec'
  outline: '#7b766e'
  outline-variant: '#ccc6bc'
  surface-tint: '#615e59'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1d1b17'
  on-primary-container: '#87837d'
  inverse-primary: '#cbc6bf'
  secondary: '#635d58'
  on-secondary: '#ffffff'
  secondary-container: '#eae1da'
  on-secondary-container: '#69635e'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#002115'
  on-tertiary-container: '#5f8e77'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e8e1db'
  primary-fixed-dim: '#cbc6bf'
  on-primary-fixed: '#1d1b17'
  on-primary-fixed-variant: '#494641'
  secondary-fixed: '#eae1da'
  secondary-fixed-dim: '#cdc5bf'
  on-secondary-fixed: '#1f1b17'
  on-secondary-fixed-variant: '#4b4641'
  tertiary-fixed: '#bbeed3'
  tertiary-fixed-dim: '#a0d1b8'
  on-tertiary-fixed: '#002115'
  on-tertiary-fixed-variant: '#204f3c'
  background: '#fbf9f4'
  on-background: '#1b1c19'
  surface-variant: '#e4e2dd'
typography:
  headline-xl:
    fontFamily: Newsreader
    fontSize: 36px
    fontWeight: '400'
    lineHeight: 44px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: '400'
    lineHeight: 36px
    letterSpacing: -0.01em
  section-marker:
    fontFamily: IBM Plex Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.12em
  body-lg:
    fontFamily: IBM Plex Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
    letterSpacing: '0'
  body-md:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: '0'
  meta-sm:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
  meta-xs:
    fontFamily: IBM Plex Sans
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
  code-base:
    fontFamily: Courier Prime
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  code-meta:
    fontFamily: Courier Prime
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
spacing:
  gutter: 1.5rem
  margin: 2.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

The design system establishes the visual atmosphere of an archival laboratory record, a rigorous physical folio, and a definitive technical forensic report. It rejects decorative tech tropes, hyperactive SaaS notifications, and artificial visual urgency. Instead, the interface acts as a silent, durable substrate for precise software engineering investigations.

The visual style is **Quiet Archival Minimalist / Editorial Structuralism**:
- **Tone & Mood:** Sober, objective, scholarly, forensic, authoritative. It presents code modifications and test executions with the gravity of historical proceedings.
- **Visual Discipline:** Pure mechanical layout, hairline structural ruling, stark editorial hierarchy, zero decorative iconography. No generative metaphors (sparks, brains, wizards), no vanity metrics, and no animated transitions.
- **Physical Analogy:** High-grade unbleached rag paper, letterpress black ink, drafting-pen rulings, and crisp typewriter margins.

## Colors

The palette is strictly restrained, modeled after ink on archival stationery with functional, single-purpose chromatic accents.

### Color Assignments
- **Canvas Base (`#f3f1ec`):** Warm unbleached paper tone. Covers the global backdrop and viewport margins.
- **Surface Tier (`#faf9f6`):** Pure ledger surface. Used for case cards, inspected file panels, tabular blocks, and code viewports.
- **Primary Ink (`#1a1814`):** Deep carbon black. Applied to primary prose, section titles, headers, and code syntax base.
- **Secondary Ink / Meta (`#6b6560`):** Graphite neutral. Reserved for structural labels, section numbers, metadata pairs, timestamps, and column dividers.
- **Structural Hairlines (`#e3ddd4`):** Neutral gray-buff line color. Strict 1px rule for dividers, cell frames, and file boundaries.
- **Pine Accent (`#1e4d3a`):** Deep botanical green. Used sparingly for passed state indicators, 2px verified status ticks, active tab markers, and inline editorial links.
- **Brick Accent (`#8c3a2f`):** Muted oxide red. Used strictly for failed executions, regressions, and fatal assertions. Rendered as typographic text only on standard paper surfaces—never as solid fills or warning banners.

## Typography

The type scale orchestrates an editorial balance between academic literature, structured technical documentation, and terminal outputs.

- **Newsreader:** Employed exclusively for case file titles and major investigation headings. It introduces literary stature and pauses the reader’s eye before entering data-dense technical proof.
- **IBM Plex Sans:** Governs the entire operational interface: section index markers, analytical prose, key-value tabular labels, and form controls. Set with calibrated vertical rhythm and balanced weights (Regular 400 for text, Medium 500 / Semi-Bold 600 for micro-labels).
- **Courier Prime:** Applied universally to all machine artifacts: Task IDs (`DEV-8921`), commit hashes (`4f1b8a9`), file paths, code diffs, and raw pytest output traces. Rendered with tabular figures and exact line-height parity to preserve unified vertical grids across columns.

## Layout & Spacing

The layout is anchored to an editorial 1440px desktop viewport utilizing a fixed-column core. The active dossier centers inside a strict `1120px` content container, bordered by calm, unencumbered canvas margins (`margin: 2.5rem`).

### Grid & Structure
- **Core Grid:** 12-column structural grid with `1.5rem` (24px) gutters. Elements strictly lock to multiples of columns (e.g., 8-column reading stream, 4-column metadata sidebar).
- **Section Dividers:** Continuous 1px hairline rules (`#e3ddd4`) running full container width.
- **Section Index Headers:** Prefixed using capitalized numeric indices (e.g., `01 / CONTEXT & ISSUE`, `02 / INSPECTED FILES`, `03 / PATCH & DIFF`, `04 / VERIFICATION & TEST LOGS`). Spaced with `space-xl` prior to the hairline and `space-md` after.
- **Data Tables:** Dense horizontal gridlines with `space-sm` vertical cell padding, preserving maximum scanning velocity without vertical visual traps.

## Elevation & Depth

The design system is strictly two-dimensional and planar. It deliberately forbids all forms of pseudo-spatial depth:
- **No drop shadows, zero ambient glow, zero blurs.**
- **No glassmorphism or translucent surfaces.**
- **Planar Hierarchy:** Hierarchy is produced solely through hairline borders (`1px solid #e3ddd4`), tonal value shifts between canvas (`#f3f1ec`) and surface (`#faf9f6`), and typographic contrast.
- **Depth Metaphor:** Elements sit as physical cut sheets of paper laid upon an architectural cutting mat. Layering is conveyed through horizontal ruling and structural column gutters, never through Z-axis elevation or simulated light sources.

## Shapes

The geometric framework is unyielding, precise, and structural.

- **Radius Definition:** A strict universal `2px` border radius applied uniformly to card bounds, data panels, inputs, and code viewports. (Denoted structurally via level 0 configuration overrides).
- **Edge Geometry:** Crisp, razor-cut edges. No circular badges, rounded pills, or organic radii are permitted under any condition.
- **Rulers & Indicators:** State ticks and markers use 2px square or rectangular bars.

## Components

### Buttons & Actions
- **Primary Action:** Solid background of `#1a1814`, text in `#faf9f6`, 2px border radius. Padding: `8px 16px`. Font: IBM Plex Sans 13px/16px Semi-Bold.
- **Subtle / Secondary Action:** Transparent background, hairline border `1px solid #e3ddd4`, text `#1a1814`. On hover: surface changes to `#faf9f6` with border `#6b6560`.
- **Inline Text Link:** Monospaced or sans-serif underlined with a 1px border offset. Colored with Pine accent (`#1e4d3a`).

### Section Headers
- Formatted as: `[Index Number] / [SECTION TITLE IN UPPERCASE]`.
- Font: IBM Plex Sans, 11px, weight 600, letter spacing `0.12em`, color `#6b6560`.
- Underlaid by a full-width 1px hairline in `#e3ddd4`.

### Record Cards & Dossier Panels
- Surface: `#faf9f6`.
- Border: `1px solid #e3ddd4`.
- Radius: `2px`.
- Padding: `20px 24px`. No shadow. Internal subsections demarcated by internal horizontal hairlines.

### Tabular Data & Lists
- Table headers: IBM Plex Sans, 11px uppercase, color `#6b6560`, border-bottom `1px solid #e3ddd4`.
- Rows: Monospaced file paths and hashes left-aligned; status text right-aligned.
- Hover: Entire row shifts subtly to `#f3f1ec` without transition animation.

### Code Diffs & Terminal Logs
- Panel background: `#faf9f6` framed in `1px solid #e3ddd4`.
- Header: Displays file path in Courier Prime 12px, diff statistics in 11px IBM Plex Sans.
- Diff Lines: Added code indicated with a 2px left border tick of `#1e4d3a` and subtle text contrast; removed code marked with `#8c3a2f` text only. No high-saturation background fills.
- Pytest Logs: Courier Prime 12px. Test run results rendered inline: `PASSED` in `#1e4d3a`, `FAILED` in `#8c3a2f`.

### Form Controls (Checkboxes & Inputs)
- Checkboxes: 14px × 14px square, `1px solid #6b6560`, 2px radius. Active state shows a 2px solid `#1e4d3a` center dot.
- Text Inputs: Background `#faf9f6`, border `1px solid #e3ddd4`, padding `6px 10px`, font IBM Plex Sans 13px. Focus indicator: `1px solid #1a1814` (no outer halo).