---
name: FinVault
description: A private household finance app laid out as a soft sorting room, where imported statements are postmarked, sorted into category pigeonholes, and anything unsorted waits in an amber tray.
colors:
  ground: "#F6F5F2"
  sheet: "#FFFFFF"
  sheet-2: "#F7F6F3"
  wall: "#E6EFEC"
  side: "#EDF4F1"
  side-2: "#E1ECE8"
  ink: "#1B2430"
  ink-2: "#4B5563"
  ink-3: "#5F6773"
  rule: "#ECE9E3"
  rule-2: "#DCD8D0"
  field: "#8F8A80"
  frame: "#1F5E57"
  frame-2: "#184B45"
  frame-soft: "#E4F0EC"
  frame-ink: "#FFFFFF"
  tray: "#E3A43A"
  tray-bg: "#FDF4E1"
  tray-ink: "#8A5A0C"
  post: "#5B5496"
  post-bg: "#EFEDF8"
  green: "#187550"
  green-bg: "#E6F5EC"
  red: "#BE3050"
  red-bg: "#FDECEF"
typography:
  display:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  figure:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  figure-sm:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  title:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "16.5px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14.5px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  body-sm:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.4
  caption:
    fontFamily: "'Figtree Variable', system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  slot: "8px"
  md: "10px"
  cell: "12px"
  lg: "14px"
  dialog: "18px"
  full: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "20px"
  xl: "28px"
  xxl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.frame}"
    textColor: "{colors.frame-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.frame-2}"
    textColor: "{colors.frame-ink}"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-secondary-hover:
    backgroundColor: "{colors.sheet-2}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-danger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.red}"
    rounded: "{rounded.md}"
    height: "38px"
  button-danger-hover:
    backgroundColor: "{colors.red-bg}"
    textColor: "{colors.red}"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    borderColor: "{colors.field}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "40px"
  card:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "20px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "8px 11px"
  nav-item-hover:
    backgroundColor: "{colors.side-2}"
    textColor: "{colors.ink}"
  nav-item-active:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.frame}"
  pill-neutral:
    backgroundColor: "{colors.sheet-2}"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.full}"
    padding: "1px 9px"
  pill-tray:
    backgroundColor: "{colors.tray-bg}"
    textColor: "{colors.tray-ink}"
    rounded: "{rounded.full}"
    padding: "1px 9px"
  pill-post:
    backgroundColor: "{colors.post-bg}"
    textColor: "{colors.post}"
    rounded: "{rounded.full}"
    padding: "1px 9px"
  pill-in:
    backgroundColor: "{colors.green-bg}"
    textColor: "{colors.green}"
    rounded: "{rounded.full}"
    padding: "1px 9px"
  pill-out:
    backgroundColor: "{colors.red-bg}"
    textColor: "{colors.red}"
    rounded: "{rounded.full}"
    padding: "1px 9px"
  tray-head:
    backgroundColor: "{colors.tray-bg}"
    textColor: "{colors.tray-ink}"
    padding: "14px 18px"
  tray-count:
    backgroundColor: "{colors.tray}"
    textColor: "#1B2430"
    rounded: "{rounded.full}"
    height: "30px"
  sort-chip:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    typography: "{typography.caption}"
    rounded: "{rounded.full}"
    padding: "3px 11px"
  sort-chip-hover:
    backgroundColor: "{colors.frame-soft}"
    textColor: "{colors.frame}"
  pigeonhole-wall:
    backgroundColor: "{colors.wall}"
    rounded: "{rounded.lg}"
    padding: "14px"
  pigeonhole:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.cell}"
    height: "200px"
  envelope:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "12px 16px 12px 12px"
  month-pocket-active:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.frame}"
    padding: "7px 16px 8px"
  dialog:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.dialog}"
    width: "540px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.cell}"
    padding: "12px 15px"
---

# Design System: FinVault

## Overview

**Creative North Star: "The Soft Sorting Room"**

