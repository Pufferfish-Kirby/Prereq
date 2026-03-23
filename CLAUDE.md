# MyUofT — AI-Powered Course Planning for University of Toronto Students

## Project Overview

MyUofT is an AI-powered course planning tool that helps University of Toronto students navigate the overwhelming number of courses, minors, majors, and specialist programs available across all three campuses (St. George, UTM, UTSC). The tool understands student preferences, academic goals, and degree requirements, then generates personalized long-term academic plans.

**Core value proposition:** Students shouldn't need to spend weeks parsing the Academic Calendar to figure out what to take. MyUofT turns a 20-minute conversation into a 4-year plan.

---

## Tech Stack

### Current (Phase 1 — Local MVP)
- **Frontend:** React with TypeScript (Vite)
- **Backend:** Python with FastAPI
- **Database:** SQLite (via SQLAlchemy ORM)
- **AI:** Anthropic Claude API (claude-sonnet-4-20250514) for conversational course advising
- **Styling:** Tailwind CSS

### Future (Phase 2+ — Production)
- **Database:** PostgreSQL (on AWS RDS)
- **Cloud:** AWS (EC2/ECS for compute, S3 for static assets, CloudFront CDN)
- **Auth:** Clerk or Auth0
- **Caching:** Redis for session state and AI response caching
- **Search:** Embeddings-based semantic search over course descriptions (pgvector)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                 Frontend (React + TS)        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Chat UI  │ │ Plan View│ │ Course Search│ │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       └─────────────┼──────────────┘         │
│                     │ REST API               │
├─────────────────────┼───────────────────────-┤
│              Backend (FastAPI)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Chat     │ │ Planner  │ │ Course Data  │ │
│  │ Service  │ │ Service  │ │ Service      │ │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       │             │              │         │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴───────┐ │
│  │Claude API│  │ SQLite   │  │Course Data │ │
│  │          │  │ (Plans)  │  │ (JSON/DB)  │ │
│  └──────────┘  └──────────┘  └────────────┘ │
└──────────────────────────────────────────────┘
```

---

## Data Sources for UofT Course Information

Course data should be scraped or imported from:
1. **UofT Academic Calendar** — https://artsci.calendar.utoronto.ca/ (course descriptions, prerequisites, exclusions, program requirements)
2. **Timetable Builder** — https://ttb.utoronto.ca/ (scheduling, sections, enrollment)
3. **Existing open-source scrapers** (reference, not dependency):
   - `cobalt-uoft/uoft-scrapers` — Python scrapers for courses, buildings, etc.
   - `UofT-Course-Tools` GitHub org — GraphQL backend, program scraper, course eval scraper
   - `nikel-api` — REST API with course, program, and textbook data
4. **Program/degree requirements** — scraped from calendar pages per department

### Course Data Schema (target)
```
Course:
  code: str           # e.g., "CSC108H1"
  name: str           # e.g., "Introduction to Computer Programming"
  description: str
  campus: str         # "St. George" | "UTM" | "UTSC"
  department: str
  division: str       # "Faculty of Arts and Science", etc.
  prerequisites: str  # raw text
  corequisites: str
  exclusions: str
  breadth_category: str
  distribution: str
  credit_weight: float  # 0.5 or 1.0
  terms_offered: list[str]  # ["F", "S", "Y"]
  tags: list[str]     # AI-generated topic tags for search
```

---

## Coding Conventions

### Python (Backend)
- Python 3.11+
- Use `ruff` for linting and formatting
- Type hints on all function signatures
- Pydantic models for request/response validation
- Async endpoints where appropriate (especially AI calls)
- Tests with `pytest`; aim for service-level tests, not just unit tests
- Environment variables via `.env` files loaded with `python-dotenv`
- Keep route handlers thin — business logic goes in service modules under `app/services/`

### TypeScript (Frontend)
- Strict TypeScript — no `any` types unless absolutely unavoidable
- Functional components with hooks only (no class components)
- Use `fetch` or `axios` for API calls, wrapped in custom hooks
- Component structure: `components/`, `pages/`, `hooks/`, `types/`, `utils/`
- Use Tailwind CSS utility classes; avoid custom CSS files
- State management: React Context for global state initially; consider Zustand if it grows

### General
- All files use 2-space indentation (frontend) or 4-space (Python backend)
- Descriptive variable names — no single-letter variables except loop counters
- Comments explain "why", not "what"
- Git commit messages: conventional commits format (`feat:`, `fix:`, `refactor:`, `docs:`)
- Never commit `.env` files, API keys, or secrets
- Always include error handling for API calls and database operations

---

## Project Structure

```
myuoft/
├── CLAUDE.md
├── README.md
├── .env.example
├── .gitignore
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Settings and env vars
│   │   ├── database.py          # SQLAlchemy engine and session
│   │   │
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── course.py
│   │   │   ├── program.py
│   │   │   ├── user.py
│   │   │   └── plan.py
│   │   │
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── course.py
│   │   │   ├── chat.py
│   │   │   └── plan.py
│   │   │
│   │   ├── routers/             # API route handlers
│   │   │   ├── __init__.py
│   │   │   ├── courses.py
│   │   │   ├── chat.py
│   │   │   ├── plans.py
│   │   │   └── programs.py
│   │   │
│   │   ├── services/            # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── ai_advisor.py    # Claude API integration
│   │   │   ├── course_search.py
│   │   │   ├── plan_generator.py
│   │   │   └── prerequisite_checker.py
│   │   │
│   │   └── data/                # Static data, scraped JSON, seed scripts
│   │       ├── courses.json
│   │       └── programs.json
│   │
│   ├── scripts/
│   │   └── scrape_calendar.py   # Course data scraper
│   │
│   ├── tests/
│   │   ├── test_courses.py
│   │   ├── test_chat.py
│   │   └── test_plans.py
│   │
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   │
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   └── SuggestionChips.tsx
│   │   │   ├── Plan/
│   │   │   │   ├── PlanTimeline.tsx
│   │   │   │   ├── SemesterCard.tsx
│   │   │   │   └── CourseSlot.tsx
│   │   │   ├── Search/
│   │   │   │   ├── CourseSearch.tsx
│   │   │   │   └── CourseCard.tsx
│   │   │   └── Layout/
│   │   │       ├── Navbar.tsx
│   │   │       └── Sidebar.tsx
│   │   │
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── ChatPage.tsx
│   │   │   ├── PlanPage.tsx
│   │   │   └── ExplorePage.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── useChat.ts
│   │   │   ├── useCourses.ts
│   │   │   └── usePlan.ts
│   │   │
│   │   ├── types/
│   │   │   ├── course.ts
│   │   │   ├── chat.ts
│   │   │   └── plan.ts
│   │   │
│   │   └── utils/
│   │       ├── api.ts           # API client wrapper
│   │       └── formatters.ts
│   │
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── vite.config.ts
│
└── docs/
    ├── plans/                    # Claude Code plan files
    ├── architecture.md
    └── data-model.md
