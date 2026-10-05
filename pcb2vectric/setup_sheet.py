"""Plain-English list of what to do in VCarve for each layer of the DXF."""

from __future__ import annotations

from typing import Optional

from .job import JobConfig, JobResult
from .tools import Tool


def build_setup_sheet(res: JobResult, cfg: JobConfig, iso_tool: Optional[Tool] = None, depth: float = 0.0) -> str:
    out = [f"Board {res.width:.2f} x {res.height:.2f} mm.  Import the DXF as millimetres.",
           "Tools, depths and offsets are your choice in VCarve; this sheet only says which layer is what.", ""]

    for side in res.copper:
        out += [f"{side} COPPER  (layer {side}_COPPER) - the real copper shapes",
                "  Toolpath : 2D Profile, machine vectors OUTSIDE/Right, with your V-bit",
                "  Offset   : Allowance offset 0.1 mm to start; 0.2 mm if you need more clearance"]
        if side == "BOTTOM":
            out.append("  Already mirrored. Flip the board left-to-right (around its vertical centre line) first.")
        if res.tight.get(side):
            out.append(f"  WARNING  : {len(res.tight[side])} spot(s) where copper is closer than {cfg.gap_check:g} mm "
                       f"(see layer {side}_WARN_TIGHT)")
        iso = res.isolation.get(side)
        if iso:
            s = cfg.isolation
            tool = iso_tool.name if iso_tool else f"{s.cut_width:.3f} mm cutter"
            out += [f"  Optional pre-offset passes (layers {side}_ISO_PASS1..{s.passes}): {tool}, "
                    f"groove {s.cut_width:.3f} mm at {depth:.3f} mm deep, {s.passes} pass(es) of {s.stepover:.3f} mm. "
                    f"These are already offset: Profile ON the vector, no allowance."]
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
        for w in res.drills.warnings[:5]:
            out.append(f"  note: {w}")
        if len(res.drills.warnings) > 5:
            out.append(f"  note: ... and {len(res.drills.warnings) - 5} more holes use a larger bit than their size")
        out.append("")
    if res.align:
        out.append(f"ALIGNMENT HOLES (layer ALIGN) - two {cfg.align_diameter:.1f} mm holes on the flip axis. "
                   f"Drill these first, before flipping.")
        out.append("")
    if res.outline is not None:
        out.append("OUTLINE (layer OUTLINE) - Profile OUTSIDE with the end mill, add tabs.")
    return "\n".join(out).rstrip() + "\n"
