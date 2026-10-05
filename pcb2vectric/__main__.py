"""Command line: python -m pcb2vectric <gerber_dir> out.dxf  (GUI to follow)."""

import argparse
import glob
import os

from .dxf_out import write_dxf
from .job import JobConfig, build_job
from .isolation import IsolationSettings


def _find(d, *patterns):
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(d, pat), recursive=False))
        if hits:
            return hits[0]
    return None


def main() -> None:
    ap = argparse.ArgumentParser(prog="pcb2vectric")
    ap.add_argument("folder")
    ap.add_argument("out")
    ap.add_argument("--cut-width", type=float, default=0.2)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--overlap", type=float, default=0.3)
    ap.add_argument("--align", action="store_true")
    a = ap.parse_args()

    cfg = JobConfig(
        top=_find(a.folder, "*.gtl", "*.GTL", "*Top*.gbr", "*top*.gbr"),
        bottom=_find(a.folder, "*.gbl", "*.GBL", "*Bottom*.gbr", "*bottom*.gbr"),
        outline=_find(a.folder, "*.gko", "*.GKO", "*.gm1", "*.GM1", "*Outline*.gbr", "*outline*.gbr"),
        drills=[p for p in (_find(a.folder, "*.drl", "*.DRL", "*.xln", "*.XLN", "*.txt"),) if p],
        isolation=IsolationSettings(a.cut_width, a.passes, a.overlap),
        align_holes=a.align,
    )
    res = build_job(cfg)
    write_dxf(res, a.out)
    print(f"Board {res.width:.2f} x {res.height:.2f} mm -> {a.out}")
    for side, iso in res.isolation.items():
        if iso.tight_spots:
            print(f"  WARNING: {len(iso.tight_spots)} spots on {side} where copper gaps are narrower than the cut")
    for w in res.drills.warnings:
        print("  note:", w)


if __name__ == "__main__":
    main()
