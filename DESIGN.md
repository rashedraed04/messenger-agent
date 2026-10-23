---
name: متجر التقوى — Storefront
description: Arabic RTL catalog of Hajj and Umrah gifts; customers order through Messenger, never through a cart.
colors:
  obsidian: "#0a0a0d"
  obsidian-panel: "#0f0f13"
  obsidian-card: "#141317"
  obsidian-elevated: "#18171b"
  obsidian-deep: "#060608"
  gold: "#d4af37"
  gold-bright: "#ffd700"
  gold-soft: "#e8c766"
  brass: "#aa7c11"
  amber: "#f5a524"
  amber-deep: "#8b6508"
  ink-on-gold: "#1a1408"
  parchment: "#f7f3e8"
  sand: "#a69f8e"
  dune: "#8f8775"
  border-faint: "rgba(212, 175, 55, 0.14)"
  border-gold: "rgba(212, 175, 55, 0.3)"
  border-hover: "rgba(212, 175, 55, 0.65)"
typography:
  display:
    fontFamily: "IBM Plex Sans Arabic, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "3.25rem"
    fontWeight: 700
    lineHeight: 1.3
  headline:
    fontFamily: "IBM Plex Sans Arabic, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "2.1rem"
    fontWeight: 700
  title:
    fontFamily: "IBM Plex Sans Arabic, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "1.2rem"
    fontWeight: 700
  body:
    fontFamily: "IBM Plex Sans Arabic, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontFamily: "IBM Plex Sans Arabic, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "0.88rem"
    fontWeight: 600
  latin:
    fontFamily: "-apple-system, Segoe UI, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 400
rounded:
  tag: "4px"
  badge: "6px"
  control: "10px"
  pill: "12px"
  input: "14px"
  card: "18px"
  panel: "20px"
  full: "9999px"
spacing:
  xs: "0.35rem"
  sm: "0.5rem"
  md: "0.9rem"
  lg: "1.5rem"
  xl: "2rem"
  section: "3.75rem"
components:
  button-messenger:
    backgroundColor: "{colors.amber-deep}"
    textColor: "{colors.gold-soft}"
    rounded: "{rounded.pill}"
    padding: "0.75rem 1rem"
    height: "48px"
  button-primary:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink-on-gold}"
    rounded: "{rounded.control}"
  chip-type:
    backgroundColor: "{colors.obsidian-card}"
    textColor: "{colors.parchment}"
    rounded: "{rounded.pill}"
    padding: "0.55rem 1rem"
    height: "42px"
  chip-type-active:
    backgroundColor: "{colors.obsidian-elevated}"
    textColor: "{colors.gold-bright}"
  chip-category-active:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink-on-gold}"
    rounded: "{rounded.control}"
  input-search:
    backgroundColor: "{colors.obsidian-panel}"
    textColor: "{colors.parchment}"
    rounded: "{rounded.input}"
    padding: "0.9rem 2.9rem 0.9rem 1.25rem"
  card-product:
    backgroundColor: "{colors.obsidian-card}"
    textColor: "{colors.parchment}"
    rounded: "{rounded.card}"
    padding: "0.9rem"
---

# Design System: متجر التقوى

Source of truth: [static/css/storefront.css](static/css/storefront.css) (public site) and [static/css/dashboard.css](static/css/dashboard.css) (admin, "Charcoal & Gold", same gold family on cooler charcoal). This file documents the **storefront**. The dashboard follows the same gold and type rules but is a working tool, so it gets feedback motion only (see Motion).

## Overview

**Creative North Star: "Golden Obsidian"**

A gift shop for pilgrims, presented like a jeweller's display case at night: near-black surfaces, gold used as a thin line rather than a fill, and product photos as the brightest thing on the screen. Its calm comes from restraint. One accent family (gold, brass, amber), one typeface, and depth built from solid surfaces and 1px gold borders instead of glass, glow or gradients across whole sections.

The site is read on phones, mostly opened from a Messenger chat, often on mid-range Android over mobile data. Performance is a design constraint, not an afterthought: no backdrop blur, no CSS filters, no fixed backgrounds, no animation libraries. Arabic and right-to-left (RTL) layout come first; Latin text (brand and English names) is a secondary voice set left-to-right.

The commercial model shapes the UI: **prices are never shown**, and every product ends in a single Messenger call to action. There is no cart, no checkout, and no urgency or scarcity tactics.

**Key Characteristics:**
- Dark, warm-black surfaces (`obsidian` family), never pure `#000` for large areas.
- Gold as hairlines and borders; solid gold fills are reserved for the active category chip and the primary button.
- One typeface (IBM Plex Sans Arabic) carries every Arabic role; hierarchy comes from weight and size.
- Small decorative vocabulary drawn from the product world: palm-drop mark, line-art product illustrations in gold, a centered gold hairline.
- Motion is quick, sparse and composite-only (`transform` and `opacity`).

