import math
import sqlite3

import ezdxf
import pytest
from shapely.geometry import Point

from pcb2vectric import gerber_io
from pcb2vectric.drills import plan_drills
from pcb2vectric.dxf_out import write_dxf
from pcb2vectric.gerber_io import Hole
from pcb2vectric.isolation import IsolationSettings, find_tight_spots, generate_isolation
from pcb2vectric.job import JobConfig, build_job
from pcb2vectric.tools import Tool, read_vtdb

TOP = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.5*%
%ADD11R,2.0X1.5*%
G01*
%LPD*%
D10*
X0Y0D02*
X10000000Y0D01*
G75*
G03*
X20000000Y10000000I0J10000000D01*
G01*
D11*
X5000000Y5000000D03*
G36*
X30000000Y0D02*
X40000000Y0D01*
X40000000Y10000000D01*
X30000000Y10000000D01*
X30000000Y0D01*
G37*
%LPC*%
G36*
X33000000Y3000000D02*
X37000000Y3000000D01*
X37000000Y7000000D01*
X33000000Y7000000D01*
X33000000Y3000000D01*
G37*
M02*
"""

OUTLINE = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.1*%
G01*
D10*
X-2000000Y-2000000D02*
X42000000Y-2000000D01*
X42000000Y12000000D01*
X-2000000Y12000000D01*
X-2000000Y-2000000D01*
M02*
"""

DRILL = """M48
METRIC,TZ
T1C0.70
T2C1.00
T3C3.40
%
T1
X5.0Y5.0
T2
X10.0Y2.0
T3
X20.0Y8.0
M30
"""


@pytest.fixture
def files(tmp_path):
    for name, text in (("a.gtl", TOP), ("a.gbl", TOP), ("a.gko", OUTLINE), ("a.drl", DRILL)):
        (tmp_path / name).write_text(text)
    return {k: str(tmp_path / v) for k, v in dict(top="a.gtl", bottom="a.gbl", outline="a.gko", drill="a.drl").items()}


def test_copper_arcs_flashes_and_clear_polarity(files):
    cu = gerber_io.load_copper(files["top"])
    assert len(cu.geoms) == 3  # trace+arc, rectangle pad, pour
    pour_area = 100 - 16  # 10x10 pour minus clear 4x4 cut-out
    assert not cu.contains(Point(35, 5))  # clear region really removed
    assert cu.contains(Point(31, 1))
    # the arc (radius 10 about (10,10)) must be present: mid-arc at ~45 degrees
    a = math.radians(-45)
    assert cu.contains(Point(10 + 10 * math.cos(a), 10 + 10 * math.sin(a)))
    assert cu.area > pour_area


def test_outline(files):
    o = gerber_io.load_outline(files["outline"])
    assert o.bounds == pytest.approx((-2, -2, 42, 12))


def test_isolation_distance_and_passes():
    cu = Point(0, 0).buffer(2)
    s = IsolationSettings(cut_width=0.2, passes=3, overlap=0.25)
    res = generate_isolation(cu, s)
    assert len(res.passes) == 3
    for i, rings in enumerate(res.passes):
        expect = 0.1 + i * s.stepover
        d = rings[0].distance(Point(0, 0))
        assert d - 2 == pytest.approx(expect, abs=0.005)


def test_tight_spots():
    from shapely.geometry import box

    cu = box(0, 0, 1, 1).union(box(1.1, 0, 2, 1))  # 0.1 mm gap
    assert find_tight_spots(cu, 0.2)
    assert not find_tight_spots(cu, 0.05)


def test_drill_snapping_matches_user_rule():
    holes = [Hole(0, 0, 0.68), Hole(1, 0, 0.75), Hole(2, 0, 0.9), Hole(3, 0, 3.4)]
    plan = plan_drills(holes, [], [0.8, 1.0, 1.1, 1.2, 2.0, 3.0, 3.1])
    assert [h.diameter for h in plan.by_bit[0.8]] == [0.68, 0.75]
    assert 1.0 in plan.by_bit  # 0.9 -> 1.0
    assert len(plan.milled) == 1  # 3.4 bigger than any bit


def test_job_zero_mirror_align_and_dxf(files, tmp_path):
    cfg = JobConfig(top=files["top"], bottom=files["bottom"], outline=files["outline"], drills=[files["drill"]],
                    align_holes=True)
    res = build_job(cfg)
    assert (res.width, res.height) == pytest.approx((44, 14))
    assert res.outline.bounds == pytest.approx((0, 0, 44, 14))
    # bottom is the top mirrored across x = W/2 = 22
    t, b = res.copper["TOP"].bounds, res.copper["BOTTOM"].bounds
    assert b[0] == pytest.approx(44 - t[2]) and b[2] == pytest.approx(44 - t[0])
    assert [(h.x, h.y) for h in res.align] == pytest.approx([(22, -5), (22, 19)])

    out = tmp_path / "o.dxf"
    write_dxf(res, str(out))
    doc = ezdxf.readfile(out)
    layers = {l.dxf.name for l in doc.layers}
    assert {"TOP_ISO_PASS1", "TOP_ISO_PASS2", "BOTTOM_ISO_PASS1", "OUTLINE", "DRILL_0.80MM", "DRILL_1.00MM",
            "DRILL_MILL", "ALIGN"} <= layers
    assert doc.header["$INSUNITS"] == 4


