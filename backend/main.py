# Remember to call venv/Scripts/activate to get here
# Also run uvicorn main:app --reload --port 8000
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from scoring import recommend_courses, explain, courses as course_catalog

# FastAPI() — note the parentheses. Without them `app` would be the class itself,
# not an instance, so every method call below would crash at startup.
app = FastAPI()

# CORSMiddleware lets the browser make requests from the React dev server
# (localhost:5173) to this API (localhost:8000). Without it, browsers block
# all cross-origin requests before they even reach our route handlers.
# WHY a specific origin instead of "*":
#   The CORS spec forbids combining allow_origins=["*"] with
#   allow_credentials=True — browsers reject the response entirely.
#   Listing the exact Vite dev-server URL fixes that, and is also safer
#   because it won't accidentally expose the API to every website on the internet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestData(BaseModel):
    interests: list[str]
    preferred_difficulty: int
    preferred_workload: int
    completed_courses: list[str] = []

@app.post("/recommend")
def recommend(data: RequestData) -> list:
    preferences = {
        "interests": data.interests,
        "preferred_difficulty": data.preferred_difficulty,
        "preferred_workload": data.preferred_workload,
        "completed_courses": data.completed_courses,
    }
    # Pass the full course catalog, not completed_courses — completed_courses
    # is used inside recommend_courses to filter out ineligible courses via is_eligible().
    courses = recommend_courses(course_catalog, preferences)
    result = []
    for course, score in courses:
        result.append({
            # Use get_name() because __init__ stores the name as self._name
            "name": course.get_name(),
            "score": score,
            "explanation": explain(course, preferences),
        })
    return result