## Colors

A single warm accent family on warm near-black: gold leads, brass and amber support, and everything else is a neutral.

### Primary
- **Pilgrim Gold** (`gold`): borders at reduced opacity, icons, the English name line, focus rings, the brand name. Gold is the line that defines a surface, not the surface itself.
- **Lamp Gold** (`gold-bright`): hover and active text only (active filter, hovered call to action). Never resting text.
- **Soft Gold** (`gold-soft`): the Messenger call-to-action label, badges, secondary headings such as "منتجات مشابهة".

### Secondary
- **Brass** (`brass`): the deep end of the gold gradient, the illustration bottle neck, category-chip borders.
- **Amber** (`amber`): small warm signals only: the search icon, the stock dot, the Messenger glyph, the active filter value text.
- **Amber Deep** (`amber-deep`) and the `--amber-fill` gradient (`#2a1d06 → #3d2a08 → #241804`): the call-to-action background, a dark ember that reads as gold-tinted without becoming a gold slab.

### Neutral
- **Obsidian** (`obsidian`): page background, and the `theme-color` meta tag.
- **Obsidian Panel / Card / Elevated** (`obsidian-panel`, `obsidian-card`, `obsidian-elevated`): the search field, product cards, chips and focused inputs, in rising lightness.
- **Obsidian Deep** (`obsidian-deep`): the footer and image wells, the darkest surfaces.
- **Parchment** (`parchment`): primary text. Pure `#fff` is used only for product titles.
- **Sand** (`sand`): secondary text, descriptions, breadcrumbs.
- **Dune** (`dune`): placeholders and hashtags, the quietest legible text (5.2:1 on cards; don't go darker).
- **Gold borders** (`border-faint`, `border-gold`, `border-hover`): the three opacities of the one structural line.

### Named Rules
**The Gold Is a Line Rule.** Gold appears as a border, hairline, icon or text. Solid gold fills are limited to the active category chip and `.btn-primary`. If a new component wants a gold background, it is probably wrong.

**The No New Hue Rule.** Success green appears only in the "متوفر" (in stock) check icon. No blues, purples or teal accents, and no neon glows.

## Typography

**Body Font:** IBM Plex Sans Arabic (weights 300–700, loaded from Google Fonts with `display=swap`)
**Latin Font:** system UI stack, for English product names, set LTR and right-aligned so the line ends where the Arabic starts.

**Character:** a humanist Arabic sans: modern and legible, without the ornament of a calligraphic display face. Hierarchy comes from weight and size alone.

### Hierarchy
- **Display** (700, 3.25rem desktop / 1.85rem phone, line-height 1.3): the hero headline only. The whole headline (both brand parts, `sf_hero_title_gold` and `sf_hero_title_white`) is one gold gradient-clipped run (`.hero-title-text`).
- **Headline** (700, 2.1rem / 1.55rem): the product title on the detail page.
- **Title** (700, 1.2rem / 1.1rem): the product name on a card, which is an `<h2>` link.
- **Body** (400, 1.05rem, line-height 1.8–1.9): hero subtitle and detail description, max width about 680px. Card descriptions are 0.86rem at line-height 1.7.
- **Label** (500–600, 0.75–0.9rem): chips, pills, badges, buttons.

### Named Rules
**The Arabic Line-Height Rule.** Arabic body text never drops below line-height 1.7. Diacritics and descenders need the room.

**The One Gradient Text Rule.** Gradient-clipped text appears once per page, in the hero headline. Not on prices, buttons or section titles. It is also the only animated text on the site: a gold current (brass, gold and two pale-gold highlights, repeating every 200%) flows through the whole headline right to left (reading direction), an 8s linear loop. Static under reduced motion; paused while the hero is off screen.

## Layout

Bootstrap 5 RTL container and grid. The catalog grid is 1 column on phones, 2 from `sm`, 3 from `lg` and 4 from `xl`, with `g-4` gutters. The detail page is a 5/7 split from `lg`, image on the right in RTL reading order.

The page rhythm is a sticky navbar, a centered hero (3.75rem top padding, 2.25rem on phones), then the filter section, the results status chip and the grid, ending with the footer. Below 768px, filter pills scroll sideways with snap points instead of wrapping into many rows, trust badges become a 2-column grid, and the navbar's Messenger button collapses to an icon.

Use logical properties (`margin-inline`, `padding-inline`, `inset-inline-*`) for anything new so RTL stays correct.

## Elevation & Depth

Mostly flat, with tonal layering. Depth comes from surfaces stepping from `obsidian` to `obsidian-elevated` and from 1px gold borders, not from shadows.

### Shadow Vocabulary
- **Card rest** (`box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35)`): product cards only, to separate them from the page.
- **Navbar seam** (`box-shadow: 0 1px 0 rgba(0, 0, 0, 0.6)`): under the sticky header.
- **Focus halo** (`box-shadow: 0 0 0 3px rgba(212, 175, 55, 0.15)`): the focused search field.
- **Inner highlight** (`box-shadow: inset 0 1px 0 rgba(255, 215, 0, 0.12)`): the top edge of the Messenger call to action.

### Named Rules
**The No Glass Rule.** No `backdrop-filter`, no `filter: blur()`, no large glowing shadows. They are the most expensive paint on low-end phones and the most generic look on the web.

## Shapes

Soft rectangles whose radius grows with the size of the object: tags 4px, badges 6px, controls 10px, pills and the call to action 12px, the search field 14px, cards 18px, the detail image 20px. Fully round (9999px) is reserved for small inline chips such as category tags, the header badge and detail chips.

Cards carry a **gold hairline crown**: a 1px gradient line along the top edge, inset 12% from each side, fading out at both ends. It is the system's signature detail, and also appears under the hero.

## Components

### Buttons
- **Messenger call to action:** the one action on every product. Dark ember fill (`--amber-fill`), 1px gold border at 70%, `gold-soft` label, Messenger glyph in amber, 48px minimum height. On hover: lamp-gold text and border, slightly brighter ember. On press: scales to 0.97.
- **Primary:** gold gradient fill with `ink-on-gold` text. Only in empty states.
- **Nav buttons:** gold outline (`.btn-nav-gold`) or faint outline (`.btn-nav-ghost`), 40px minimum height.

### Chips
- **Type pills:** card surface, faint border, gold icon. Active: gold border, 12% gold tint, lamp-gold text.
- **Category pills:** darker (`#1c1b1f`) with a brass border. Active: solid gold gradient fill, the one permitted gold slab.
- **Tags:** category tag (round, gold tint), brand tag (black, uppercase Latin, LTR), size badge (on the image, bottom-left), hashtag badge (quietest).

### Cards / Containers
- **Product card:** 18px radius, a vertical gradient from `#1a181b` to `obsidian-card`, a gold border at 28%, the hairline crown and the card rest shadow. It contains the head (brand and category tags), an image well (190px, 170px on phones), the title, the Latin name, a description, up to four hashtags, and the call to action pinned to the bottom.
- **Image well:** a dark well with a faint gold radial when there is no photo. Products without photos show a gold line-art illustration chosen by product kind (bottle, gift, rug, beads, book, garment, dates).

### Inputs / Fields
- **Search:** `obsidian-panel` fill, gold border at 30%, 14px radius, amber search icon at the inline start. Focus: elevated fill, full gold border, gold halo. Results update live with a 300ms debounce.

### Navigation
- **Navbar:** sticky solid header (`#0d0d10`). Logo on a white rounded tile, gold store name, sand tagline and location. A desktop-only header badge with the palm-drop mark.
- **Footer:** `obsidian-deep` background, outlined gold chips, and a deliberately faint lock icon linking to the admin area.

### Motion
Motion explains state and continuity. It is never decoration for its own sake.

- **Tokens:** `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)` for entering and feedback; `--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)` for movement on screen.
- **Press feedback:** buttons and pills scale to 0.97 over 160ms. This is the only motion on the dashboard.
- **Product to detail continuity:** the card's image well and the detail image share a `view-transition-name` (`product-<id>`), so tapping a product carries its image into the detail page, and Back (or the breadcrumb) carries it home. Only the tapped card is named (`data-vt`, set on click by motion.js; the return trip is named by the inline `pagereveal` script in the layout), so navigations never snapshot the whole grid. Browsers without support simply navigate.
- **Detail arrival:** the product details rise 8px and fade in reading order, 40ms apart (capped at 240ms), alongside the image carry-over.
- **Hero arrival:** title, subtitle and trust badges rise 8px and fade in, staggered 60ms, and the gold hairline under the hero draws outward from the center. Once per page load, under 700ms in total.
- **Page flux lines** ([static/js/flux-lines.js](static/js/flux-lines.js)): the site's one ambient loop, the catalog's background. A plain-JS port of React Bits' FluxLines (shader unchanged): glowing gold lines (`#aa7c11 → #d4af37 → #fbe7a1`) tracing a churning fluid that drifts down, at 60% opacity, on a fixed `.page-flux` layer behind the page (z-index -1). The solid hero, header, cards, controls and footer cover it, so it shows in the margins and between cards. On a fine pointer the cursor is a magnet that reveals and curls the lines; a click or tap stirs a swirl. WebGL2, no library; the shader compiles on idle after first paint and fades the lines in over 1.8s; without WebGL2 the page stays plain. It fills the screen, so it renders at most 1.5x density (1x on touch) and touch devices run at 30fps; the canvas is sized to `100lvh` so the phone URL bar never resizes it. It sleeps in hidden tabs. Quality is judged against the page's own best pace, not 60fps, because Energy Saver and battery modes legitimately cap pages at 30fps: only frames arriving 35% behind that pace count as dropped, which steps resolution down (2 → 1.5 → 1 → 0.75 → 0.5), and a smooth 30 seconds steps it back up. It never freezes on its own; a GPU driver reset (`webglcontextlost`) rebuilds the program when the context returns. Reduced motion or Save-Data get one still frame. Tune it through `SETTINGS` (React Bits prop names).
- **Scroll reveal:** only cards that start **below the fold** fade and rise 12px when they enter the viewport, once each, staggered up to 4 per batch; then the card's gold crown line draws out from the center. Cards visible on load never wait. On a fine pointer, hovering a card stretches the crown line across (`scaleX(1.25)`).
- **Hero palms** ([static/js/palms.js](static/js/palms.js)): two gold line-art date palms, drawn as SVG in code (no image files), laid out as the Golden Palm ambient background: each 85% of the hero's height, sunk 40px below its bottom and 60px past each side, leaning 8° inward, at 28% opacity, fading in over 0.5s once built on idle. Behind them a static ambient glow: gold pools at 10% and 90% across (60% down) and a soft ellipse rising from the bottom. The halo around fronds and trunks is drawn into the SVG (wide, faint gold strokes under the lines) rather than a CSS `drop-shadow`, so nothing is re-filtered while the fronds sway; no `mix-blend-mode` (identical to normal blending on near-black). Scrolling is wind: scroll speed drives two springs, a quick one that lifts each frond (scroll down) or presses it down (scroll up), and a slow one that leans the crowns; when the page stops they spring back with a small overshoot. Each frond is its own composited layer turned by a shared CSS variable; the loop runs only while the springs are moving and the hero is on screen. palms.js also pauses the title gradient while the hero is off screen. Reduced motion gets still palms. They never move on their own.
- **Scroll-linked (CSS scroll timelines, no JS, still where unsupported):** the header's shade fades in over the first 96px of scroll; the hero recedes (fade and scale to 0.96, never a parallax offset) as it leaves; on phones the pill rows show edge fades that track how far the row has been swiped. Scroll-linked motion is only for these three relationships.
- **Results swap:** while live search loads, the grid dims to 45% and returns to full opacity over 150ms. Cards already on screen settle in (240ms, 6px, 30ms apart); new cards below the fold join the scroll reveal. Grid photos fade in once decoded instead of popping.
- **Sticky order bar (product page, below `lg`):** once the main Messenger button scrolls above the viewport, a bar with the product name and the button slides up from the bottom (280ms in, 200ms out), respecting the safe-area inset.
- **Card hover:** the card rises 4px and scales to 1.03 with a deeper shadow (320ms, `--ease-out`), and its photo zooms to 1.06 inside the well (500ms). Only with a fine pointer (`hover: hover` and `pointer: fine`), so taps never leave a stuck state.
- **Reduced motion:** with `prefers-reduced-motion: reduce`, all movement, the scroll-linked hero recede and the view transition are removed; color and border state changes, the header shade and the pill edge fades remain, and the sticky order bar fades instead of sliding.

## Do's and Don'ts

### Do:
- **Do** animate only `transform` and `opacity`; use `clip-path` only in small isolated regions.
- **Do** keep UI feedback under 300ms, and use the system's `--ease-out` rather than the built-in `ease-out`.
- **Do** keep content visible when JavaScript fails. Reveal styles are applied by script, never by default CSS.
- **Do** gate hover motion behind `@media (hover: hover) and (pointer: fine)`.
- **Do** keep every product ending in the single Messenger call to action, labelled from `brand.sf_cta_label`.
- **Do** test new UI with long Arabic names, missing photos, missing descriptions and a single result.

### Don't:
- **Don't** show prices, discounts, countdowns or "only 2 left" scarcity badges.
- **Don't** add animation libraries (GSAP, Framer Motion, AOS). CSS and IntersectionObserver cover this site.
- **Don't** use parallax, scroll-jacking, bouncing or elastic easing, typewriter text, shimmer or skeleton sweeps on text (the hero's gold sheen is the single exception), or particle and confetti effects.
- **Don't** add a second ambient loop. The hero flux lines are the only continuously running animation; anything new reacts to an action or a scroll, then stops.
- **Don't** fade in every section on scroll. Reveal is for the product grid only.
- **Don't** use emoji as icons; use Bootstrap Icons or the store's own SVGs.
- **Don't** introduce a second typeface for Arabic, or set Arabic in Latin-only fonts.
- **Don't** use glassmorphism, neon glows, or purple-to-blue gradients.
