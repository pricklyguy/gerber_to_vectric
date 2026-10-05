"""A PCB job: load layers, place them, and produce everything the DXF writer needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from shapely import affinity
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import gerber_io
from .drills import DrillPlan, plan_drills
from .gerber_io import Hole, Slot
from .isolation import IsolationResult, IsolationSettings, generate_isolation


@dataclass
class JobConfig:
    top: Optional[str] = None
    bottom: Optional[str] = None
    outline: Optional[str] = None
    drills: List[str] = field(default_factory=list)
    isolation: IsolationSettings = field(default_factory=IsolationSettings)
    drill_bits: List[float] = field(default_factory=lambda: [0.8, 1.0, 1.1, 1.2, 2.0, 3.0, 3.1])
    zero_at_corner: bool = True  # move board lower-left to (0, 0)
    align_holes: bool = False  # two registration holes on the flip axis (double-sided boards)
    align_diameter: float = 3.0
    align_margin: float = 5.0  # distance from the board edge to the alignment hole centre


@dataclass
class JobResult:
    width: float
    height: float
    outline: Optional[BaseGeometry] = None
    copper: dict = field(default_factory=dict)  # "TOP"/"BOTTOM" -> geometry (BOTTOM is mirrored)
    isolation: dict = field(default_factory=dict)  # "TOP"/"BOTTOM" -> IsolationResult
    drills: Optional[DrillPlan] = None
    align: List[Hole] = field(default_factory=list)


def _move_hole(h: Hole, dx: float, dy: float) -> Hole:
    return Hole(h.x + dx, h.y + dy, h.diameter)


def build_job(cfg: JobConfig) -> JobResult:
    if not (cfg.top or cfg.bottom):
        raise ValueError("Load at least one copper layer")

    copper = {}
    if cfg.top:
        copper["TOP"] = gerber_io.load_copper(cfg.top)
    if cfg.bottom:
        copper["BOTTOM"] = gerber_io.load_copper(cfg.bottom)
    outline = gerber_io.load_outline(cfg.outline) if cfg.outline else None
    holes, slots = gerber_io.load_drills(*cfg.drills) if cfg.drills else ([], [])

    board = outline if outline is not None else unary_union(list(copper.values())).envelope
    minx, miny, maxx, maxy = board.bounds
    dx, dy = (-minx, -miny) if cfg.zero_at_corner else (0.0, 0.0)
    width, height = maxx - minx, maxy - miny
    axis_x = (minx + maxx) / 2 + dx  # vertical flip axis, in placed coordinates

    def place(g):
        return affinity.translate(g, dx, dy)

    res = JobResult(width=width, height=height)
    res.outline = place(outline) if outline is not None else None
    for side, geom in copper.items():
        geom = place(geom)
        if side == "BOTTOM":  # mirror across the flip axis, ready for the flipped setup
            geom = affinity.scale(geom, xfact=-1, yfact=1, origin=(axis_x, 0))
        res.copper[side] = geom
        res.isolation[side] = generate_isolation(geom, cfg.isolation)

    holes = [_move_hole(h, dx, dy) for h in holes]
    slots = [Slot(s.x1 + dx, s.y1 + dy, s.x2 + dx, s.y2 + dy, s.diameter) for s in slots]
    res.drills = plan_drills(holes, slots, cfg.drill_bits)

    if cfg.align_holes:
        top, bot = miny + dy - cfg.align_margin, maxy + dy + cfg.align_margin
        res.align = [Hole(axis_x, top, cfg.align_diameter), Hole(axis_x, bot, cfg.align_diameter)]
    return res