def test_vtdb_reader(tmp_path):
    p = tmp_path / "t.vtdb"
    con = sqlite3.connect(p)
    con.executescript(
        """CREATE TABLE tool_geometry (id TEXT, name_format TEXT, tool_type INTEGER, units INTEGER,
             diameter REAL, included_angle REAL, flat_diameter REAL);
           CREATE TABLE tool_tree_entry (id TEXT, parent_group_id TEXT, tool_geometry_id TEXT, name TEXT);
           INSERT INTO tool_geometry VALUES ('a','30 deg V',4,1,0.25,30.0,0.0039370079);
           INSERT INTO tool_geometry VALUES ('b','.8mm Drill',1,0,0.8,NULL,NULL);
           INSERT INTO tool_geometry VALUES ('c','End Mill (1/8)',1,1,0.125,NULL,NULL);
           INSERT INTO tool_tree_entry VALUES ('g',NULL,NULL,'PCB Bits'); INSERT INTO tool_tree_entry VALUES ('x','g','a','30 deg V');"""
    )
    con.commit()
    con.close()
    tools = {t.name: t for t in read_vtdb(str(p))}
    v = tools["30 deg V"]
    assert v.kind == "vbit" and v.tip_diameter == pytest.approx(0.1)
    assert tools[".8mm Drill"].kind == "drill" and tools[".8mm Drill"].diameter == 0.8
    assert tools["End Mill (1/8)"].diameter == pytest.approx(3.175)


def test_vbit_width_depth_roundtrip():
    v = Tool("v", "vbit", 6.35, 30.0, 0.1)
    assert v.v_cut_width(0.1) == pytest.approx(0.1 + 2 * 0.1 * math.tan(math.radians(15)))
    assert v.v_depth_for_width(v.v_cut_width(0.07)) == pytest.approx(0.07)


def test_template_names_and_groups(tmp_path):
    p = tmp_path / "t.vtdb"
    con = sqlite3.connect(p)
    con.executescript(
        """CREATE TABLE tool_geometry (id TEXT, name_format TEXT, tool_type INTEGER, units INTEGER,
             diameter REAL, included_angle REAL, flat_diameter REAL);
           CREATE TABLE tool_tree_entry (id TEXT, parent_group_id TEXT, tool_geometry_id TEXT, name TEXT);
           INSERT INTO tool_geometry VALUES ('a','.8mm {Tool Type}',6,0,0.8,118.0,NULL);
           INSERT INTO tool_geometry VALUES ('b','20°, Tip {Flat Diameter} - {Diameter|F}{Units Short})',4,0,3.175,20.0,0.1);
           INSERT INTO tool_tree_entry VALUES ('g',NULL,NULL,'PCB Bits');
           INSERT INTO tool_tree_entry VALUES ('x','g','a',NULL);
           INSERT INTO tool_tree_entry VALUES ('y','g','b',NULL);"""
    )
    con.commit()
    con.close()
    tools = {t.name: t for t in read_vtdb(str(p))}
    assert tools[".8mm Drill"].kind == "drill" and tools[".8mm Drill"].group == "PCB Bits"
    assert "20°, Tip 0.1 - 3.175mm)" in tools


def test_detect_files(tmp_path):
    from pcb2vectric.detect import detect_files

    for n in ("Gerber_TopLayer.GTL", "Gerber_BottomLayer.GBL", "Gerber_BoardOutlineLayer.GKO"):
        (tmp_path / n).write_text("x")
    (tmp_path / "Drill_PTH_Through.DRL").write_text(DRILL)
    (tmp_path / "notes.txt").write_text("hello")  # .txt that isn't Excellon must be ignored
    d = detect_files(str(tmp_path))
    assert d.top.endswith("TopLayer.GTL") and d.bottom.endswith("BottomLayer.GBL") and d.outline.endswith(".GKO")
    assert [p.split("/")[-1] for p in d.drills] == ["Drill_PTH_Through.DRL"]


def test_gui_smoke(files, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    import time

    from pcb2vectric.gui.app import MainWindow

    app = widgets.QApplication.instance() or widgets.QApplication([])
    w = MainWindow()
    w.f_top.set_path(files["top"])
    w.f_out.set_path(files["outline"])
    w.f_drl.set_path(files["drill"])
    w._files_changed()
    end = time.time() + 10
    while w.result is None and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    assert w.result is not None and "TOP" in w.result.isolation
    assert "TOP ISOLATION" in w.sheet.toPlainText()
