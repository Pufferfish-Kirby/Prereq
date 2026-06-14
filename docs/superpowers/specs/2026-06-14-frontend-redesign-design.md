# MyUofT Frontend Redesign — Design Spec

**Date:** 2026-06-14
**Scope:** Frontend only (`frontend/`). No backend changes.

## Goal
Elevate the MyUofT frontend from a plain three-tab tool into a polished product
with a real landing page, a ChatGPT-style streaming typing effect in the AI
Advisor, and proper browser-tab branding (title + custom favicon).

## Decisions (confirmed with user)
- **Typing effect:** Simulated client-side reveal (no backend/SSE changes).
- **Landing page:** A default `home` view inside the existing single-page app
  (no router / new deps).
- **Favicon:** Hand-crafted graduation-cap SVG in UofT blue (no raster image).
- **Visual direction:** Polish the existing minimalist UofT-blue identity, not a
  bold restyle.

## Work items

### 1. Landing page (new default `home` view)
- Add a `'home'` view; change default `activeTab` from `'planner'` to `'home'`
  (`App.jsx:25`). Add `Home` to the navbar tab switcher (`App.jsx:272`) and make
  the logo click return home.
- **Hero:** "MyUofT", tagline "Turn a 20-minute conversation into a 4-year plan",
  one-paragraph problem explainer (thousands of courses across St. George / UTM /
  UTSC), two CTAs: **Get Started** → Planner, **Talk to the AI Advisor** → Chat.
- **Features strip:** three cards (Course Planner, AI Advisor, Course Reviews),
  each icon + one-line description.
- Deeper UofT-blue gradient background, subtle fade/slide-in on load, refined type.

### 2. Simulated typing effect (AI Advisor)
- On a freshly-received assistant reply, reveal text progressively (word chunks,
  blinking cursor), then settle into full markdown render.
- Tag new replies with an `animate` flag so loading past sessions
  (`loadChat`, `App.jsx:96`) renders instantly and history never re-types.
- Keep auto-scroll following the growing text (`messagesEndRef`).

### 3. Tab title + favicon
- `index.html:7` `<title>frontend</title>` → `<title>MyUofT</title>`; add
  `theme-color` and `apple-touch-icon`.
- Replace `frontend/public/favicon.svg` with a graduation-cap SVG on a rounded
  UofT-blue tile (visible on light and dark tabs).

### 4. Visual polish
- Refine navbar, card depth/shadows, type scale, and transitions across all tabs;
  keep the minimalist UofT-blue look.

## Constraints
- Match the real codebase: plain **JSX** (not TS), Tailwind utilities, existing
  `bg-uoft-blue` custom color, 2-space indentation.
- Per CLAUDE.md: add detailed "why" comments explaining design decisions inline.
- Do not change backend endpoints or response shapes.
