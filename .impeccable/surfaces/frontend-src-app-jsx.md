---
version: 1
slug: "frontend-src-app-jsx"
primary_target: "frontend/src/App.jsx"
related_targets: []
---

Scope: the whole FinVault web app shell and all its screens. Visitor mode: Operate.
Audience: a household on a home server; monthly import-and-tidy ritual on desktop, quick checks on phone.
Constraints: a mix the user asked for: Securo's softness with the Sorting Case ideas, never a copy of Securo's layout or indigo. Avoid bank/fintech gloss, gamification, spreadsheet density, clinical grey.

## Direction contract

THESIS: FinVault is a household mail-sorting case. Each imported statement arrives postmarked; every line is sorted into a category pigeonhole; whatever is unsorted waits in the tray. Refuses the white-card fintech dashboard with a hero metric and icon tiles.
OWN-WORLD: Soft sorting room. Warm off-white ground #F6F5F2, white cards with 14px radius, #ECE9E3 hairlines and soft shadows (the Securo softness the user asked to keep). Deep teal #1F5E57 accent for actions and the active nav, amber #E3A43A for the unsorted tray, postmark violet #5B5496 for stamps, green #1F8A5B money in, rose #D6455D money out. Figtree throughout, sentence case, tabular numerals. Pigeonholes are rounded cells on a pale teal wall #E6EFEC, each with a soft tab label and a pastel fill to its budget; over-limit gets a rose ribbon. No gradients or glass.
STORY: The member sees what arrived, sorts the tray in a few clicks, reads each pigeonhole's fill against its budget, then imports the next statement.
FIRST VIEWPORT: Soft light sidebar at left (pale teal tint, rounded nav, teal active pill) with the account list. Main: month label strip with Import statement at right; left column is the Unsorted tray (uncategorized lines with one-click sort); right is the pigeonhole wall, one cell per spending category showing spent and a stack-height fill against its budget; below, postmarked received statements and the month's in/out/net totals.
FORM: grounded pick "Sorting Case" softened toward the Securo reference at the user's request (mix), seed key 524639eb re-roll 1.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
