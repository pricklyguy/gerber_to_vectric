"""Tool model and a reader for Vectric tool databases (.vtdb, which are SQLite files)."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

MM_PER_INCH = 25.4

# tool_geometry.tool_type values seen in VCarve Pro 10 databases.
KIND_BY_VTDB_TYPE = {0: "ballnose", 1: "endmill", 2: "bowl", 3: "vbit", 4: "vbit", 5: "tapered"}


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str  # endmill | vbit | drill | ballnose | tapered | other
    diameter: float  # mm, shank-side cutting diameter
    included_angle: Optional[float] = None  # degrees, V-bits
    tip_diameter: float = 0.0  # mm, flat at the tip of a V-bit

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


def classify(name: str, vtdb_type: int) -> str:
    if "drill" in name.lower():
        return "drill"
    return KIND_BY_VTDB_TYPE.get(vtdb_type, "other")


def read_vtdb(path: str) -> List[Tool]:
    """Read every tool from a Vectric .vtdb file. Dimensions are converted to mm."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """SELECT COALESCE(NULLIF(t.name, ''), g.name_format), g.name_format, g.tool_type,
                      g.units, g.diameter, g.included_angle, g.flat_diameter
               FROM tool_geometry g LEFT JOIN tool_tree_entry t ON t.tool_geometry_id = g.id"""
        ).fetchall()
    finally:
        con.close()

    tools = []
    for tree_name, fmt, ttype, units, dia, angle, flat in rows:
        scale = MM_PER_INCH if units == 1 else 1.0  # units: 0 = mm, 1 = inch
        name = fmt or tree_name or "?"
        tools.append(
            Tool(
                name=name,
                kind=classify(name, ttype),
                diameter=(dia or 0.0) * scale,
                included_angle=angle,
                tip_diameter=(flat or 0.0) * scale,
            )
        )
    return tools
