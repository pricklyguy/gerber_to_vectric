"""Map Excellon holes onto the drill bits you actually own."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .gerber_io import Hole, Slot


@dataclass
class DrillPlan:
    by_bit: Dict[float, List[Hole]] = field(default_factory=dict)  # bit diameter -> holes (x, y)
    milled: List[Hole] = field(default_factory=list)  # too big for any bit: cut with the end mill
    slots: List[Slot] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def plan_drills(
    holes: Sequence[Hole],
    slots: Sequence[Slot],
    bits: Sequence[float],
    oversize_warn: float = 0.3,
    max_drill: float | None = None,
) -> DrillPlan:
    """Assign each hole to the smallest bit that is >= the hole (so 0.68/0.70/0.75 -> 0.8).

    Holes larger than `max_drill` (default: the biggest bit) are milled instead.
    """
    plan = DrillPlan(slots=list(slots))
    bits = sorted(set(round(b, 4) for b in bits))
    if not bits:
        raise ValueError("No drill bits configured")
    limit = max_drill if max_drill is not None else bits[-1]
    for h in holes:
        if h.diameter > limit + 1e-6:
            plan.milled.append(h)
            continue
        bit = next(b for b in bits if b >= h.diameter - 1e-6)
        if bit - h.diameter > oversize_warn:
            plan.warnings.append(
                f"{h.diameter:.2f} mm hole at ({h.x:.2f}, {h.y:.2f}) will be drilled with {bit:.2f} mm bit"
            )
        plan.by_bit.setdefault(bit, []).append(h)
    return plan
