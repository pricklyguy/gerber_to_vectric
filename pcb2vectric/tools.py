"""Tool model and a reader for Vectric tool databases (.vtdb, which are SQLite files)."""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

MM_PER_INCH = 25.4

# tool_geometry.tool_type values seen in VCarve Pro 10 databases (6 = drill is from a real PCB tool set).
KIND_BY_VTDB_TYPE = {0: "ballnose", 1: "endmill", 2: "bowl", 3: "vbit", 4: "vbit", 5: "tapered", 6: "drill"}
TYPE_LABEL = {"ballnose": "Ball Nose", "endmill": "End Mill", "bowl": "Bowl", "vbit": "V-Bit",
              "tapered": "Tapered", "drill": "Drill", "other": "Tool"}


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str  # endmill | vbit | drill | ballnose | tapered | other
    diameter: float  # mm, cutting diameter (full width for V-bits)
    included_angle: Optional[float] = None  # degrees, V-bits
    tip_diameter: float = 0.0  # mm, flat at the tip of a V-bit
    group: str = ""  # top-level group in the tool tree, e.g. "PCB Bits"

    def v_cut_width(self, depth: float) -> float:
        """Width of the groove a V-bit cuts at a given depth (mm)."""
        if self.kind != "vbit" or not self.included_angle:
            raise ValueError(f"{self.name} is not a V-bit")
        return self.tip_diameter + 2.0 * depth * math.tan(math.radians(self.included_angle) / 2.0)

    def v_depth_for_width(self, width: float) -> float:
        """Depth needed for a V-bit groove of a given width (mm)."""
        if self.kind != "vbit" or not self.included_angle:
            raise ValueError(f"{self.name} is not a V-bit")
        return max(0.0, (width - self.tip_diameter) / (2.0 * math.tan(math.radians(self.included_angle) / 2.0)))

    def cut(self, depth: Optional[float] = None, width: Optional[float] = None) -> Tuple[float, float]:
        """Return (groove_width, depth) for this tool given either a depth or a width.

        V-bits: the unknown one is calculated (a width narrower than the tip is clamped to the tip).
        Other tools: the groove is the tool diameter; depth is whatever you ask for.
        """
        if self.kind == "vbit" and self.included_angle:
            if depth is not None:
                return self.v_cut_width(depth), depth
            if width is not None:
                return max(width, self.tip_diameter), self.v_depth_for_width(width)
            raise ValueError("give depth or width")
        return self.diameter, depth if depth is not None else 0.0


def _fmt_num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def expand_name(fmt: str, kind: str, units: int, diameter_mm: float, flat_mm: float) -> str:
    """Vectric stores some names as templates, e.g. '.8mm {Tool Type}' -> '.8mm Drill'."""
    if "{" not in fmt:
        return fmt
    scale = 1.0 if units == 0 else 1.0 / MM_PER_INCH
    subs = {
        "Tool Type": TYPE_LABEL.get(kind, "Tool"),
        "Units Short": "mm" if units == 0 else "in",
        "Flat Diameter": _fmt_num(flat_mm * scale),
        "Diameter|F": _fmt_num(diameter_mm * scale),
        "Diameter": _fmt_num(diameter_mm * scale),
    }
    return re.sub(r"\{([^}]*)\}", lambda m: subs.get(m.group(1), m.group(0)), fmt)


def read_vtdb(path: str) -> List[Tool]:
    """Read every tool from a Vectric .vtdb file. Dimensions are converted to mm."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tree = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, parent_group_id, name FROM tool_tree_entry")}
        rows = con.execute(
            """SELECT g.id, g.name_format, g.tool_type, g.units, g.diameter, g.included_angle, g.flat_diameter,
                      t.id, t.name
               FROM tool_geometry g LEFT JOIN tool_tree_entry t ON t.tool_geometry_id = g.id"""
        ).fetchall()
    finally:
        con.close()

    def top_group(entry_id: Optional[str]) -> str:
        name, seen = "", set()
        while entry_id and entry_id in tree and entry_id not in seen:
            seen.add(entry_id)
            parent, nm = tree[entry_id]
            if parent is None:
                name = nm or ""
            entry_id = parent
        return name

    tools = []
    for _gid, fmt, ttype, units, dia, angle, flat, entry_id, entry_name in rows:
        scale = MM_PER_INCH if units == 1 else 1.0  # units: 0 = mm, 1 = inch
        kind = KIND_BY_VTDB_TYPE.get(ttype, "other")
        if kind != "drill" and "drill" in (fmt or "").lower():
            kind = "drill"
        dia_mm, flat_mm = (dia or 0.0) * scale, (flat or 0.0) * scale
        name = expand_name(entry_name or fmt or "?", kind, units, dia_mm, flat_mm)
        tools.append(Tool(name, kind, dia_mm, angle, flat_mm, top_group(entry_id)))
    return tools
