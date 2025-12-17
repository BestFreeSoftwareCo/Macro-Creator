# Changelog

All notable changes to this project will be documented in this file.

 This changelog is meant to be readable by users and contributors. When releases are tagged, entries will move from [Unreleased] into a versioned section.

## [Unreleased]

### Added

- **First-run Terms of Service gate**: On first launch, you must accept the Terms before the main UI is available.
- **Discord invite prompt**: Optional prompt to join the Discord community, including a persistent "Don't show again" dismissal.
- **Access Key prompt**: An access key is required to use the app.
  - Click "Join Discord Server"
  - Get your access key from the Discord community
  - Paste it into the prompt and click "Verify"
- **New macro action types**:
  - **Keyboard**:
    - `type_text` (type a string)
    - `hotkey` (press a key combination)
    - `key_down` / `key_up` (hold/release keys)
  - **Mouse**:
    - `mouse_down` / `mouse_up` (hold/release mouse buttons)
    - `move_mouse_rel` (relative mouse movement)
    - `drag_to` (click-and-drag to a position)
  - **Image automation**:
    - `wait_for_image` (wait until an image appears)
    - `click_image` (find an image and click its center)
- **Simple Mode UI coverage** for the new action types (add/edit via the action dialog and readable formatting in the actions list).

### Changed

- **Macro engine image waits**:
  - Waiting loops are stop/pause-aware so the macro remains responsive while waiting.
  - `timeout_ms=0` is interpreted as "wait indefinitely" (until found or stopped).
- **Macro JSON validation**:
  - `settings.repeat=0` is allowed and means "repeat until stopped".
  - `post_action` is validated recursively.
  - Image-related numeric fields (`timeout_ms`, `interval_ms`) are validated as non-negative integers where applicable.

### Fixed

- **Macro engine stability**: Restored/corrected action execution control flow after adding image actions.
- **Repo default config**: Reset committed `config/settings.json` to default values for a clean repo state.

### Notes

- If you're having trouble with an access key, make sure you're pasting it exactly (no extra spaces before/after).
- Image actions can be sensitive to DPI scaling, theme changes, window animations, and multi-monitor setups.