FinVault is a household mail-sorting case rendered in soft materials. Each imported statement arrives as an envelope with a circular violet postmark; every line is sorted into a category pigeonhole on a pale teal wall; whatever has no category waits in an amber tray until someone sorts it with one click. The sorting-case ideas carry the meaning, and the softness carries the mood: white rounded sheets on a warm off-white ground, hairline borders, low ambient shadows, one friendly sans in sentence case, and generous space.

The system is calm and domestic rather than financial. There is no hero metric, no gradient, no glass, and no brand-colored chrome beyond a single deep teal for actions and the active place in the nav. Colour is spent on meaning: amber means "waiting to be sorted", violet means "this arrived from a statement", green is money in, rose is money out and over-limit. Category colours come from the household's own data and appear only as soft tints inside pigeonholes and chips. Density is moderate: comfortable 20px card padding, 13px list rows, tabular numerals everywhere so money columns line up.

The world was deliberately softened away from a strict mail-room build that read as too technical. All-caps condensed type, square corners and heavy rules are out; so is a copy of the Securo reference's layout, indigo accent, and icon-tile grammar.

**Key Characteristics:**
- Warm off-white ground (#F6F5F2) under white sheets with 14px corners and #ECE9E3 hairlines.
- One action colour: deep teal (#1F5E57) for primary buttons, links, focus, and the active nav pill.
- Semantic accents only: amber tray, violet postmark, green in, rose out.
- Figtree Variable throughout, sentence case, tabular numerals, weights between 400 and 750.
- Pigeonholes: rounded cells on a pale teal wall whose pastel fill rises toward the budget; over-limit gets a rose ring and a diagonal rose ribbon.
- Flat by default with a whisper of ambient shadow; lift only on hover and for floating layers.
- A full dark theme mirrors every token (`data-theme="dark"`), following the OS preference on first visit.

## Colors

A warm neutral room with one teal voice and three small semantic lamps (amber, violet, green/rose).

### Primary
- **Sorting-Case Teal** (frame): primary buttons, links, focus rings, checked switches and checkboxes, the active nav item's text and icon, the active month pocket, dropzone hover, and the user's chat bubbles. Its hover step is **Deep Case Teal** (frame-2). **Teal Mist** (frame-soft) is its quiet tint for hovered sort chips, the selected palette row, the avatar, and the Canadian-import banner.

### Secondary
- **Tray Amber** (tray): the unsorted tray only. The tray header sits on **Tray Cream** (tray-bg) with **Tray Brown** (tray-ink) text, the count badge is solid amber with dark ink numerals (#1B2430 in both themes; white on amber is only 2.2:1), and the same trio marks an unset category select, the nav's unsorted count, stale-account notes, warning banners, and text selection.

### Tertiary
- **Postmark Violet** (post): postmark stamps on received statements, the "last imported" stamp, savings-goal bars, and info pills and banners on **Violet Wash** (post-bg).

### Semantic
- **Ledger Green** (green) on **Mint Wash** (green-bg): money in, completed import steps, the default progress fill.
- **Rose Out** (red) on **Rose Wash** (red-bg): money out, danger buttons, errors, and the over-budget ribbon and ring on a pigeonhole.

### Neutral
- **Warm Ground** (ground): the page behind everything.
- **Sheet White** (sheet): cards, the tray, pigeonhole cells, envelopes, dialogs, inputs.
- **Sheet Shade** (sheet-2): table headers, hover fills, segmented-control track, empty slots, skeletons, dropzone rest.
- **Pigeonhole Wall** (wall): the pale teal wall behind the pigeonholes and the sign-in aside.
- **Sidebar Tint** (side) with **Sidebar Hover** (side-2): the soft light sidebar and mobile bar.
- **Ink** (ink), **Ink Soft** (ink-2), **Ink Quiet** (ink-3): primary text, secondary text and nav, then labels, meta and placeholders.
- **Hairline** (rule) and **Hairline Firm** (rule-2): card borders and row dividers, then button borders and the month-pocket baseline.
- **Field Line** (field, dark #66726F): the border of inputs, selects, the tag input and the off switch track. It holds 3:1 against the sheet so a field can be found without its label; the softer hairlines stay for sheets and rows.

**Contrast.** Every text pair meets WCAG 2.2 AA (4.5:1, 3:1 for large text) in both themes, and control boundaries, icons and focus rings meet 3:1. Quiet ink (#5F6773) holds 4.7:1 or more on every light surface it sits on, including the sidebar hover and the pigeonhole wall; rose (#BE3050) and green (#187550) hold 4.6:1 or more on their washes and on white. In dark mode, white text never sits on rose or amber: the error toast and the over-budget band use dark ink.

### Named Rules
**The Lamp Rule.** Amber, violet, green and rose are lamps, not paint. Each one appears only where its meaning applies (unsorted, received, in, out/over); never as decoration, section colour, or a second brand accent.

**The One Teal Rule.** Teal is the only colour that means "you can act here" or "you are here". A second action colour is a defect.

**The Household Colours Rule.** Category colours belong to the user's data. They enter the interface only through `--c` as soft `color-mix` tints (10 to 42 percent into the sheet) on pigeonhole labels, fills and sort chips, never as solid fields.

## Typography

**Display Font:** Figtree Variable (with system-ui, -apple-system, Segoe UI, sans-serif)
**Body Font:** Figtree Variable (same stack)
**Label/Mono Font:** ui-monospace, Cascadia Mono, Consolas for recovery codes and inline code only.

**Character:** One rounded, friendly geometric sans at many weights. Hierarchy comes from size and weight steps (400, 500, 550, 600, 650, 700, 750), never from case or a second family.

### Hierarchy
- **Display** (700, 30px, 1.2, -0.02em; 26px under 860px): page titles.
- **Figure** (700, 24px, -0.02em): month totals in the manifest strip; 20px on phones.
- **Figure Small** (700, 20px, -0.01em): the spent amount in each pigeonhole and import stat strips.
- **Title** (650, 16.5px, 1.2): card and section headings; h3 at 15.5px.
- **Body** (400, 14.5px, 1.5): default text; page subtitles cap at 70ch. Links and row titles step up to 550 to 600.
- **Label** (600, 13px): field labels, manifest labels, figure labels, month pockets (13.5px), buttons (14px).
- **Caption** (400, 12.5px): meta lines, table headers (600), dates in the tray, pigeonhole "of budget" text. Nav group labels are 12px/600.

### Named Rules
**The Sentence Case Rule.** Every interface label, heading, button and nav item is sentence case with normal or slightly negative tracking. The one native exception is the postmark stamp itself, whose ring text and month are set in capitals with open tracking because that is what a date stamp is.

**The Tabular Money Rule.** `font-variant-numeric: tabular-nums` is set on `body`; money is always right-aligned in tables and set at 600 to 700 weight.

## Layout

A two-column shell: a sticky 264px sidebar and a fluid main column padded 28px 40px 64px, with page content capped at 1300px and centred. The dashboard reads top to bottom as: a head row (title, last postmark, Import statement at right) over a row of month pockets; a five-cell manifest strip of month totals; the sorting row, a 300 to 370px unsorted tray on the left beside the pigeonhole wall; then received envelopes beside a 320px totals card.

Rhythm is built on 20px: card padding, grid gaps and stack gaps are 20px; card heads are 16px 20px; list rows 13px 20px; the pigeonhole wall uses a 10px gap inside a 14px padded wall; controls sit in 8px gaps. Page heads leave 24px below.

Responsive behaviour:
- **Under 1180px:** the sorting row and received row stack to one column; the manifest drops to three columns.
- **Under 960px:** two-column grids stack; the sign-in aside is hidden.
- **Under 860px:** the sidebar becomes an off-canvas drawer (min(300px, 86vw)) with a scrim and a sticky mobile bar; main padding becomes 20px 16px 48px; the manifest becomes two columns with the last cell spanning; the pigeonhole wall becomes exactly two columns with an 8px gap; forms go single-column; row actions become always visible.

The pigeonhole wall auto-fills 170px-minimum cells on desktop.

## Elevation & Depth

Soft and nearly flat. Sheets carry a two-layer ambient shadow so faint it reads as paper resting on a table, not a floating card. Depth rises only in response to state (hover) or for layers that truly float (dialogs, toasts, the mobile drawer, chart tooltips). Pigeonholes and empty slots add a small inset shadow at the top edge so they read as recessed cells in the wall.

### Shadow Vocabulary
- **Rest** (`0 1px 2px rgba(27,36,48,0.04), 0 2px 8px rgba(27,36,48,0.04)`): cards, tray, envelopes, manifest, active nav pill, active segmented option, search trigger.
- **Hover** (`0 4px 16px rgba(27,36,48,0.08)`): hovered pigeonholes and envelopes.
- **Float** (`0 20px 44px -12px rgba(27,36,48,0.28), 0 4px 10px -4px rgba(27,36,48,0.08)`): dialogs, toasts, chart tooltips, the off-canvas sidebar.
- **Cell recess** (`inset 0 3px 8px -4px rgba(27,36,48,0.12)`, combined with Rest): the pigeonhole cell.
- **Slot recess** (`inset 0 2px 4px rgba(27,36,48,0.1)`): the pocket at the bottom of each pigeonhole.
- **Focus halo** (`0 0 0 3px` teal at 18 percent): focused inputs.

### Named Rules
**The Resting Paper Rule.** At rest, nothing is lifted more than the Rest shadow. Hover may lift a clickable sheet by 2px with the Hover shadow; only floating layers get Float.

**The No Gloss Rule.** No gradients, glass, blur backdrops or glows anywhere in the interface. The only blur is the privacy blur on money values.

## Shapes

Everything is gently rounded, and radius grows with the size of the object: 5px keyboard keys, 8px slots and code chips, 10px controls and nav items, 11px category marks, 12px pigeonhole cells and toasts, 14px sheets, 18px dialogs, full pills for chips, counts, badges, avatars and switches. Month pockets are rounded only on top (10px 10px 0 0) and sit on a hairline like accordion-file dividers.

Borders are 1px hairlines; dashed 1.5px borders mean "open" or "drop here" (an empty budget slot with no limit, the dropzone, the "other category" chip). The postmark is a double-ringed circle rotated -8 degrees. The over-budget ribbon is a 10px rose band rotated -6 degrees across the slot. The logo is a six-hole sorting case with one amber letter.

## Components

### Buttons
Soft, confident, and small-radius; 38px tall (32px small) with 7px icon gaps.
- **Shape:** gently curved (10px).
- **Primary:** teal fill, white text, 600 weight, `0 15px` padding, a faint teal-tinted shadow; hover steps to the deeper teal.
- **Secondary (default):** white sheet with a firm hairline border and ink text; hover to sheet shade.
- **Ghost:** transparent until hover. **Danger:** rose text on white; hover fills rose wash and drops the border.
- **Press / Focus:** press nudges down 1px; focus is a 2px teal outline offset 2px. Disabled drops to 50 percent opacity.
- **Icon button:** 34px square, transparent, quiet ink; `bordered` variant adds a sheet fill and firm hairline.

### Chips
- **Pills:** full-round, 12px/650, tinted wash with matching text: neutral, amber (tray), violet (post), green, rose.
- **Sort chips:** full-round white chips with a hairline and a 7px category dot. The likely category gets a 55 percent category-colour border and a 10 percent tint. Hover turns any chip teal on teal mist. The "other" chip is dashed.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** sheet white on the warm ground.
- **Shadow Strategy:** Rest (see Elevation).
- **Border:** 1px hairline; card heads separated by a hairline.
- **Internal Padding:** 20px (16px on phones).

### Inputs / Fields
- **Style:** 40px tall (34px small), white, field-line border, 10px radius, 12px side padding; selects carry a quiet chevron.
- **Focus:** border turns teal plus a 3px teal halo at 18 percent. Hover darkens the border slightly.
- **Labels:** 13px/600 in ink soft above the control, 6px gap; hints are 12.5px quiet ink. Required fields add a quiet asterisk; errors sit under the field in rose 600 and turn the border rose.
- **Switch:** 38 by 22 full-round track, teal when on.

### Navigation
- **Sidebar:** pale teal tint with a hairline right edge; brand at top, a search trigger with a keyboard hint, grouped links with 12px group labels, the account list with balances, and the member at the foot.
- **Items:** 8px 11px, 10px radius, 550 weight ink soft with 18px quiet icons. Hover fills sidebar hover. Active is a white pill with the Rest shadow, teal text and icon at 650. The unsorted count rides at the right as an amber pill.
- **Mobile:** off-canvas drawer with Float shadow over a scrim; a sticky sidebar-tinted bar holds the menu trigger.
- **Month pockets:** tab-like dividers; the active pocket is white with a firm hairline and teal text.

### Unsorted Tray (signature)
A white sheet whose header is a cream amber band holding the inbox icon, the "To sort" heading, a subline, and a solid amber count badge. Each item shows description and amount, a date line, and a wrap of sort chips. Sorting slides the item out to the right with a slight 2 degree rotation and fade.

### Pigeonhole Wall (signature)
A pale teal wall (14px radius, 14px padding) holding white 12px-radius cells, 200px tall on desktop. Each cell has a full-round tab label tinted with its category colour and a dot, the spent amount at Figure Small, "of budget" in caption, and a recessed slot at the bottom whose fill (42 percent category tint with a 2px category-colour top edge) rises toward the limit with a slow ease-out. No budget shows a dashed open slot. Over budget turns the fill rose, adds a 2px rose ring, a small rose "over" band, and the diagonal rose ribbon. Hover lifts 2px.

### Envelopes and Postmarks (signature)
Received statements are white 14px envelopes (240 to 340px wide) with a 58px violet postmark rotated -8 degrees: account or source around the top ring, "IMPORTED" around the bottom, the day large in the centre and month and year beneath. A 34px mini postmark marks the last import in the dashboard head.

### Manifest Strip
Five equal cells in a single white sheet separated by hairlines: a 13px/600 label, a 24px/700 figure, a 12.5px foot.

### Dialogs and Toasts
Dialogs are white, 18px radius, 540px (780px wide variant), Float shadow, over a 42 percent dark teal-ink backdrop, popping in 8px with a slight scale. Toasts are ink-on-ground 12px pills at bottom right with Float; errors are solid rose.

## Do's and Don'ts

### Do:
- **Do** set every surface on the warm ground (#F6F5F2) with white sheets at 14px radius, 1px #ECE9E3 hairlines and the Rest shadow.
- **Do** reserve teal (#1F5E57) for primary actions, links, focus and the active place in navigation.
- **Do** use amber only for unsorted work, violet only for received statements, green for money in and rose for money out or over budget.
- **Do** tint category colours softly with `color-mix` into the sheet; let the household's colours live inside pigeonholes and chips.
- **Do** keep all interface text in Figtree, sentence case, with tabular numerals and right-aligned money.
- **Do** lift only on hover (2px, Hover shadow) and give Float only to dialogs, toasts, tooltips and the drawer.
- **Do** respect reduced motion; every animation and transition collapses to near zero under `prefers-reduced-motion`, hover lifts stay put, and scripted scrolling jumps instead of gliding. Recharts follows the setting on its own.
- **Do** give every focusable thing a visible 2px teal ring that follows its shape, and every chart a "Show as a table" disclosure with the same numbers.
- **Do** define every new colour for both themes; dark mode is a full mirror, not an afterthought.

### Don't:
- **Don't** add gradients, glass, backdrop blur or glows.
- **Don't** use all-caps or condensed type for labels, headings or buttons; capitals belong only inside the postmark stamp.
- **Don't** square off corners or use heavy rules; hairlines and soft radii are the material.
- **Don't** introduce an indigo or second action accent, or copy the Securo layout of white sidebar, slate ground and icon tiles.
- **Don't** lead a screen with a single hero metric or a grid of icon tiles; the tray and the pigeonhole wall carry the dashboard.
- **Don't** fill large areas with solid category colour or a semantic lamp colour.
