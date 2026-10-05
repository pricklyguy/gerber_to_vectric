"""Zoomable board preview. Scene units are mm; the view flips Y so the board reads like the Gerber."""

from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView

from ..gerber_io import _polys
from ..job import JobResult

LAYERS = [  # key, label, default-visible
    ("TOP_COPPER", "Top copper", True),
    ("TOP_ISO", "Top isolation", True),
    ("BOTTOM_COPPER", "Bottom copper (mirrored)", False),
    ("BOTTOM_ISO", "Bottom isolation", False),
    ("OUTLINE", "Outline", True),
    ("DRILLS", "Drills", True),
    ("ALIGN", "Alignment holes", True),
    ("WARN", "Tight spots", True),
]
PASS_COLORS = ["#ffd400", "#00e5ff", "#7CFC00", "#ff8c00", "#ff69b4", "#b19cd9"]


def _poly_path(geom) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.OddEvenFill)
    for poly in _polys(geom):
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            path.moveTo(QPointF(*pts[0]))
            for p in pts[1:]:
                path.lineTo(QPointF(*p))
            path.closeSubpath()
    return path


def _cosmetic(color: str, width: float = 1.0) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)
    return pen


class BoardView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(QColor("#1b1d20")))
        self.setRenderHints(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.scale(1, -1)
        self._groups: Dict[str, List[QGraphicsItem]] = {k: [] for k, _, _ in LAYERS}
        self._visible = {k: v for k, _, v in LAYERS}

    # -- content ---------------------------------------------------------------------------------
    def set_result(self, res: JobResult, first: bool) -> None:
        sc = self.scene()
        sc.clear()
        self._groups = {k: [] for k, _, _ in LAYERS}

        def add(group: str, path: QPainterPath, pen: QPen, brush=Qt.NoBrush, z=0):
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setBrush(brush)
            item.setZValue(z)
            sc.addItem(item)
            self._groups[group].append(item)

        for side in ("TOP", "BOTTOM"):
            if side not in res.copper:
                continue
            color = "#c87533" if side == "TOP" else "#4a86c8"
            c = QColor(color)
            c.setAlpha(170)
            add(f"{side}_COPPER", _poly_path(res.copper[side]), _cosmetic(color), QBrush(c), z=1)
            iso = res.isolation[side]
            for n, rings in enumerate(iso.passes):
                path = QPainterPath()
                for ring in rings:
                    pts = list(ring.coords)
                    path.moveTo(QPointF(*pts[0]))
                    for p in pts[1:]:
                        path.lineTo(QPointF(*p))
                add(f"{side}_ISO", path, _cosmetic(PASS_COLORS[n % len(PASS_COLORS)]), z=2)
            for p in iso.tight_spots:
                path = QPainterPath()
                path.addEllipse(QPointF(p.x, p.y), 0.35, 0.35)
                add("WARN", path, _cosmetic("#ff3030", 2), z=6)

        if res.outline is not None:
            add("OUTLINE", _poly_path(res.outline), _cosmetic("#ff4fd8", 1.5), z=3)
        if res.drills:
            path = QPainterPath()
            for holes in res.drills.by_bit.values():
                for h in holes:
                    path.addEllipse(QPointF(h.x, h.y), h.diameter / 2, h.diameter / 2)
            for h in res.drills.milled:
                path.addEllipse(QPointF(h.x, h.y), h.diameter / 2, h.diameter / 2)
            for s in res.drills.slots:
                path.addPath(_poly_path(s.shape()))
            add("DRILLS", path, _cosmetic("#39ff7a", 1.5), z=4)
        if res.align:
            path = QPainterPath()
            for h in res.align:
                path.addEllipse(QPointF(h.x, h.y), h.diameter / 2, h.diameter / 2)
            add("ALIGN", path, _cosmetic("#b388ff", 1.5), z=4)

        if first:  # on the first result show the side that exists
            self._visible["TOP_COPPER"] = self._visible["TOP_ISO"] = "TOP" in res.copper
            self._visible["BOTTOM_COPPER"] = self._visible["BOTTOM_ISO"] = "TOP" not in res.copper
        self._apply_visibility()
        if first:
            self.fit()

    def visible_map(self) -> Dict[str, bool]:
        return dict(self._visible)

    def set_layer_visible(self, key: str, on: bool) -> None:
        self._visible[key] = on
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        for key, items in self._groups.items():
            for it in items:
                it.setVisible(self._visible.get(key, True))

    # -- navigation ------------------------------------------------------------------------------
    def fit(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        m = max(rect.width(), rect.height()) * 0.05 + 1
        self.fitInView(rect.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)
