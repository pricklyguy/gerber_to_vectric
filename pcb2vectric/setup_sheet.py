"""Plain-English list of what to enter in VCarve for each layer of the DXF."""

from __future__ import annotations

from typing import Optional

from .job import JobConfig, JobResult
from .tools import Tool


def build_setup_sheet(res: JobResult, cfg: JobConfig, iso_tool: Optional[Tool], depth: float) -> str:
    s = cfg.isolation
    out = [f"Board {res.width:.2f} x {res.height:.2f} mm.  Import the DXF as millimetres.",
           "Zero Z at the top of the copper. Layer names below are the DXF layers.", ""]

    for side, iso in res.isolation.items():
        tool = iso_tool.name if iso_tool else f"{s.cut_width:.3f} mm cutter"
        out += [f"{side} ISOLATION  (layers {side}_ISO_PASS1 .. PASS{s.passes})",
                f"  Toolpath : Profile, machine ON the vector, one toolpath per pass layer",
                f"  Tool     : {tool}",
                f"  Cut depth: {depth:.3f} mm   -> groove {s.cut_width:.3f} mm wide at the surface",
                f"  Passes   : {s.passes}, each {s.stepover:.3f} mm further out ({s.overlap:.0%} overlap)"]
        if side == "BOTTOM":
            out.append("  Flip the board left-to-right (around its vertical centre line) before this one.")
        if iso.tight_spots:
            out.append(f"  WARNING  : {len(iso.tight_spots)} spot(s) where copper is closer than the groove "
                       f"(see layer {side}_WARN_TIGHT)")
        out.append("")

    if res.drills:
        for bit, holes in sorted(res.drills.by_bit.items()):
            out.append(f"DRILL {bit:.2f} mm  (layer DRILL_{bit:.2f}MM) - {len(holes)} hole(s). "
                       f"Drilling toolpath, circle centres.")
        if res.drills.milled:
            out.append(f"MILL HOLES (layer DRILL_MILL) - {len(res.drills.milled)} hole(s) larger than your biggest "
                       f"drill; profile INSIDE with the outline end mill.")
        if res.drills.slots:
            out.append(f"SLOTS (layer SLOTS_MILL) - {len(res.drills.slots)} slot(s); profile INSIDE with the outline end mill.")
        for w in res.drills.warnings:
            out.append(f"  note: {w}")
        out.append("")
    if res.align:
        out.append(f"ALIGNMENT HOLES (layer ALIGN) - two {cfg.align_diameter:.1f} mm holes on the flip axis. "
                   f"Drill these first, before flipping.")
        out.append("")
    if res.outline is not None:
        out.append("OUTLINE (layer OUTLINE) - Profile OUTSIDE with the end mill, add tabs.")
    return "\n".join(out).rstrip() + "\n"
