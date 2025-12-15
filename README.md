# PyMacro Studio

A beginner-friendly **macro creator** with an optional **Advanced (JSON) mode**.

Built with **Python 3.12** + **PySide6**.

## Features

### Simple Mode (no-code)

- Create macros with an actions list (drag/drop reorder)
- Add/Edit actions via a single popup dialog
- **Timing-friendly**: delays support **ms / seconds / minutes**
- Optional **Post Action** per step (runs immediately after the main action)
- Global hotkeys:
  - Start/Stop toggle
  - Emergency stop
- Save/Load macros as JSON

### Advanced Mode (JSON)

- JSON editor with:
  - Format
  - Validate
  - Load/Save
  - Run/Stop
- Live logs

### Engine / Safety

- Threaded execution
- PyAutoGUI failsafe support
- `max_steps` safety cap
- `repeat=0` supports **repeat until stopped**

## Quick Start

### 1) Create a virtual environment

```bash
python -m venv .venv
```

### 2) Install dependencies

```bash
# Windows
.venv\Scripts\pip install -r requirements.txt

# macOS/Linux
.venv/bin/pip install -r requirements.txt
```

### 3) Run

```bash
# From the repo root
.venv\Scripts\python -m PyMacroStudio
```

If you prefer:

```bash
.venv\Scripts\python PyMacroStudio\main.py
```

## Macro JSON format (schema_version = 1)

Minimal example:

```json
{
  "schema_version": 1,
  "name": "Example Macro",
  "hotkeys": {
    "start_stop": "F6",
    "stop": "ESC"
  },
  "settings": {
    "repeat": 1,
    "max_steps": 50000
  },
  "actions": [
    {"type": "click", "button": "left"},
    {"type": "wait", "duration_ms": 250}
  ]
}
```

### Post action

Any action may include a `post_action` which runs immediately after the main action:

```json
{
  "type": "click",
  "button": "left",
  "post_action": {"type": "wait", "duration_ms": 250}
}
```

## Repo hygiene (important)

- Do **not** commit `.venv/` (it contains machine-specific paths). This repo ignores it via `.gitignore`.
- Do **not** commit `__pycache__/`.

## Roadmap

- Visual condition builder for `if image` blocks
- Installer/packaging
- Extra QoL tools (step-by-step run, action templates, better debugging)
