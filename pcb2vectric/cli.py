"""Command line interface (the GUI is the default when no folder is given)."""

import argparse

from .detect import detect_files
from .dxf_out import write_dxf
from .isolation import IsolationSettings
from .job import JobConfig, build_job


def run(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="pcb2vectric")
    ap.add_argument("folder")
    ap.add_argument("out")
    ap.add_argument("--isolation", action="store_true", help="also write offset isolation passes")
    ap.add_argument("--gap-check", type=float, default=0.2, help="warn on copper gaps narrower than this (mm), 0 = off")
    ap.add_argument("--cut-width", type=float, default=0.2)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--overlap", type=float, default=0.3)
    ap.add_argument("--keep-vias", action="store_true", help="drill vias and keep their pads (default: ignore)")
    ap.add_argument("--align", action="store_true")
    a = ap.parse_args(argv)

    d = detect_files(a.folder)
    cfg = JobConfig(top=d.top, bottom=d.bottom, outline=d.outline, drills=d.drills,
                    isolation=IsolationSettings(a.cut_width, a.passes, a.overlap), precompute_isolation=a.isolation,
                    gap_check=a.gap_check, skip_vias=not a.keep_vias, align_holes=a.align)
    res = build_job(cfg)
    write_dxf(res, a.out)
    print(f"Board {res.width:.2f} x {res.height:.2f} mm -> {a.out}")
    for side, pts in res.tight.items():
        if pts:
            print(f"  WARNING: {len(pts)} spots on {side} where copper gaps are narrower than {a.gap_check} mm")
    for w in res.drills.warnings:
        print("  note:", w)
