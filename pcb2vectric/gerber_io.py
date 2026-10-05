"""Load Gerber / Excellon files into Shapely geometry (all coordinates in mm)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from gerbonara import ExcellonFile, GerberFile
from gerbonara import graphic_primitives as gp
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

ARC_ERROR_MM = 0.005


@dataclass
class Hole:
    x: float
    y: float
    diameter: float


@dataclass
class Slot:
    x1: float
    y1: float
    x2: float
    y2: float
    diameter: float

    def shape(self) -> BaseGeometry:
        return LineString([(self.x1, self.y1), (self.x2, self.y2)]).buffer(self.diameter / 2.0, 32)


def _sample_arc(x1, y1, x2, y2, cx, cy, clockwise) -> List[tuple]:
    """Points along a circular arc, including both end points."""
    r = math.hypot(x1 - cx, y1 - cy)
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    sweep = a2 - a1
    if clockwise:
        if sweep >= 0:
            sweep -= 2 * math.pi
    elif sweep <= 0:
        sweep += 2 * math.pi
    if math.isclose(x1, x2, abs_tol=1e-9) and math.isclose(y1, y2, abs_tol=1e-9):
        sweep = -2 * math.pi if clockwise else 2 * math.pi  # full circle
    step = 2 * math.acos(max(0.0, 1 - ARC_ERROR_MM / max(r, ARC_ERROR_MM)))
    n = max(4, int(math.ceil(abs(sweep) / max(step, 1e-3))))
    return [(cx + r * math.cos(a1 + sweep * i / n), cy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]


def _arc_points(p: gp.Arc) -> List[tuple]:
    return _sample_arc(p.x1, p.y1, p.x2, p.y2, p.cx, p.cy, p.clockwise)


def _arcpoly_points(p: gp.ArcPoly) -> List[tuple]:
    pts: List[tuple] = []
    for p1, p2, (clockwise, center) in p.segments:
        if clockwise is None:
            pts.append(p1)
        else:
            pts.extend(_sample_arc(*p1, *p2, *center, clockwise)[:-1])
    return pts


def _primitive_shape(p) -> Optional[BaseGeometry]:
    if isinstance(p, gp.Line):
        return LineString([(p.x1, p.y1), (p.x2, p.y2)]).buffer(p.width / 2.0, 16)
    if isinstance(p, gp.Arc):
        return LineString(_arc_points(p)).buffer(p.width / 2.0, 16)
    if isinstance(p, gp.Circle):
        return Point(p.x, p.y).buffer(p.r, 32)
    if isinstance(p, gp.Rectangle):
        rect = box(p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2)
        if p.rotation:
            rect = affinity.rotate(rect, p.rotation, origin=(p.x, p.y), use_radians=True)
        return rect
    if isinstance(p, gp.ArcPoly):
        pts = _arcpoly_points(p)
        if len(pts) < 3:
            return None
        poly = Polygon(pts)
        return poly if poly.is_valid else poly.buffer(0)
    return None


def _polys(geom: BaseGeometry) -> List[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) for g in _polys(g)]


def load_copper(path: str) -> BaseGeometry:
    """Return the copper as a (Multi)Polygon, honouring dark/clear polarity in file order."""
    gf = GerberFile.open(path)
    copper: BaseGeometry = Polygon()
    run: List[BaseGeometry] = []
    run_dark = True

    def flush():
        nonlocal copper, run
        if run:
            u = unary_union(run)
            copper = copper.union(u) if run_dark else copper.difference(u)
            run = []

    for obj in gf.objects:
        for prim in obj.to_primitives("mm"):
            shape = _primitive_shape(prim)
            if shape is None or shape.is_empty:
                continue
            dark = bool(prim.polarity_dark)
            if dark != run_dark:
                flush()
                run_dark = dark
            run.append(shape)
    flush()
    return copper


def load_outline(path: str) -> BaseGeometry:
    """Board outline as a polygon, built from the centre-lines of the outline layer."""
    gf = GerberFile.open(path)
    lines: List[LineString] = []
    polys: List[Polygon] = []
    for obj in gf.objects:
        for prim in obj.to_primitives("mm"):
            if isinstance(prim, gp.Line):
                lines.append(LineString([(prim.x1, prim.y1), (prim.x2, prim.y2)]))
            elif isinstance(prim, gp.Arc):
                lines.append(LineString(_arc_points(prim)))
            elif isinstance(prim, gp.ArcPoly):
                shape = _primitive_shape(prim)
                if shape is not None:
                    polys.append(shape)
    if lines:
        # snap near-coincident endpoints so polygonize can close the loop
        merged = unary_union([affinity.scale(l, 1, 1) for l in lines])
        polys.extend(polygonize(merged))
    if not polys:
        raise ValueError(f"No closed board outline found in {path}")
    return unary_union([Polygon(p.exterior) for p in polys])


def load_drills(*paths: str):
    """Return (holes, slots) from one or more Excellon files, in mm."""
    holes: List[Hole] = []
    slots: List[Slot] = []
    for path in paths:
        ef = ExcellonFile.open(path)
        for obj in ef.objects:
            kind = type(obj).__name__
            if kind == "Flash":
                holes.append(Hole(obj.x, obj.y, obj.tool.diameter))
            elif kind == "Line":
                slots.append(Slot(obj.x1, obj.y1, obj.x2, obj.y2, obj.tool.diameter))
    return holes, slots
