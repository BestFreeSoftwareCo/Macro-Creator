from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2  # type: ignore
import numpy as np  # type: ignore
import pyautogui

from PyMacroStudio.core.paths import project_root


@dataclass(frozen=True)
class ImageCheck:
    value: str
    confidence: float = 0.9
    region: tuple[int, int, int, int] | None = None


_TEMPLATE_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_TEMPLATE_CACHE_MAX = 32


def image_found(check: ImageCheck) -> bool:
    template_path = _resolve_image_path(check.value)

    cache_key = str(template_path)
    template = _TEMPLATE_CACHE.get(cache_key)
    if template is None:
        template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ValueError("failed to load image")
        _TEMPLATE_CACHE[cache_key] = template
        _TEMPLATE_CACHE.move_to_end(cache_key)
        while len(_TEMPLATE_CACHE) > _TEMPLATE_CACHE_MAX:
            _TEMPLATE_CACHE.popitem(last=False)
    else:
        _TEMPLATE_CACHE.move_to_end(cache_key)

    screenshot = pyautogui.screenshot(region=check.region)
    screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

    if screen.shape[0] < template.shape[0] or screen.shape[1] < template.shape[1]:
        return False

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val) >= float(check.confidence)


def _resolve_image_path(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("image path is required")

    p = Path(value)
    if p.is_absolute():
        if not p.exists():
            raise FileNotFoundError(str(p))
        return p

    root = project_root()
    candidates = [
        root / value,
        root / "assets" / "images" / value,
        root / "assets" / value,
        root / "macros" / value,
    ]

    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(str(candidates[0]))


def parse_image_check(action: dict[str, Any]) -> ImageCheck:
    confidence = action.get("confidence", 0.9)
    try:
        confidence_f = float(confidence)
    except Exception:
        confidence_f = 0.9
    confidence_f = max(0.0, min(1.0, confidence_f))

    region = action.get("region")
    region_tuple: tuple[int, int, int, int] | None = None
    if region is not None:
        if (
            isinstance(region, (list, tuple))
            and len(region) == 4
            and all(isinstance(v, (int, float)) for v in region)
        ):
            region_tuple = (int(region[0]), int(region[1]), int(region[2]), int(region[3]))
        else:
            raise ValueError("region must be [x, y, w, h]")

    return ImageCheck(
        value=str(action.get("value", "")),
        confidence=confidence_f,
        region=region_tuple,
    )
