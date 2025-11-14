# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Dict
import random

# ---- tiny seed so plans have something to pick from ----
EXERCISES = [
    {"id": "pushup",    "name": "Push-ups",            "group": "chest",     "equipment": "bodyweight"},
    {"id": "ohp-db",    "name": "DB Shoulder Press",   "group": "shoulders", "equipment": "dumbbells"},
    {"id": "bench",     "name": "Bench Press",         "group": "chest",     "equipment": "gym"},
    {"id": "row",       "name": "DB Row",              "group": "back",      "equipment": "dumbbells"},
    {"id": "pullup",    "name": "Pull-ups",            "group": "back",      "equipment": "bodyweight"},
    {"id": "squat-bw",  "name": "Bodyweight Squat",    "group": "legs",      "equipment": "bodyweight"},
    {"id": "goblet",    "name": "Goblet Squat",        "group": "legs",      "equipment": "dumbbells"},
    {"id": "backsquat", "name": "Back Squat",          "group": "legs",      "equipment": "gym"},
    {"id": "plank",     "name": "Plank",               "group": "core",      "equipment": "bodyweight"},
    {"id": "hkr",       "name": "Hanging Knee Raise",  "group": "core",      "equipment": "gym"},
]

# ---- character archetypes (template + default sets/reps bias) ----
CHAR_ARCH = {
    "goku":    {"style": "power",      "template": ["push","pull","legs","full","full"], "sets": 4, "reps": 5},
    "luffy":   {"style": "endurance",  "template": ["full","full","legs","full","full"], "sets": 3, "reps": 12},
    "asta":    {"style": "strength",   "template": ["push","pull","legs","push","pull"], "sets": 4, "reps": 6},
    "saitama": {"style": "full-body",  "template": ["full","full","full"],               "sets": 3, "reps": 10},
}

DayFocus  = Literal["push", "pull", "legs", "full"]
Level     = Literal["beginner", "intermediate"]
Goal      = Literal["strength", "hypertrophy", "athletic"]
Equipment = Literal["bodyweight", "dumbbells", "gym"]

# ---- request/response models ----
class GenerateRequest(BaseModel):
    character_id: str
    days_per_week: int
    level: Level
    goal: Goal
    equipment: Equipment

class ExerciseItem(BaseModel):
    exercise_id: str
    sets: int
    reps: int

class DayPlan(BaseModel):
    week: int
    day_index: int
    focus: DayFocus
    items: List[ExerciseItem]

class PlanResponse(BaseModel):
    weeks: int
    schedule: List[DayPlan]

# ---- generator ----
class WorkoutPlan:
    def __init__(self, character_id: str, days_per_week: int, level: str, goal: str, equipment: str):
        self.character_id = character_id
        self.days = max(1, min(6, days_per_week))
        self.level = level
        self.goal = goal
        self.equipment = equipment
        self.last_trained: Dict[str, int] = {
            "chest": -999, "back": -999, "legs": -999, "shoulders": -999, "arms": -999, "core": -999
        }
        self.template = self._make_template(self.days)

    def _make_template(self, days: int) -> List[DayFocus]:
        # Prefer the character's template and resize to requested days
        pref = CHAR_ARCH.get(self.character_id)
        if pref:
            base = pref["template"]
            if len(base) >= days:
                return base[:days]
            # extend by repeating the last day type
            return base + [base[-1]] * (days - len(base))
        # fallback generic templates
        if days <= 3:  return ["full","full","full"]
        if days == 4:  return ["push","legs","pull","full"]
        if days == 5:  return ["push","pull","legs","full","full"]
        return ["push","pull","legs","push","pull","legs"]

    def _sets_reps(self):
        # start with character bias
        char = CHAR_ARCH.get(self.character_id, {})
        base_sets = char.get("sets", 3 if self.level == "beginner" else 4)
        char_reps = char.get("reps")

        # then nudge by goal (goal wins ties)
        if self.goal == "strength":
            reps = 4 if char_reps is None else min(char_reps, 6)
        elif self.goal == "hypertrophy":
            reps = 8 if char_reps is None else max(char_reps, 8)
        else:  # athletic
            reps = 10 if char_reps is None else max(char_reps, 10)

        return base_sets, reps

    def _focus_groups(self, focus: DayFocus) -> List[str]:
        if focus == "push": return ["chest", "shoulders", "core"]
        if focus == "pull": return ["back", "core"]
        if focus == "legs": return ["legs", "core"]
        return ["chest", "back", "legs", "shoulders", "core"]  # full

    def _filtered(self, group: str) -> List[dict]:
        pool = []
        for ex in EXERCISES:
            if ex["group"] != group:
                continue
            if self.equipment == "gym":
                pool.append(ex)
            elif ex["equipment"] in (self.equipment, "bodyweight"):
                pool.append(ex)
        return pool

    def generate(self, weeks: int = 4) -> List[DayPlan]:
        schedule: List[DayPlan] = []
        sets, reps = self._sets_reps()
        current_day_index = 0

        for w in range(1, weeks + 1):
            for d, focus in enumerate(self.template):
                groups = self._focus_groups(focus)
                groups.sort(key=lambda g: self.last_trained[g])  # least recently trained first
                items: List[ExerciseItem] = []

                for g in groups:
                    # simple recovery: ~2 days between hits
                    if current_day_index - self.last_trained[g] < 2:
                        continue
                    pool = self._filtered(g)
                    if not pool:
                        continue
                    choice = random.choice(pool)
                    items.append(ExerciseItem(exercise_id=choice["id"], sets=sets, reps=reps))
                    self.last_trained[g] = current_day_index
                    if len(items) >= 5:
                        break

                schedule.append(DayPlan(week=w, day_index=d, focus=focus, items=items))
                current_day_index += 1

        return schedule

# ---- FastAPI app ----
app = FastAPI(title="ANI_FIT API", version="0.1.0")

# allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generate", response_model=PlanResponse)
def generate_plan(req: GenerateRequest):
    gen = WorkoutPlan(
        character_id=req.character_id,
        days_per_week=req.days_per_week,
        level=req.level,
        goal=req.goal,
        equipment=req.equipment,
    )
    schedule = gen.generate(weeks=4)
    return PlanResponse(weeks=4, schedule=schedule)
