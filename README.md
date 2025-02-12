# StarCraft Build Order Readout

This project is largely AI-generated. (like, I did not read this readme in full)

A local application that provides audible notifications for your StarCraft build orders. The app reads out build order steps at the designated times during a match and features a real-time timeline display, pause/resume/stop controls, and the ability to save, load, and edit build orders.

---

## Features

- **Build Order Readout:**  
  Input your build order in a text format and have the app announce each step using offline text-to-speech (via pyttsx3).

- **Configurable Delay:**  
  Set a custom delay (default is 1 second) before the match timer starts.

- **Real-Time Timeline Display:**  
  - **Past Steps (Green Boxes):** Shows the last 3 steps that have occurred.
  - **Next Step (Yellow Box):** Displays the immediate upcoming step with a live countdown.
  - **Future Steps (Red Boxes):** Lists the next 3 upcoming steps.

- **Control Buttons:**  
  Easily pause, resume, or stop the build order readout at any time.

- **Build Management:**  
  Save, load, and edit build orders which are stored locally in a JSON file.

- **Web-Based UI:**  
  A clean and responsive interface built using FastAPI and standard web technologies.
