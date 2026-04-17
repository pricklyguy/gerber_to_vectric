#!/usr/bin/env python3
"""
Gerber/Excellon to DXF converter for VCarve Pro.

Includes:
- Copper trace + pad polygon creation
- Optional isolation contour generation
- Drill overlay output
- Optional Tkinter GUI mode for interactive usage
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import ezdxf
except ImportError as exc:  # pragma: no cover - hard dependency
    raise SystemExit("ERROR: ezdxf is required. Install with: pip install ezdxf") from exc

try:
    from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
    from shapely.ops import unary_union

    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


@dataclass
class GerberPoint:
    x: float
    y: float


class ExcellonParser:
    """Parse Excellon drill files."""

    def __init__(self) -> None:
        self.drills: List[dict] = []
        self.current_tool: Optional[str] = None
        self.tools: Dict[str, float] = {}
        self.unit = "mm"
        self.format_x = "2.4"
        self.format_y = "2.4"
        self.copper_bounds: Optional[Tuple[float, float, float, float]] = None

    @staticmethod
    def parse_coordinate(coord_str: str, format_spec: str) -> float:
        if not coord_str:
            raise ValueError("Empty coordinate")
        value = int(coord_str)
        _, decimal_digits = map(int, format_spec.split("."))
        divisor = 10**decimal_digits
        return value / divisor

    def parse_file(self, filename: str) -> List[dict]:
        print(f"  Parsing drill file: {os.path.basename(filename)}")

        with open(filename, "r", encoding="utf-8", errors="ignore") as file:
            lines = file.readlines()

        sample_coords: List[str] = []
        for line in lines[:150]:
            line = line.strip()
            if "INCH" in line or "MILS" in line:
                self.unit = "inch"
            elif "METRIC" in line or "MM" in line:
                self.unit = "mm"

            if "X" in line and "Y" in line and "T" not in line:
                x_match = re.search(r"X([+-]?\d+\.?\d*)", line)
                if x_match:
                    sample_coords.append(x_match.group(1))

        if sample_coords and "." not in sample_coords[0]:
            digits = len(sample_coords[0])
            if digits >= 6:
                self.format_x = self.format_y = "2.4"
            elif digits == 5:
                self.format_x = self.format_y = "2.3"
            elif digits == 4:
                self.format_x = self.format_y = "2.2"

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("T") and "C" in line:
                match = re.search(r"T(\d+).*?C([0-9.]+)", line)
                if match:
                    tool_num = match.group(1)
                    diameter = float(match.group(2))
                    if self.unit == "inch":
                        diameter *= 25.4
                    self.tools[tool_num] = diameter
                continue

            if line.startswith("T") and "C" not in line and "X" not in line and "Y" not in line:
                if len(line) <= 4 and line[1:].isdigit():
                    self.current_tool = line[1:]
                continue

            if "X" in line and "Y" in line:
                x_match = re.search(r"X([+-]?\d+\.?\d*)", line)
                y_match = re.search(r"Y([+-]?\d+\.?\d*)", line)
                if not (x_match and y_match):
                    continue

                x_str = x_match.group(1)
                y_str = y_match.group(1)

                if "." in x_str:
                    x = float(x_str)
                    y = float(y_str)
                else:
                    x = self.parse_coordinate(x_str, self.format_x)
                    y = self.parse_coordinate(y_str, self.format_y)

                if self.unit == "inch":
                    x *= 25.4
                    y *= 25.4

                diameter = self.tools.get(self.current_tool or "", 0.8)
                self.drills.append({"x": x, "y": y, "diameter": diameter})

        self._validate_and_retry_if_needed(filename)
        print(f"    Drill format: {self.format_x} ({self.unit})")
        print(f"    Holes found: {len(self.drills)}")
        return self.drills

    def _validate_and_retry_if_needed(self, filename: str) -> None:
        if len(self.drills) < 4 or not self.copper_bounds:
            return

        cminx, cmaxx, cminy, cmaxy = self.copper_bounds
        cwidth = max(cmaxx - cminx, 1e-9)
        cheight = max(abs(cmaxy - cminy), 1e-9)

        xs = [d["x"] for d in self.drills]
        ys = [d["y"] for d in self.drills]
        dwidth = max(xs) - min(xs)
        dheight = max(ys) - min(ys)

        if dwidth / cwidth >= 0.15 and dheight / cheight >= 0.15:
            return

        self.format_x = self.format_y = "2.3"
        self.drills = []
        self.current_tool = None

        with open(filename, "r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("T") and "C" not in line and "X" not in line and "Y" not in line:
                    if len(line) <= 4 and line[1:].isdigit():
                        self.current_tool = line[1:]
                    continue

                if "X" in line and "Y" in line:
                    x_match = re.search(r"X([+-]?\d+\.?\d*)", line)
                    y_match = re.search(r"Y([+-]?\d+\.?\d*)", line)
                    if not (x_match and y_match):
                        continue

                    x_str = x_match.group(1)
                    y_str = y_match.group(1)
                    if "." in x_str:
                        x = float(x_str)
                        y = float(y_str)
                    else:
                        x = self.parse_coordinate(x_str, self.format_x)
                        y = self.parse_coordinate(y_str, self.format_y)

                    if self.unit == "inch":
                        x *= 25.4
                        y *= 25.4

                    diameter = self.tools.get(self.current_tool or "", 0.8)
                    self.drills.append({"x": x, "y": y, "diameter": diameter})


class GerberParser:
    """Lightweight Gerber RS-274X parser for copper geometry extraction."""

    def __init__(self) -> None:
        self.current_x = 0.0
        self.current_y = 0.0
        self.format_x = "2.4"
        self.format_y = "2.4"
        self.unit = "mm"

        self.paths: List[List[GerberPoint]] = []
        self.current_path: List[GerberPoint] = []
        self.current_path_aperture: Optional[str] = None

        self.apertures: Dict[str, dict] = {}
        self.current_aperture: Optional[str] = None

        self.current_operation = "D02"  # modal state: move by default

        self.flashes: List[dict] = []
        self.regions: List[List[GerberPoint]] = []
        self.in_region = False
        self.region_points: List[GerberPoint] = []

        self.path_apertures: List[Optional[str]] = []

    @staticmethod
    def parse_coordinate(coord_str: str, format_spec: str) -> float:
        value = int(coord_str)
        _, decimal_digits = map(int, format_spec.split("."))
        return value / (10**decimal_digits)

    def _flush_current_path(self) -> None:
        if self.current_path and len(self.current_path) > 1:
            self.paths.append(self.current_path)
            self.path_apertures.append(self.current_path_aperture or self.current_aperture)
        self.current_path = []
        self.current_path_aperture = None

    def _apply_units(self, value: float) -> float:
        return value * 25.4 if self.unit == "inch" else value

    def parse_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return

        if "FSLAX" in line or "FSTAX" in line:
            match = re.search(r"FSL?[AT]X(\d)(\d)Y(\d)(\d)", line)
            if match:
                self.format_x = f"{match.group(1)}.{match.group(2)}"
                self.format_y = f"{match.group(3)}.{match.group(4)}"
            return

        if "MOIN" in line:
            self.unit = "inch"
        elif "MOMM" in line:
            self.unit = "mm"

        if line.startswith("%ADD"):
            match = re.search(r"%ADD(\d+)([A-Za-z][A-Za-z0-9_]*),([^*]+)", line)
            if match:
                num, kind, params = match.groups()
                kind = kind.upper()
                parts = [p.strip() for p in params.split("X") if p.strip()]

                # Circle aperture, ignore optional hole modifiers after first value
                if kind.startswith("C"):
                    size = float(parts[0])
                    self.apertures[num] = {"type": "circle", "size": size}

                # Rectangle / round-rect fallback
                elif kind.startswith("R") or kind == "ROUNDRECT":
                    if len(parts) >= 2:
                        w = float(parts[0])
                        h = float(parts[1])
                    else:
                        w = h = float(parts[0])
                    self.apertures[num] = {
                        "type": "rectangle",
                        "size": max(w, h),
                        "width": w,
                        "height": h,
                    }

                # Obround
                elif kind.startswith("O"):
                    if len(parts) >= 2:
                        w = float(parts[0])
                        h = float(parts[1])
                    else:
                        w = h = float(parts[0])
                    self.apertures[num] = {
                        "type": "obround",
                        "size": max(w, h),
                        "width": w,
                        "height": h,
                    }
            return

        if "G36" in line:
            self._flush_current_path()
            self.in_region = True
            self.region_points = []
            return

        if "G37" in line:
            if self.in_region and len(self.region_points) > 2:
                if (
                    self.region_points[0].x != self.region_points[-1].x
                    or self.region_points[0].y != self.region_points[-1].y
                ):
                    self.region_points.append(
                        GerberPoint(self.region_points[0].x, self.region_points[0].y)
                    )
                self.regions.append(self.region_points)
            self.in_region = False
            self.region_points = []
            return

        if line.startswith("%"):
            return

        aperture_or_op = re.fullmatch(r"(?:G54)?D(\d+)\*", line)
        if aperture_or_op:
            code = aperture_or_op.group(1)
            if code.isdigit():
                n = int(code)
                if n >= 10:
                    self._flush_current_path()
                    self.current_aperture = code
                elif n in (1, 2, 3):
                    self.current_operation = f"D{n:02d}"
            return

        x_match = re.search(r"X([+-]?\d+)", line)
        y_match = re.search(r"Y([+-]?\d+)", line)

        new_x = self.current_x
        new_y = self.current_y

        if x_match:
            new_x = self.parse_coordinate(x_match.group(1), self.format_x)
            new_x = self._apply_units(new_x)

        if y_match:
            new_y = self.parse_coordinate(y_match.group(1), self.format_y)
            new_y = self._apply_units(new_y)

        op_match = re.search(r"D0([123])", line)
        if op_match:
            self.current_operation = f"D0{op_match.group(1)}"

        op = self.current_operation

        if not x_match and not y_match and op != "D03":
            return

        if op == "D03":
            self._flush_current_path()
            if self.current_aperture and self.current_aperture in self.apertures:
                self.flashes.append({"x": new_x, "y": new_y, "aperture": self.current_aperture})

        elif op == "D02":
            self._flush_current_path()
            if self.in_region:
                self.region_points = [GerberPoint(new_x, new_y)]

        elif op == "D01":
            if self.in_region:
                if not self.region_points:
                    self.region_points = [GerberPoint(self.current_x, self.current_y)]
                self.region_points.append(GerberPoint(new_x, new_y))
            else:
                if not self.current_path:
                    self.current_path = [GerberPoint(self.current_x, self.current_y)]
                    self.current_path_aperture = self.current_aperture
                self.current_path.append(GerberPoint(new_x, new_y))

        self.current_x = new_x
        self.current_y = new_y

    def parse_file(self, filename: str):
        print(f"  Parsing copper file: {os.path.basename(filename)}")
        with open(filename, "r", encoding="utf-8", errors="ignore") as file:
            for line in file:
                self.parse_line(line)

        self._flush_current_path()

        print(f"    Paths={len(self.paths)}, Flashes={len(self.flashes)}, Regions={len(self.regions)}")
        return self.paths, self.flashes, self.regions, self.path_apertures, self.apertures


class DXFExporter:
    """Collect copper/drill geometry and write layered DXF output."""

    def __init__(self, default_trace_width: float = 0.25, isolation_offset: float = 0.2) -> None:
        self.doc = ezdxf.new("R2010")
        self.msp = self.doc.modelspace()
        self.default_trace_width = default_trace_width
        self.isolation_offset = isolation_offset
        self.copper_geometries: Dict[str, list] = {}
        self.drill_geometries: List = []

    def _append_geom(self, layer: str, geom) -> None:
        if geom is None:
            return
        try:
            if geom.is_empty:
                return
        except Exception:
            pass
        self.copper_geometries.setdefault(layer, []).append(geom)

    def _clean_geom(self, geom):
        if geom is None:
            return None
        try:
            if geom.is_empty:
                return None
            if hasattr(geom, "is_valid") and not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty:
                return None
            return geom
        except Exception:
            return None

    def _iter_polygons(self, geom):
        if geom is None:
            return
        try:
            if geom.is_empty:
                return
        except Exception:
            return

        if isinstance(geom, Polygon):
            yield geom
            return

        if isinstance(geom, MultiPolygon):
            for g in geom.geoms:
                yield g
            return

        if isinstance(geom, GeometryCollection):
            for g in geom.geoms:
                yield from self._iter_polygons(g)
            return

        if hasattr(geom, "geoms"):
            for g in geom.geoms:
                yield from self._iter_polygons(g)

    def add_path_as_polygon(self, path: List[GerberPoint], layer: str, trace_width: Optional[float]) -> None:
        if len(path) < 2:
            return

        if not SHAPELY_AVAILABLE:
            pts = [(p.x, p.y) for p in path]
            self.msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
            return

        width = trace_width if trace_width else self.default_trace_width
        line = LineString([(p.x, p.y) for p in path])
        poly = line.buffer(width / 2.0, cap_style=1, join_style=1)
        poly = self._clean_geom(poly)
        self._append_geom(layer, poly)

    def add_region(self, region: List[GerberPoint], layer: str) -> None:
        if len(region) < 3:
            return

        pts = [(p.x, p.y) for p in region]
        if pts[0] != pts[-1]:
            pts.append(pts[0])

        if SHAPELY_AVAILABLE:
            poly = Polygon(pts)
            poly = self._clean_geom(poly)
            self._append_geom(layer, poly)
        else:
            self.msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "closed": True})

    def _make_obround(self, x: float, y: float, w: float, h: float):
        if not SHAPELY_AVAILABLE:
            return None

        if abs(w - h) < 1e-9:
            return Point(x, y).buffer(w / 2.0, resolution=32)

        if w > h:
            radius = h / 2.0
            half_len = (w - h) / 2.0
            line = LineString([(x - half_len, y), (x + half_len, y)])
            return line.buffer(radius, cap_style=1, join_style=1)

        radius = w / 2.0
        half_len = (h - w) / 2.0
        line = LineString([(x, y - half_len), (x, y + half_len)])
        return line.buffer(radius, cap_style=1, join_style=1)

    def add_flash(self, flash: dict, apertures: dict, layer: str) -> None:
        aperture = apertures.get(flash["aperture"])
        if not aperture:
            return

        x = flash["x"]
        y = flash["y"]
        typ = aperture.get("type")

        if SHAPELY_AVAILABLE:
            if typ == "circle":
                geom = Point(x, y).buffer(aperture["size"] / 2.0, resolution=32)

            elif typ == "rectangle":
                w = aperture.get("width", aperture["size"])
                h = aperture.get("height", aperture["size"])
                geom = Polygon(
                    [
                        (x - w / 2, y - h / 2),
                        (x + w / 2, y - h / 2),
                        (x + w / 2, y + h / 2),
                        (x - w / 2, y + h / 2),
                    ]
                )

            elif typ == "obround":
                w = aperture.get("width", aperture["size"])
                h = aperture.get("height", aperture["size"])
                geom = self._make_obround(x, y, w, h)

            else:
                geom = Point(x, y).buffer(aperture["size"] / 2.0, resolution=32)

            geom = self._clean_geom(geom)
            self._append_geom(layer, geom)
            return

        size = aperture.get("size", 0.5)
        self.msp.add_circle((x, y), size / 2.0, dxfattribs={"layer": layer})

    def add_drill(self, drill: dict, layer: str = "DRILLS") -> None:
        radius = drill["diameter"] / 2.0
        self.msp.add_circle((drill["x"], drill["y"]), radius, dxfattribs={"layer": layer})

        if SHAPELY_AVAILABLE:
            geom = Point(drill["x"], drill["y"]).buffer(radius, resolution=32)
            geom = self._clean_geom(geom)
            if geom is not None:
                self.drill_geometries.append(geom)

    def add_outline_path(self, path: List[GerberPoint], layer: str = "BOARD_OUTLINE") -> None:
        if len(path) < 2:
            return
        self.msp.add_lwpolyline([(p.x, p.y) for p in path], dxfattribs={"layer": layer})

    def _emit_polygon(self, polygon, layer: str) -> None:
        polygon = self._clean_geom(polygon)
        if polygon is None:
            return

        ext = list(polygon.exterior.coords)
        if len(ext) >= 2:
            self.msp.add_lwpolyline(ext, dxfattribs={"layer": layer, "closed": True})

        for interior in polygon.interiors:
            pts = list(interior.coords)
            if len(pts) >= 2:
                self.msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "closed": True})

    def finalize_copper(self, include_isolation: bool = False) -> None:
        if not SHAPELY_AVAILABLE:
            return

        weld_eps = 0.0002  # tiny weld to join touching boundaries without changing shape much

        for layer, geometries in self.copper_geometries.items():
            cleaned = []
            for geom in geometries:
                geom = self._clean_geom(geom)
                if geom is not None:
                    cleaned.append(geom)

            if not cleaned:
                continue

            try:
                merged = unary_union(cleaned)
                merged = self._clean_geom(merged)
            except Exception:
                merged = None

            # If merge fails, fall back to raw polygons so we still get usable output
            if merged is None:
                for geom in cleaned:
                    for poly in self._iter_polygons(geom):
                        self._emit_polygon(poly, layer)
                continue

            # Tiny weld pass to mimic VCarve "Weld" behavior
            try:
                merged = merged.buffer(weld_eps, join_style=1).buffer(-weld_eps, join_style=1)
                merged = self._clean_geom(merged)
            except Exception:
                pass

            if merged is None:
                for geom in cleaned:
                    for poly in self._iter_polygons(geom):
                        self._emit_polygon(poly, layer)
                continue

            for poly in self._iter_polygons(merged):
                self._emit_polygon(poly, layer)

            # leave isolation OFF for now until copper is stable

    def save(self, filename: str) -> None:
        self.doc.saveas(filename)
        print(f"\nDXF saved: {filename}")
        
def process_pcb_to_dxf(
    file_dict: dict,
    output_file: str,
    use_only_regions: bool = False,
    default_trace_width: float = 1.25,
    isolation_offset: float = 0.10,
    include_isolation: bool = True,
    include_copper_regions: bool = False,
) -> None:
    exporter = DXFExporter(default_trace_width=default_trace_width, isolation_offset=isolation_offset)

    copper_min_x, copper_max_x = float("inf"), float("-inf")
    copper_min_y, copper_max_y = float("inf"), float("-inf")

    def update_bounds(paths, regions):
        nonlocal copper_min_x, copper_max_x, copper_min_y, copper_max_y
        for seq in (paths + regions):
            for p in seq:
                copper_min_x = min(copper_min_x, p.x)
                copper_max_x = max(copper_max_x, p.x)
                copper_min_y = min(copper_min_y, p.y)
                copper_max_y = max(copper_max_y, p.y)

    for side_name, key in (("TOP", "top_copper"), ("BOTTOM", "bottom_copper")):
        if not file_dict.get(key):
            continue

        print(f"\nProcessing {side_name} copper")
        parser = GerberParser()
        paths, flashes, regions, path_apertures, apertures = parser.parse_file(file_dict[key])
        update_bounds(paths, regions)

        if not use_only_regions:
            for idx, path in enumerate(paths):
                ap_id = path_apertures[idx] if idx < len(path_apertures) else None
                trace_width = apertures.get(ap_id, {}).get("size") if ap_id else None
                exporter.add_path_as_polygon(path, layer=f"{side_name}_COPPER", trace_width=trace_width)

        if include_copper_regions:
            for region in regions:
                exporter.add_region(region, layer=f"{side_name}_COPPER")
        for flash in flashes:
            exporter.add_flash(flash, apertures, layer=f"{side_name}_COPPER")

    if file_dict.get("board_outline"):
        print("\nProcessing board outline")
        parser = GerberParser()
        paths, _, regions, _, _ = parser.parse_file(file_dict["board_outline"])
        for path in paths:
            exporter.add_outline_path(path)
        for region in regions:
            exporter.add_region(region, layer="BOARD_OUTLINE")

    if copper_min_x < float("inf"):
        print(
            f"\nCopper bounds: X=[{copper_min_x:.3f}, {copper_max_x:.3f}], "
            f"Y=[{copper_min_y:.3f}, {copper_max_y:.3f}]"
        )

    all_drills: List[dict] = []
    for drill_file in file_dict.get("drills", []):
        parser = ExcellonParser()
        if copper_min_x < float("inf"):
            parser.copper_bounds = (copper_min_x, copper_max_x, copper_min_y, copper_max_y)
        all_drills.extend(parser.parse_file(drill_file))

    for drill in all_drills:
        exporter.add_drill(drill)

    exporter.finalize_copper(include_isolation=include_isolation)
    exporter.save(output_file)


def detect_files(gerber_dir: str) -> dict:
    files = {"top_copper": None, "bottom_copper": None, "board_outline": None, "drills": []}
    for filename in os.listdir(gerber_dir):
        filepath = os.path.join(gerber_dir, filename)
        upper_name = filename.upper()

        if ("TOP" in upper_name and upper_name.endswith((".GTL", ".TOP", ".CMP"))) or "TOPLAYER" in upper_name:
            files["top_copper"] = filepath
        elif ("BOTTOM" in upper_name and upper_name.endswith((".GBL", ".BOT", ".SOL"))) or "BOTTOMLAYER" in upper_name:
            files["bottom_copper"] = filepath
        elif "OUTLINE" in upper_name or upper_name.endswith((".GKO", ".GM1", ".GML")):
            files["board_outline"] = filepath
        elif upper_name.endswith((".DRL", ".TXT", ".XLN")) and (
            "DRILL" in upper_name or "PTH" in upper_name or "NPTH" in upper_name or upper_name.endswith(".DRL")
        ):
            files["drills"].append(filepath)

    return files


def run_cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python export_script.py <gerber_directory> [output.dxf]")
        raise SystemExit(1)

    gerber_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "pcb_complete.dxf"

    files = detect_files(gerber_dir)
    if not any([files["top_copper"], files["bottom_copper"], files["board_outline"], files["drills"]]):
        raise SystemExit("No Gerber/Excellon files detected.")

    process_pcb_to_dxf(files, output_file)


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Gerber to DXF by The Prickly Guy")
    root.geometry("900x610")
    root.minsize(860, 580)

    COLORS = {
        "bg": "#111111",
        "panel": "#1a1a1a",
        "panel2": "#232323",
        "panel3": "#2b2b2b",
        "text": "#f4efe7",
        "muted": "#c9b8a3",
        "accent": "#c97a2b",
        "accent_hover": "#de8c38",
        "accent_press": "#a55f1b",
        "accent_dark": "#7f4814",
        "border": "#3a2a1d",
        "entry": "#0f0f0f",
        "success": "#6bbf59",
        "danger": "#d06060",
        "soft": "#353535",
    }

    root.configure(bg=COLORS["bg"])

    style = ttk.Style()
    style.theme_use("clam")

    default_font = ("Segoe UI", 10)
    title_font = ("Segoe UI Semibold", 20)
    subtitle_font = ("Segoe UI", 10)
    section_font = ("Segoe UI Semibold", 10)
    small_font = ("Segoe UI", 9)

    style.configure(
        "Dark.TEntry",
        fieldbackground=COLORS["entry"],
        background=COLORS["entry"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        insertcolor=COLORS["text"],
        padding=7,
        relief="flat",
    )

    vars_ = {
        "top": tk.StringVar(),
        "bottom": tk.StringVar(),
        "outline": tk.StringVar(),
        "drills": tk.StringVar(),
        "output": tk.StringVar(value=os.path.abspath("pcb_complete.dxf")),
        "isolation": tk.DoubleVar(value=0.10),
        "default_width": tk.DoubleVar(value=1.25),
        "regions_only": tk.BooleanVar(value=False),
        "include_copper_regions": tk.BooleanVar(value=False),
        "write_iso": tk.BooleanVar(value=False),
    }

    status_var = tk.StringVar(value="Ready. Choose files or auto-detect a Gerber folder.")

    def set_status(message: str) -> None:
        status_var.set(message)
        root.update_idletasks()

    def make_button(parent, text, command, variant="secondary", width=None):
        if variant == "primary":
            bg = COLORS["accent"]
            fg = "#ffffff"
            hover = COLORS["accent_hover"]
            pressed = COLORS["accent_press"]
            border = COLORS["accent_dark"]
        elif variant == "ghost":
            bg = COLORS["bg"]
            fg = COLORS["muted"]
            hover = COLORS["panel2"]
            pressed = COLORS["panel3"]
            border = COLORS["soft"]
        else:
            bg = COLORS["panel3"]
            fg = COLORS["text"]
            hover = "#343434"
            pressed = "#2b2b2b"
            border = COLORS["border"]

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            font=("Segoe UI Semibold", 10) if variant == "primary" else ("Segoe UI", 10),
            cursor="hand2",
            width=width,
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
        )

        def on_enter(_event):
            btn.configure(bg=hover)

        def on_leave(_event):
            btn.configure(bg=bg)

        def on_press(_event):
            btn.configure(bg=pressed)

        def on_release(_event):
            if btn.winfo_containing(root.winfo_pointerx(), root.winfo_pointery()) == btn:
                btn.configure(bg=hover)
            else:
                btn.configure(bg=bg)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<ButtonPress-1>", on_press)
        btn.bind("<ButtonRelease-1>", on_release)
        return btn

    def make_check(parent, text, variable):
        cb = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["panel"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["panel2"],
            bd=0,
            highlightthickness=0,
            font=default_font,
            cursor="hand2",
        )
        return cb

    def browse_file(target: str, title: str):
        path = filedialog.askopenfilename(title=title)
        if path:
            vars_[target].set(path)
            set_status(f"Loaded {os.path.basename(path)}")

    def browse_drills():
        paths = filedialog.askopenfilenames(
            title="Select drill files",
            filetypes=[("Drill files", "*.drl *.xln *.txt"), ("All files", "*.*")],
        )
        if paths:
            vars_["drills"].set(";".join(paths))
            set_status(f"Loaded {len(paths)} drill file(s)")

    def autodetect():
        folder = filedialog.askdirectory(title="Select Gerber folder")
        if not folder:
            return
        found = detect_files(folder)
        vars_["top"].set(found.get("top_copper") or "")
        vars_["bottom"].set(found.get("bottom_copper") or "")
        vars_["outline"].set(found.get("board_outline") or "")
        vars_["drills"].set(";".join(found.get("drills") or []))
        vars_["output"].set(os.path.join(folder, "pcb_complete.dxf"))

        found_count = sum(
            1 for item in [
                found.get("top_copper"),
                found.get("bottom_copper"),
                found.get("board_outline"),
            ] if item
        ) + len(found.get("drills") or [])

        set_status(f"Auto-detected files in {os.path.basename(folder)} ({found_count} item(s))")

    def clear_paths():
        vars_["top"].set("")
        vars_["bottom"].set("")
        vars_["outline"].set("")
        vars_["drills"].set("")
        vars_["output"].set(os.path.abspath("pcb_complete.dxf"))
        set_status("Cleared selected files.")

    def export_now():
        drills = [d for d in vars_["drills"].get().split(";") if d]
        file_dict = {
            "top_copper": vars_["top"].get() or None,
            "bottom_copper": vars_["bottom"].get() or None,
            "board_outline": vars_["outline"].get() or None,
            "drills": drills,
        }

        if not any([
            file_dict["top_copper"],
            file_dict["bottom_copper"],
            file_dict["board_outline"],
            file_dict["drills"],
        ]):
            messagebox.showerror("Missing files", "Please select at least one Gerber or drill file.", parent=root)
            set_status("Export blocked: no files selected.")
            return

        try:
            set_status("Exporting DXF...")
            process_pcb_to_dxf(
                file_dict,
                vars_["output"].get(),
                use_only_regions=vars_["regions_only"].get(),
                default_trace_width=vars_["default_width"].get(),
                isolation_offset=vars_["isolation"].get(),
                include_isolation=vars_["write_iso"].get(),
                include_copper_regions=vars_["include_copper_regions"].get(),
            )
            set_status(f"Export complete: {os.path.basename(vars_['output'].get())}")
            messagebox.showinfo("Done", f"DXF exported:\n{vars_['output'].get()}", parent=root)
        except Exception as exc:
            set_status("Export failed.")
            messagebox.showerror("Export failed", str(exc), parent=root)

    def add_file_row(parent, row, label, key, button_text, callback):
        lbl = tk.Label(
            parent,
            text=label,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=default_font,
            anchor="w",
        )
        lbl.grid(row=row, column=0, sticky="w", pady=7)

        entry = ttk.Entry(parent, textvariable=vars_[key], style="Dark.TEntry", width=78)
        entry.grid(row=row, column=1, sticky="ew", padx=12)

        btn = make_button(parent, button_text, callback, variant="secondary", width=11)
        btn.grid(row=row, column=2, sticky="e")

    root.bind("<Control-e>", lambda _e: export_now())
    root.bind("<Control-d>", lambda _e: autodetect())
    root.bind("<Control-l>", lambda _e: clear_paths())
    root.bind("<Escape>", lambda _e: root.destroy())

    app = tk.Frame(root, bg=COLORS["bg"], padx=16, pady=14)
    app.pack(fill="both", expand=True)

    top_bar = tk.Frame(app, bg=COLORS["accent"], height=3)
    top_bar.pack(fill="x", pady=(0, 10))
    top_bar.pack_propagate(False)

    header = tk.Frame(
        app,
        bg=COLORS["panel2"],
        padx=16,
        pady=14,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
    )
    header.pack(fill="x", pady=(0, 14))

    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prickly_guy_small.png")
    logo_loaded = False
    if os.path.exists(logo_path):
        try:
            root._logo_img_full = tk.PhotoImage(file=logo_path)
            root._logo_img = root._logo_img_full.subsample(2, 2)
            logo_label = tk.Label(
                header,
                image=root._logo_img,
                bg=COLORS["panel2"],
                bd=0,
                highlightthickness=0,
            )
            logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 14), sticky="w")
            try:
                root.iconphoto(True, root._logo_img_full)
            except Exception:
                pass
            logo_loaded = True
        except Exception:
            logo_loaded = False

    title_col = 1 if logo_loaded else 0

    tk.Label(
        header,
        text="Gerber to DXF by The Prickly Guy",
        bg=COLORS["panel2"],
        fg=COLORS["text"],
        font=title_font,
        anchor="w",
    ).grid(row=0, column=title_col, sticky="w")

    tk.Label(
        header,
        text="Dark copper mode for the VCarve workflow",
        bg=COLORS["panel2"],
        fg=COLORS["muted"],
        font=subtitle_font,
        anchor="w",
    ).grid(row=1, column=title_col, sticky="w", pady=(4, 0))

    badge = tk.Label(
        header,
        text="CNC APP",
        bg=COLORS["accent_dark"],
        fg="#ffffff",
        font=("Segoe UI Semibold", 9),
        padx=10,
        pady=4,
    )
    badge.grid(row=0, column=title_col + 1, rowspan=2, sticky="e", padx=(12, 0))

    header.columnconfigure(title_col, weight=1)

    files_frame = tk.LabelFrame(
        app,
        text="Project files",
        bg=COLORS["panel"],
        fg=COLORS["accent"],
        font=section_font,
        padx=14,
        pady=12,
        bd=1,
        relief="solid",
        highlightbackground=COLORS["border"],
    )
    files_frame.pack(fill="x", pady=(0, 12))

    add_file_row(files_frame, 0, "Top copper", "top", "Browse", lambda: browse_file("top", "Select top copper Gerber"))
    add_file_row(files_frame, 1, "Bottom copper", "bottom", "Browse", lambda: browse_file("bottom", "Select bottom copper Gerber"))
    add_file_row(files_frame, 2, "Board outline", "outline", "Browse", lambda: browse_file("outline", "Select board outline Gerber"))

    tk.Label(files_frame, text="Drill files", bg=COLORS["panel"], fg=COLORS["text"], font=default_font).grid(
        row=3, column=0, sticky="w", pady=7
    )
    ttk.Entry(files_frame, textvariable=vars_["drills"], style="Dark.TEntry", width=78).grid(
        row=3, column=1, sticky="ew", padx=12
    )
    make_button(files_frame, "Select", browse_drills, variant="secondary", width=11).grid(
        row=3, column=2, sticky="e"
    )

    tk.Label(files_frame, text="Output DXF", bg=COLORS["panel"], fg=COLORS["text"], font=default_font).grid(
        row=4, column=0, sticky="w", pady=7
    )
    ttk.Entry(files_frame, textvariable=vars_["output"], style="Dark.TEntry", width=78).grid(
        row=4, column=1, sticky="ew", padx=12
    )
    make_button(
        files_frame,
        "Save as",
        lambda: vars_["output"].set(
            filedialog.asksaveasfilename(
                defaultextension=".dxf",
                filetypes=[("DXF", "*.dxf")],
            ) or vars_["output"].get()
        ),
        variant="secondary",
        width=11,
    ).grid(row=4, column=2, sticky="e")

    files_frame.columnconfigure(1, weight=1)

    opts = tk.LabelFrame(
        app,
        text="Processing options",
        bg=COLORS["panel"],
        fg=COLORS["accent"],
        font=section_font,
        padx=14,
        pady=12,
        bd=1,
        relief="solid",
        highlightbackground=COLORS["border"],
    )
    opts.pack(fill="x", pady=(0, 12))

    tk.Label(opts, text="Isolation offset (mm)", bg=COLORS["panel"], fg=COLORS["text"], font=default_font).grid(
        row=0, column=0, sticky="w", pady=(0, 10)
    )
    ttk.Entry(opts, textvariable=vars_["isolation"], style="Dark.TEntry", width=12).grid(
        row=0, column=1, sticky="w", padx=(8, 24)
    )

    tk.Label(opts, text="Fallback trace width (mm)", bg=COLORS["panel"], fg=COLORS["text"], font=default_font).grid(
        row=0, column=2, sticky="w", pady=(0, 10)
    )
    ttk.Entry(opts, textvariable=vars_["default_width"], style="Dark.TEntry", width=12).grid(
        row=0, column=3, sticky="w", padx=(8, 0)
    )

    make_check(opts, "Include copper fill regions", vars_["include_copper_regions"]).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )
    make_check(opts, "Generate isolation contour layers (*_ISO)", vars_["write_iso"]).grid(
        row=1, column=2, columnspan=2, sticky="w", pady=(4, 0)
    )
    make_check(opts, "Use regions only (ignore stroke traces)", vars_["regions_only"]).grid(
        row=2, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )

    actions = tk.Frame(app, bg=COLORS["bg"])
    actions.pack(fill="x", pady=(2, 8))

    left_actions = tk.Frame(actions, bg=COLORS["bg"])
    left_actions.pack(side="left")

    right_actions = tk.Frame(actions, bg=COLORS["bg"])
    right_actions.pack(side="right")

    make_button(left_actions, "Auto-detect folder", autodetect, variant="secondary").pack(side="left")
    tk.Frame(left_actions, bg=COLORS["bg"], width=8).pack(side="left")
    make_button(left_actions, "Clear", clear_paths, variant="ghost", width=10).pack(side="left")

    make_button(right_actions, "Export DXF", export_now, variant="primary", width=14).pack(side="right")

    status_frame = tk.Frame(
        app,
        bg=COLORS["panel2"],
        padx=12,
        pady=8,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
    )
    status_frame.pack(fill="x", pady=(8, 0))

    tk.Label(
        status_frame,
        textvariable=status_var,
        bg=COLORS["panel2"],
        fg=COLORS["muted"],
        font=small_font,
        anchor="w",
    ).pack(side="left", fill="x", expand=True)

    tk.Label(
        status_frame,
        text="Ctrl+D Auto-detect   •   Ctrl+E Export   •   Ctrl+L Clear   •   Esc Exit",
        bg=COLORS["panel2"],
        fg=COLORS["muted"],
        font=small_font,
        anchor="e",
    ).pack(side="right")

    root.mainloop()


if __name__ == "__main__":
    if "--gui" in sys.argv or len(sys.argv) == 1:
        launch_gui()
    else:
        run_cli()
