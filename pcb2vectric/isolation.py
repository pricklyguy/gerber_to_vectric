"""Isolation routing: tool-centre paths around copper, with clearance checking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from .gerber_io import _polys


@dataclass
class IsolationSettings:
    cut_width: float = 0.2  # mm, width of the groove at the copper surface
    passes: int = 2
    overlap: float = 0.3  # fraction of cut_width shared between neighbouring passes
    simplify: float = 0.002  # mm, vertex-reduction tolerance on the output paths

    @property
    def stepover(self) -> float:
        return self.cut_width * (1.0 - self.overlap)


@dataclass
class IsolationResult:
    passes: List[List[LineString]] = field(default_factory=list)  # one list of closed rings per pass
    tight_spots: List[Point] = field(default_factory=list)  # gaps narrower than the cut


def _rings(geom: BaseGeometry, tol: float) -> List[LineString]:
    out = []
    for poly in _polys(geom):
        for ring in [poly.exterior, *poly.interiors]:
            line = ring.simplify(tol) if tol else ring
            if len(line.coords) >= 4:
                out.append(LineString(line.coords))
    return out


def find_tight_spots(copper: BaseGeometry, cut_width: float, limit: int = 200) -> List[Point]:
    """Midpoints where two separate copper features are closer than the cutter is wide.

    Isolation can't separate those without the cut touching copper, so the user should know.
    """
    polys = _polys(copper)
    if len(polys) < 2:
        return []
    tree = STRtree(polys)
    spots: List[Point] = []
    for i, p in enumerate(polys):
        for j in tree.query(p.buffer(cut_width)):
            if j <= i:
                continue
            q = polys[j]
            if p.distance(q) < cut_width - 1e-6:
                a, b = nearest_points(p, q)
                spots.append(Point((a.x + b.x) / 2, (a.y + b.y) / 2))
                if len(spots) >= limit:
                    return spots
    return spots


def generate_isolation(copper: BaseGeometry, s: IsolationSettings) -> IsolationResult:
    """Pass 1 hugs the copper (cutter edge touches it); each later pass steps outward."""
    res = IsolationResult(tight_spots=find_tight_spots(copper, s.cut_width))
    for i in range(s.passes):
        d = s.cut_width / 2.0 + i * s.stepover
        res.passes.append(_rings(copper.buffer(d, quad_segs=16), s.simplify))
    return res
