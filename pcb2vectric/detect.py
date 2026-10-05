"""Guess which file in a folder is which Gerber/Excellon layer (EasyEDA, KiCad, Eagle naming)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

TOP = (".gtl", ".top", ".cmp")
BOTTOM = (".gbl", ".bot", ".sol")
OUTLINE = (".gko", ".gm1", ".gml", ".oln")
DRILL = (".drl", ".xln", ".exc", ".txt")


@dataclass
class Detected:
    top: Optional[str] = None
    bottom: Optional[str] = None
    outline: Optional[str] = None
    drills: List[str] = field(default_factory=list)


def _is_excellon(path: str) -> bool:
    try:
        with open(path, "r", errors="ignore") as f:
            head = f.read(2048)
    except OSError:
        return False
    return "M48" in head or "METRIC" in head or "INCH" in head


def detect_files(folder: str) -> Detected:
    d = Detected()
    for fn in sorted(os.listdir(folder)):
        path, low = os.path.join(folder, fn), fn.lower()
        ext = os.path.splitext(low)[1]
        if ext in TOP or "toplayer" in low or low.endswith("-f_cu.gbr") or "_top.gbr" in low:
            d.top = d.top or path
        elif ext in BOTTOM or "bottomlayer" in low or low.endswith("-b_cu.gbr") or "_bottom.gbr" in low:
            d.bottom = d.bottom or path
        elif ext in OUTLINE or "outline" in low or low.endswith("-edge_cuts.gbr"):
            d.outline = d.outline or path
        elif ext in DRILL and _is_excellon(path):
            d.drills.append(path)
    return d
