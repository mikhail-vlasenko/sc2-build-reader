from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import threading, time, os, sys, json
import pyttsx3
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BUILD_FILE = "builds.json"

# Global state for the match and build order scheduling
match_state = {
    "start_time": None,
    "delay": 3,
    "build_steps": [],
    "lock": threading.Lock(),
    "paused": False,
    "pause_time": None,
    "elapsed_time": 0,
    "stop_requested": False,
    "next_step_index": 0,
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
    """Speak the given text, using 'say' on macOS and pyttsx3 elsewhere."""
    if sys.platform == "darwin":  # macOS
        os.system(f'say "{text}"')
    else:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()


def scheduler():
    """
    Manages the execution of the build order, allowing for pause and stop functionality,
    using a pointer to track which step to speak next, and sleeping until the next event.
    """
    with match_state["lock"]:
        time.sleep(match_state["delay"])
        match_state["start_time"] = time.time() - match_state["elapsed_time"]
        match_state["stop_requested"] = False
        match_state["next_step_index"] = 0

    time_to_next = 0
    while True:
        time.sleep(min(time_to_next, 0.1))

        with match_state["lock"]:
            # Handle STOP
            if match_state["stop_requested"]:
                match_state["build_steps"].clear()
                match_state["start_time"] = None
                match_state["elapsed_time"] = 0
                match_state["next_step_index"] = 0
                return

            # Handle PAUSE
            if match_state["paused"]:
                continue

            # No more steps? We're done.
            if match_state["next_step_index"] >= len(match_state["build_steps"]):
                return

            # Calculate current elapsed time
            current_time = time.time() - match_state["start_time"]

            # Check if any steps are due now
            # Speak all steps that are at or before current_time
            while (match_state["next_step_index"] < len(match_state["build_steps"]) and
                   match_state["build_steps"][match_state["next_step_index"]]["time"] <= current_time):
                step = match_state["build_steps"][match_state["next_step_index"]]
                if not step["spoken"]:
                    step["spoken"] = True
                    threading.Thread(
                        target=speak,
                        args=(step["action"],),
                        daemon=True
                    ).start()
                match_state["next_step_index"] += 1

            # Otherwise, sleep until next step time OR a short interval
            next_step_time = match_state["build_steps"][match_state["next_step_index"]]["time"]
            time_to_next = next_step_time - current_time

@app.post("/pause", response_class=JSONResponse)
async def pause_build():
    """Pause the build execution."""
    with match_state["lock"]:
        if not match_state["paused"] and match_state["start_time"]:
            match_state["paused"] = True
            match_state["pause_time"] = time.time()
            match_state["elapsed_time"] = time.time() - match_state["start_time"]
    return {"message": "Build paused"}


@app.post("/resume", response_class=JSONResponse)
async def resume_build():
    """Resume the build execution."""
    with match_state["lock"]:
        if match_state["paused"]:
            match_state["paused"] = False
            pause_duration = time.time() - match_state["pause_time"]
            # Shift start_time forward by however long we paused
            match_state["start_time"] += pause_duration
    return {"message": "Build resumed"}

@app.post("/stop", response_class=JSONResponse)
async def stop_build():
    """Stop the build execution entirely."""
    with match_state["lock"]:
        match_state["stop_requested"] = True
    return {"message": "Build stopped"}

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
      - "paused": Whether the build execution is paused.
    """
    with match_state["lock"]:
        start_time = match_state["start_time"]
        steps = match_state["build_steps"]
        paused = match_state["paused"]
        # If paused, use match_state["elapsed_time"], else compute from start_time
        if paused:
            elapsed_time = match_state["elapsed_time"]
        else:
            elapsed_time = (time.time() - start_time) if start_time else 0

    current_time = elapsed_time
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
        "paused": paused,
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
