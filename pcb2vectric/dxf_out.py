"""Write a VCarve-ready DXF. Every operation gets its own layer so each is one VCarve toolpath."""

from __future__ import annotations

from typing import Iterable

import ezdxf
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from .gerber_io import _polys
from .job import JobResult

COLORS = {"ISO": 1, "OUTLINE": 5, "DRILL": 3, "ALIGN": 6, "SLOT": 4, "COPPER": 8, "WARN": 2}


def _layer(doc, name: str, color: int) -> str:
    if name not in doc.layers:
        doc.layers.add(name, color=color)
    return name


def _add_rings(msp, geom: BaseGeometry, layer: str) -> None:
    for poly in _polys(geom):
        for ring in [poly.exterior, *poly.interiors]:
            msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": layer})


def write_dxf(res: JobResult, path: str, include_copper: bool = False) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for side, iso in res.isolation.items():
        for n, rings in enumerate(iso.passes, start=1):
            layer = _layer(doc, f"{side}_ISO_PASS{n}", COLORS["ISO"] + n)
            for ring in rings:
                msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": layer})
        if iso.tight_spots:
            layer = _layer(doc, f"{side}_WARN_TIGHT", COLORS["WARN"])
            for p in iso.tight_spots:
                msp.add_circle((p.x, p.y), 0.3, dxfattribs={"layer": layer})
        if include_copper:
            _add_rings(msp, res.copper[side], _layer(doc, f"{side}_COPPER", COLORS["COPPER"]))

    if res.outline is not None:
        _add_rings(msp, res.outline, _layer(doc, "OUTLINE", COLORS["OUTLINE"]))

    if res.drills:
        for bit, holes in sorted(res.drills.by_bit.items()):
            layer = _layer(doc, f"DRILL_{bit:.2f}MM", COLORS["DRILL"])
            for h in holes:
                msp.add_circle((h.x, h.y), h.diameter / 2, dxfattribs={"layer": layer})
        if res.drills.milled:
            layer = _layer(doc, "DRILL_MILL", COLORS["DRILL"])
            for h in res.drills.milled:
                msp.add_circle((h.x, h.y), h.diameter / 2, dxfattribs={"layer": layer})
        if res.drills.slots:
            layer = _layer(doc, "SLOTS_MILL", COLORS["SLOT"])
            for s in res.drills.slots:
                _add_rings(msp, s.shape(), layer)

    if res.align:
        layer = _layer(doc, "ALIGN", COLORS["ALIGN"])
        for h in res.align:
            msp.add_circle((h.x, h.y), h.diameter / 2, dxfattribs={"layer": layer})

    doc.saveas(path)
