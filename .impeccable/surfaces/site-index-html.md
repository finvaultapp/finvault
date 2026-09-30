---
version: 1
slug: "site-index-html"
primary_target: "site/index.html"
related_targets: ["site/styles.css", "site/site.js"]
---

Scope: the public FinVault landing site, a static page in `site/` (no build step). Visitor mode: Persuade.
Audience: Canadian households, often a couple, who are privacy-minded and wary of apps that ask for their bank password. They arrive from a link, decide in a minute whether to self-host, and some read French first.
Constraints: the user asked for "the same landing website" as usesecuro.com. The section order and devices follow it: a stacked multi-line headline with an accented last line, a rotating product card, a bank strip, a "where your data lives" flow, a live screenshot viewer with a theme toggle, the features as a sorting case (the app's four menu groups as pigeonhole cells) with a status pill per feature (built in, or optional and off), three install steps with copy buttons, and a footer. The copy, the data, the materials and the brand are FinVault's own; no Securo text, logo or indigo. No invented testimonials, user counts, stars or benchmarks (PRODUCT.md: evidence on hand is none). Every claim must match a README feature that has shipped.

## Direction contract

THESIS: the same soft sorting room as the app, shown to a stranger. The hero card is a working piece of the app (tray, pigeonholes, registered room, shared costs, ask), not a generic dashboard mock.
OWN-WORLD: the app's DESIGN.md tokens in both themes (warm ground, white sheets, teal for actions, amber tray, violet postmark and file formats, green in, rose out, pale teal wall for "your server" and the Canada band). Figtree, sentence case, tabular numerals; the postmark is the only place for capitals.
PERSUADE ALLOWANCES (deliberate departures from the app's Operate ramp):
- Type ramp: headline clamp(40px, 5.6vw, 72px) at 780; section titles clamp(30px, 4vw, 44px) at 750; lede 19px; section subs 17.5px; hero figures 34px (28px on phones); flow node titles 21px; body 16px.
- Radii: the app scale (8, 10, 12, 14, 18, full) plus 16px for mid-size marketing cards and 20 to 22px for the two large framed objects (hero stage, browser frame).
- The teal accent colours the last headline line, the one brand gesture beyond actions.
- Float shadow on the hero stage and the browser frame, the two objects that sit above the page.
STORY: read the promise, see the tray sort itself in the card, learn that only a file crosses from the bank, look at the real screens (phone-width captures on phones), scan features, see the Canadian specifics, get the five questions a privacy-minded household asks before installing (bank password, where data lives, two people, moving from another app, AI) answered in "Good to know" in place of Securo's business-contact block, which FinVault has no contact details for, then copy three commands.
FIRST VIEWPORT: on phones and tablets a menu button replaces the header links. Stacked headline and lede with two actions at left; the rotating app card at right with five tabs, a progress tick, the tray visibly sorting one line into Groceries (the one authored motion), pause on hover or focus, stop on any direct use, and no rotation under reduced motion.
FONT: Figtree Variable self-hosted from site/fonts (OFL); the page makes no third-party requests.
LANGUAGE: English and Canadian French. French is chosen from the browser language or the toggle and remembered; money formats follow the language.
FORM: code-led surface of the app's world; no concept roll of its own. Inherits the app contract's grounded pick "Sorting Case", seed key 524639eb re-roll 1 (see frontend-src-app-jsx.md).
FINISH: detector clean of real quality findings, the finish review, then commit.