```

---

## AI Integration Details

### Model Selection
- **Conversational advising (chat):** `claude-sonnet-4-20250514` — fast, cheap, good at dialogue
- **Complex plan generation:** `claude-sonnet-4-20250514` with extended system prompt — for generating multi-year plans with constraint satisfaction
- **Embeddings for course search:** Use `voyage-3` or OpenAI `text-embedding-3-small` to embed course descriptions, then store in SQLite (Phase 1) or pgvector (Phase 2)

### System Prompt Strategy
The AI advisor should receive:
1. A system prompt explaining it is a UofT academic advisor
2. Relevant course data injected as context (filtered by student's expressed interests)
3. The student's current academic state (year, completed courses, declared programs)
4. Degree requirements for their declared or prospective programs

### Key AI Features
- **Preference Discovery Chat:** Conversational flow that asks about interests, career goals, course load preferences, schedule constraints
- **Plan Generation:** Takes preferences and outputs a semester-by-semester plan
- **Prerequisite Validation:** Checks that the generated plan respects all prerequisites
- **Course Recommendations:** "Students who liked X also took Y" style suggestions
- **What-If Analysis:** "What would my plan look like if I switched from CS Major to CS Specialist?"

---

## Development Phases

### Phase 1: Local MVP (Current)
- [ ] Scrape and store Arts & Science course data (St. George)
- [ ] Basic FastAPI backend with course search endpoint
- [ ] Simple chat interface that talks to Claude API
- [ ] Generate a basic 4-year plan from chat preferences
- [ ] SQLite database for courses and generated plans
- [ ] React frontend with chat UI and plan display

### Phase 2: Smart Planning
- [ ] Prerequisite graph and validation
- [ ] Program requirement tracking (major/minor/specialist)
- [ ] Embeddings-based semantic course search
- [ ] Improved plan generation with constraint satisfaction
- [ ] User accounts and saved plans

### Phase 3: Multi-Campus & Scale
- [ ] UTM and UTSC course data
- [ ] PostgreSQL migration
- [ ] AWS deployment
- [ ] Redis caching for AI responses
- [ ] Rate limiting and usage tracking

### Phase 4: Community Features
- [ ] Course reviews and ratings from students
- [ ] Plan sharing and templates
- [ ] Integration with UofT Timetable Builder for scheduling
- [ ] Mobile-responsive redesign

---

## Common Mistakes to Avoid

- **Don't over-engineer early.** SQLite is fine for Phase 1. Don't set up PostgreSQL, Redis, and Kubernetes before the chat works.
- **Don't send the entire course catalog to Claude.** Filter courses by department/interest first, then include only relevant ones in the prompt context.
- **Don't trust AI output blindly.** Always validate generated plans against prerequisite data programmatically.
- **Don't scrape UofT in production.** Scrape once, store as JSON/DB, update periodically. Don't hit their servers on every request.
- **Don't forget about breadth requirements.** UofT Arts & Science has specific breadth/distribution requirements that must be satisfied — the planner must account for these.
- **When generating code, add detailed comments explaining WHY each piece exists, not just what it does. Explain design decisions inline.** I still want to be learning a lot from this project so this is important.

---

## Environment Variables

```
# .env.example
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=sqlite:///./myuoft.db
ENVIRONMENT=development
LOG_LEVEL=info
CORS_ORIGINS=http://localhost:5173
```

---

## Commands Reference

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Scraping
cd backend
python scripts/scrape_calendar.py

# Tests
cd backend
pytest tests/ -v
```
