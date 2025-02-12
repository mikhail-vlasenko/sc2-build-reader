from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import threading, time, os, json
import pyttsx3
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BUILD_FILE = "builds.json"

# Global state for the match and build order scheduling
match_state = {
    "start_time": None,  # Set when the match begins (after the delay)
    "delay": 3,  # Configurable delay (in seconds) before match start
    "build_steps": [],  # List of build steps (each a dict with supply, time, action, spoken)
    "lock": threading.Lock()
}


def load_builds():
    """Load saved builds from the JSON file."""
    if os.path.exists(BUILD_FILE):
        with open(BUILD_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_builds_data(builds):
    """Save the builds dictionary to the JSON file."""
    with open(BUILD_FILE, "w") as f:
        json.dump(builds, f, indent=4)


def parse_build_order(build_order_text: str):
    """
    Parse the build order text into a list of steps.
    Each line should have: supply, time (m:ss), and an action.
    """
    steps = []
    lines = build_order_text.strip().splitlines()
    for line in lines:
        if not line.strip():
            continue
        tokens = line.strip().split()
        if len(tokens) < 3:
            continue  # Skip invalid lines; alternatively, raise an error.
        supply = tokens[0]
        time_str = tokens[1]
        action = " ".join(tokens[2:])
        try:
            minutes, seconds = time_str.split(":")
            total_seconds = int(minutes) * 60 + int(seconds)
        except Exception:
            total_seconds = 0
        step = {
            "supply": supply,
            "time": total_seconds,
            "action": action,
            "spoken": False
        }
        steps.append(step)
    steps.sort(key=lambda s: s["time"])
    return steps


def speak(text: str):
    """Use pyttsx3 to speak the given text."""
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def scheduler():
    """
    Wait for the initial delay, then record the start time.
    Loop to check if each build step’s scheduled time has been reached.
    When a step’s time is passed, trigger TTS.
    """
    delay = match_state["delay"]
    time.sleep(delay)
    with match_state["lock"]:
        match_state["start_time"] = time.time()

    while True:
        with match_state["lock"]:
            if not match_state["build_steps"]:
                break
            current_time = time.time() - match_state["start_time"]
            for step in match_state["build_steps"]:
                if not step["spoken"] and step["time"] <= current_time:
                    step["spoken"] = True
                    threading.Thread(target=speak, args=(step["action"],), daemon=True).start()
            if all(step["spoken"] for step in match_state["build_steps"]):
                break
        time.sleep(0.5)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main page with build management."""
    saved_builds = load_builds()
    return templates.TemplateResponse("index.html", {"request": request, "saved_builds": saved_builds})


@app.post("/start", response_class=HTMLResponse)
async def start_build(request: Request, build_order: str = Form(...), delay: int = Form(...)):
    """
    Accept the build order text and configurable delay from the form.
    Parse the build order, update the global state, and start the scheduler.
    """
    steps = parse_build_order(build_order)
    with match_state["lock"]:
        match_state["build_steps"] = steps
        match_state["delay"] = delay
        match_state["start_time"] = None
        for step in match_state["build_steps"]:
            step["spoken"] = False
    threading.Thread(target=scheduler, daemon=True).start()
    saved_builds = load_builds()
    return templates.TemplateResponse("index.html",
                                      {"request": request, "message": "Build started!", "saved_builds": saved_builds})


@app.get("/timeline", response_class=JSONResponse)
async def get_timeline():
    """
    Return a JSON object with:
      - "past": The last 3 build steps whose scheduled times have passed.
      - "future": The next 4 upcoming steps.
    """
    with match_state["lock"]:
        start_time = match_state["start_time"]
        steps = match_state["build_steps"]
    current_time = 0 if start_time is None else time.time() - start_time
    past_steps = [step for step in steps if step["time"] <= current_time]
    future_steps = [step for step in steps if step["time"] > current_time]
    past = past_steps[-3:]
    next_step = None
    next_countdown = None
    if future_steps:
        next_step = future_steps[0]
        next_countdown = max(0, next_step["time"] - current_time)
        future_remaining = future_steps[1:4]
    else:
        future_remaining = []
    return {
        "past": past,
        "next": {"step": next_step, "countdown": next_countdown} if next_step else None,
        "future": future_remaining,
        "paused": False,
    }


@app.get("/builds", response_class=JSONResponse)
async def list_builds():
    """Return a JSON list of saved builds."""
    builds = load_builds()
    return builds


@app.get("/load_build")
async def load_build(build_name: str):
    """
    Load a saved build by its name.
    Returns the build order text.
    """
    builds = load_builds()
    if build_name in builds:
        return {"build_order": builds[build_name]}
    return {"error": "Build not found"}


@app.post("/save_build", response_class=JSONResponse)
async def save_build(build_name: str = Form(...), build_order: str = Form(...)):
    """
    Save or update a build.
    The build is identified by its unique name.
    """
    builds = load_builds()
    builds[build_name] = build_order
    save_builds_data(builds)
    return {"message": "Build saved successfully", "saved_builds": builds}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
