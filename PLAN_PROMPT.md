# Claude Code Plan Prompt — MyUofT Project Initialization

## How to Use This File

Copy the prompt below into Claude Code. Before pasting, do the following:

1. **Set effort to max:** Run `/effort max` in Claude Code
2. **Enter plan mode:** Press `Shift+Tab` to toggle into Plan Mode
3. **Paste the prompt below**
4. **Review the plan** Claude generates, ask follow-up questions, then press `Shift+Tab` again to switch to execution mode and let it build

---

## The Prompt

```
ultrathink + plan mode

I'm building MyUofT — an AI-powered course planning tool for University of Toronto students. Read my CLAUDE.md file first for full project context, tech stack, architecture, and conventions.

Here's what I need you to plan for the INITIAL SCAFFOLDING (Phase 1 MVP only):

### 1. Backend Scaffolding (FastAPI + Python)
Plan the complete backend structure:
- FastAPI app with proper project layout matching CLAUDE.md structure
- SQLAlchemy models for Course, Program, User, and Plan
- Pydantic schemas for all request/response types
- Router stubs for /courses, /chat, /plans, /programs
- A service module for Claude API integration (ai_advisor.py) that:
  - Accepts a chat message + conversation history
  - Includes a system prompt positioning Claude as a UofT academic advisor
  - Sends relevant course data as context
  - Returns a structured response
- A basic course search service with text filtering
- Database initialization script
- Config module loading from .env
- requirements.txt with pinned versions
- A sample courses.json with 20-30 real UofT CS courses (CSC108, CSC148, CSC207, CSC236, CSC258, CSC263, CSC369, CSC373, MAT135, MAT136, MAT223, MAT235, MAT237, STA237, STA247, etc.) including accurate prerequisites and descriptions from the UofT Academic Calendar

### 2. Frontend Scaffolding (React + TypeScript + Vite)
Plan the frontend setup:
- Vite + React + TypeScript project
- Tailwind CSS configuration
- Component structure matching CLAUDE.md
- A working Chat page with:
  - Message input and display
  - Streaming-ready architecture (even if not streaming yet)
  - Suggestion chips for common questions
- A Plan page with:
  - Semester-by-semester grid/timeline view
  - Course cards that show code, name, and credit weight
- A simple Course Search/Explore page
- API client utility for backend communication
- TypeScript types matching backend schemas
- React Router for navigation between pages

### 3. Data Layer
Plan the data pipeline:
- A Python scraper script that can pull course data from the UofT Academic Calendar (artsci.calendar.utoronto.ca)
- How to structure the scraped data as JSON for seeding
- SQLite database setup with proper migrations approach
- Seed script to load courses.json into the database

### 4. Integration
Plan how the pieces connect:
- CORS configuration between frontend (port 5173) and backend (port 8000)
- The full request flow: user sends chat message → backend receives → backend calls Claude API with course context → response sent back → frontend displays
- How the plan generation works end-to-end: chat extracts preferences → service queries relevant courses → Claude generates plan → plan is validated and stored

### Important Constraints:
- This is Phase 1 ONLY. No PostgreSQL, no Redis, no AWS, no auth. SQLite and local dev.
- Use claude-sonnet-4-20250514 as the model for the AI advisor
- Keep the AI prompts focused — don't dump the entire course catalog into context. Filter by relevance.
- All Python code must have type hints
- All TypeScript must be strict (no `any`)
- Include error handling for API calls, database operations, and AI responses
- Create a .env.example file
- Create a proper .gitignore

Think through this carefully. Consider edge cases, the order of implementation, and dependencies between components. Create a detailed, step-by-step plan I can review before you write any code.
```

---

## After the Plan is Approved

Once you've reviewed and approved the plan, switch to execution mode (`Shift+Tab`) and tell Claude:

```
Execute the plan. Start with the backend scaffolding, then the frontend, then wire them together. Create all files, install dependencies, and make sure both servers start without errors. After each major section, pause and let me verify before continuing.
```

---

## For Subsequent Features

After the scaffold is built, use these focused prompts for each feature:

### Adding the Course Scraper
```
think hard + plan mode

Read CLAUDE.md. I need you to build the course scraper (backend/scripts/scrape_calendar.py). It should:
1. Scrape Arts & Science course data from artsci.calendar.utoronto.ca
2. Extract: code, name, description, prerequisites, exclusions, breadth category, distribution, credit weight
3. Handle pagination and rate limiting (be respectful, 1-2 second delays)
4. Output to backend/app/data/courses.json
5. Include a seed script that loads this JSON into SQLite

Plan the scraper architecture, then I'll approve before you build it.
```

### Adding Prerequisite Validation
```
think hard + plan mode

Read CLAUDE.md. I need a prerequisite checking service. It should:
1. Parse prerequisite strings from course data (e.g., "CSC148H1/CSC150H1, MAT135H1/MAT136H1/MAT137Y1")
2. Build a prerequisite graph
3. Given a student's completed courses, validate whether they can take a target course
4. Given a generated plan, validate all courses in sequence respect prerequisites
5. Return specific errors like "CSC263 in Year 2 Fall requires CSC236, which isn't scheduled until Year 2 Winter"

Plan the data structures, parsing approach, and validation algorithm.
```

### Adding Embeddings-Based Course Search
```
ultrathink + plan mode

Read CLAUDE.md. I want to add semantic search over courses. Plan:
1. Which embedding model to use (voyage-3 vs OpenAI text-embedding-3-small vs local model)
2. How to embed all course descriptions + generate topic tags
3. Storage approach for Phase 1 (numpy arrays in memory or SQLite with a vector extension)
4. Search endpoint that takes natural language ("I want to learn about machine learning") and returns ranked courses
5. How this integrates with the existing course search and the AI advisor context selection
```
