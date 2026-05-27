#!/usr/bin/env python3
"""
IPC-2581 to KiCad PCB Converter
Converts IPC-2581 (XML) files to KiCad .kicad_pcb format.
Supports IPC-2581A and IPC-2581B.

Usage:
    python ipc2581_to_kicad.py input.xml output.kicad_pcb
    python ipc2581_to_kicad.py input.xml  # outputs input.kicad_pcb
"""

import xml.etree.ElementTree as ET
import re
import sys
import os
import math
from dataclasses import dataclass, field
from typing import Optional

# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class Layer:
    name: str
    layer_type: str  # SIGNAL, PLANE, DIELECTRIC, etc.
    kicad_id: int = 0
    thickness: float = 0.0

@dataclass
class Net:
    name: str
    net_id: int

@dataclass
class Pad:
    net_name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    shape: str = "rect"  # rect, circle, oval
    rotation: float = 0.0
    pad_type: str = "smd"  # smd, thru_hole
    drill: float = 0.0

@dataclass
class Component:
    ref: str
    part: str
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    side: str = "F"  # F = front, B = back
    pads: list = field(default_factory=list)

@dataclass
class Track:
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    width: float = 0.25
    layer: str = "F.Cu"
    net_name: str = ""

@dataclass
class Via:
    x: float = 0.0
    y: float = 0.0
    size: float = 0.8
    drill: float = 0.4
    net_name: str = ""

@dataclass
class Zone:
    layer: str = "F.Cu"
    net_name: str = ""
    points: list = field(default_factory=list)

@dataclass
class BoardOutline:
    points: list = field(default_factory=list)
    width: float = 200.0
    height: float = 200.0

# ─── Layer Mapping ────────────────────────────────────────────────────────────

# Maps IPC-2581 layer function to KiCad layer id and name
LAYER_MAP = {
    "SIGNAL":      {"F": (0, "F.Cu"),   "B": (31, "B.Cu")},
    "PLANE":       {"F": (0, "F.Cu"),   "B": (31, "B.Cu")},
    "SILKSCREEN":  {"F": (37, "F.SilkS"), "B": (36, "B.SilkS")},
    "SOLDERMASK":  {"F": (39, "F.Mask"), "B": (38, "B.Mask")},
    "SOLDERPASTE": {"F": (35, "F.Paste"), "B": (34, "B.Paste")},
    "ASSEMBLY":    {"F": (33, "F.Fab"),  "B": (32, "B.Fab")},
    "COURTYARD":   {"F": (45, "F.Courtyard"), "B": (44, "B.Courtyard")},
    "BOARD":       {"F": (28, "Edge.Cuts"), "B": (28, "Edge.Cuts")},
}

INNER_LAYER_START = 1  # KiCad inner layers start at In1.Cu (id=1)

STANDARD_KICAD_LAYERS = """    (0 "F.Cu" signal)
    (1 "In1.Cu" signal hide)
    (2 "In2.Cu" signal hide)
    (3 "In3.Cu" signal hide)
    (4 "In4.Cu" signal hide)
    (5 "In5.Cu" signal hide)
    (6 "In6.Cu" signal hide)
    (7 "In7.Cu" signal hide)
    (8 "In8.Cu" signal hide)
    (9 "In9.Cu" signal hide)
    (10 "In10.Cu" signal hide)
    (11 "In11.Cu" signal hide)
    (12 "In12.Cu" signal hide)
    (13 "In13.Cu" signal hide)
    (14 "In14.Cu" signal hide)
    (15 "In15.Cu" signal hide)
    (16 "In16.Cu" signal hide)
    (17 "In17.Cu" signal hide)
    (18 "In18.Cu" signal hide)
    (19 "In19.Cu" signal hide)
    (20 "In20.Cu" signal hide)
    (21 "In21.Cu" signal hide)
    (22 "In22.Cu" signal hide)
    (23 "In23.Cu" signal hide)
    (24 "In24.Cu" signal hide)
    (25 "In25.Cu" signal hide)
    (26 "In26.Cu" signal hide)
    (27 "In27.Cu" signal hide)
    (28 "In28.Cu" signal hide)
    (29 "In29.Cu" signal hide)
    (30 "In30.Cu" signal hide)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user hide)
    (33 "F.Adhes" user hide)
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user hide)
    (37 "F.SilkS" user)
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user hide)
    (41 "Cmts.User" user hide)
    (42 "Eco1.User" user hide)
    (43 "Eco2.User" user hide)
    (44 "Edge.Cuts" user)
    (45 "Margin" user hide)
    (46 "B.CrtYd" user hide)
    (47 "F.CrtYd" user hide)
    (48 "B.Fab" user hide)
    (49 "F.Fab" user hide)"""

# ─── Parser ───────────────────────────────────────────────────────────────────

class IPC2581Parser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.tree = ET.parse(filepath)
        self.root = self.tree.getroot()

        # Strip XML namespace for easier parsing
        self.ns = self._get_namespace(self.root.tag)
        self._strip_ns()

        self.layers: list[Layer] = []
        self.nets: list[Net] = []
        self.components: list[Component] = []
        self.tracks: list[Track] = []
        self.vias: list[Via] = []
        self.zones: list[Zone] = []
        self.outline = BoardOutline()

        # Lookup maps
        self.net_map: dict[str, int] = {}       # name -> id
        self.layer_name_map: dict[str, str] = {}  # ipc name -> kicad name
        self.padstack_map: dict[str, dict] = {}   # padstack id -> pad info
        self.package_map: dict[str, list] = {}    # package ref -> pads

        self.warnings: list[str] = []

    def _get_namespace(self, tag: str) -> str:
        if tag.startswith("{"):
            return tag.split("}")[0] + "}"
        return ""

    def _strip_ns(self):
        """Remove XML namespace prefixes from all tags for simpler parsing."""
        for elem in self.root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

    def _float(self, val, default=0.0) -> float:
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def parse(self):
        self._parse_layers()
        self._parse_nets()
        self._parse_padstacks()
        self._parse_packages()
        self._parse_components()
        self._parse_board_outline()
        self._parse_layout()
        print(f"[OK] Parsed: {len(self.layers)} layers, {len(self.nets)} nets, "
              f"{len(self.components)} components, {len(self.tracks)} tracks, "
              f"{len(self.vias)} vias")

    def _parse_layers(self):
        """Parse layer stack — handles IPC-2581 A/B (Layer elements) and C (LayerRef in Content)."""
        inner_count = 0
        seen = set()

        # IPC-2581C: layers declared as <LayerRef name="..."> inside <Content>
        content_el = self.root.find("Content")
        if content_el is not None:
            for lr in content_el.findall("LayerRef"):
                name = lr.get("name", "")
                if not name or name in seen:
                    continue
                seen.add(name)
                ltype, side = self._infer_type_side_from_name(name, inner_count)
                kicad_name = self._map_layer_name(name, ltype, side, inner_count)
                if kicad_name.startswith("In") and kicad_name.endswith(".Cu"):
                    inner_count += 1
                layer = Layer(name=name, layer_type=ltype)
                layer.kicad_id = self._kicad_layer_id(kicad_name)
                self.layers.append(layer)
                self.layer_name_map[name] = kicad_name

        # IPC-2581A/B: explicit <Layer> elements
        for layer_el in self.root.iter("Layer"):
            name = layer_el.get("name", "")
            ltype = layer_el.get("layerFunction", layer_el.get("type", "SIGNAL")).upper()
            side = layer_el.get("side", "F").upper()
            if not name or name in seen:
                continue
            seen.add(name)
            kicad_name = self._map_layer_name(name, ltype, side, inner_count)
            if kicad_name.startswith("In") and kicad_name.endswith(".Cu"):
                inner_count += 1
            layer = Layer(name=name, layer_type=ltype)
            layer.kicad_id = self._kicad_layer_id(kicad_name)
            self.layers.append(layer)
            self.layer_name_map[name] = kicad_name

        if not self.layers:
            self.layer_name_map["TOP"] = "F.Cu"
            self.layer_name_map["BOTTOM"] = "B.Cu"
            self.warnings.append("No layer definitions found — assumed 2-layer board")

    def _infer_type_side_from_name(self, name: str, inner_count: int) -> tuple:
        """Infer layer type and side from KiCad-style layer names used in IPC-2581C exports."""
        n = name.upper()
        if "SILKSCREEN" in n or "SILK" in n: return ("SILKSCREEN", "F" if "F." in name else "B")
        if "MASK" in n:   return ("SOLDERMASK",  "F" if "F." in name else "B")
        if "PASTE" in n:  return ("SOLDERPASTE", "F" if "F." in name else "B")
        if "FAB" in n:    return ("ASSEMBLY",    "F" if "F." in name else "B")
        if "COURT" in n:  return ("COURTYARD",   "F" if "F." in name else "B")
        if "EDGE" in n or "CUTS" in n: return ("BOARD", "F")
        if "DIEL" in n:   return ("DIELECTRIC",  "F")
        if "B.CU" in n:   return ("SIGNAL", "B")
        if "F.CU" in n:   return ("SIGNAL", "F")
        if re.search(r"IN\d+\.CU", n): return ("SIGNAL", "I")
        return ("SIGNAL", "F" if inner_count == 0 else "I")

    def _map_layer_name(self, ipc_name: str, ltype: str, side: str, inner_idx: int) -> str:
        ipc_upper = ipc_name.upper()

        # KiCad native layer names (used in IPC-2581C exports from KiCad)
        kicad_native = {
            "F.CU": "F.Cu", "B.CU": "B.Cu",
            "F.SILKSCREEN": "F.SilkS", "B.SILKSCREEN": "B.SilkS",
            "F.MASK": "F.Mask", "B.MASK": "B.Mask",
            "F.PASTE": "F.Paste", "B.PASTE": "B.Paste",
            "F.FAB": "F.Fab", "B.FAB": "B.Fab",
            "F.COURTYARD": "F.CrtYd", "B.COURTYARD": "B.CrtYd",
            "EDGE.CUTS": "Edge.Cuts", "MARGIN": "Margin",
            "DWGS.USER": "Dwgs.User", "CMTS.USER": "Cmts.User",
            "ECO1.USER": "Eco1.User", "ECO2.USER": "Eco2.User",
        }
        if ipc_upper in kicad_native:
            return kicad_native[ipc_upper]

        # Inner copper: In1.Cu, In2.Cu etc.
        m = re.match(r"IN(\d+)\.CU", ipc_upper)
        if m:
            return f"In{m.group(1)}.Cu"

        # Dielectric layers — map to user layer or skip
        if "DIEL" in ipc_upper:
            return "Cmts.User"

        # Generic fallbacks
        if "SILK" in ipc_upper or "LEGEND" in ipc_upper:
            return "F.SilkS" if side != "B" else "B.SilkS"
        if "MASK" in ipc_upper or "SOLDERMASK" in ltype:
            return "F.Mask" if side != "B" else "B.Mask"
        if "PASTE" in ipc_upper or "SOLDERPASTE" in ltype:
            return "F.Paste" if side != "B" else "B.Paste"
        if "OUTLINE" in ipc_upper or "BOARD" in ipc_upper or "EDGE" in ipc_upper:
            return "Edge.Cuts"
        if "ASSY" in ipc_upper or "ASSEMBLY" in ipc_upper or "FAB" in ipc_upper:
            return "F.Fab" if side != "B" else "B.Fab"
        if "COURT" in ipc_upper:
            return "F.CrtYd" if side != "B" else "B.CrtYd"
        if "TOP" in ipc_upper or (side == "F" and inner_idx == 0 and ltype in ("SIGNAL", "PLANE")):
            return "F.Cu"
        if "BOT" in ipc_upper or "BOTTOM" in ipc_upper:
            return "B.Cu"
        if ltype in ("SIGNAL", "PLANE"):
            return f"In{inner_idx + 1}.Cu"
        return "Cmts.User"

    def _kicad_layer_id(self, kicad_name: str) -> int:
        mapping = {
            "F.Cu": 0, "B.Cu": 31,
            "B.Adhes": 32, "F.Adhes": 33,
            "B.Paste": 34, "F.Paste": 35,
            "B.SilkS": 36, "F.SilkS": 37,
            "B.Mask": 38, "F.Mask": 39,
            "Edge.Cuts": 28, "Margin": 29,
            "F.CrtYd": 45, "B.CrtYd": 44,
            "F.Fab": 49, "B.Fab": 48,
            "Cmts.User": 25,
        }
        if kicad_name in mapping:
            return mapping[kicad_name]
        if kicad_name.startswith("In") and kicad_name.endswith(".Cu"):
            try:
                return int(kicad_name[2:-3])
            except ValueError:
                pass
        return 25

    def _kicad_layer_for_ipc(self, ipc_name: str) -> str:
        return self.layer_name_map.get(ipc_name,
               self.layer_name_map.get(ipc_name.upper(), "F.Cu"))

    def _parse_nets(self):
        net_id = 1
        seen = set()
        for net_el in self.root.iter("Net"):
            name = net_el.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            self.nets.append(Net(name=name, net_id=net_id))
            self.net_map[name] = net_id
            net_id += 1

        # Also pick up nets referenced in LogicalNet
        for net_el in self.root.iter("LogicalNet"):
            name = net_el.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            self.nets.append(Net(name=name, net_id=net_id))
            self.net_map[name] = net_id
            net_id += 1

    def _parse_padstacks(self):
        """Parse padstack definitions for pad shape/size lookup."""
        for ps in self.root.iter("Padstack"):
            ps_id = ps.get("id", ps.get("name", ""))
            if not ps_id:
                continue
            info = {"shape": "rect", "width": 1.0, "height": 1.0, "drill": 0.0, "type": "smd"}

            # Drill
            drill_el = ps.find("Drill")
            if drill_el is not None:
                info["drill"] = self._float(drill_el.get("diameter", drill_el.get("size", 0)))
                if info["drill"] > 0:
                    info["type"] = "thru_hole"

            # Pad shape on any layer
            for pad_el in ps.iter("Pad"):
                shape_el_found = pad_el.find("PadShape")
                shape_el = shape_el_found if shape_el_found is not None else pad_el
                shape = (shape_el.get("shape") or shape_el.get("type") or "RECT").upper()
                w = self._float(shape_el.get("width") or shape_el.get("xSize"))
                h = self._float(shape_el.get("height") or shape_el.get("ySize") or shape_el.get("xSize"))
                d = self._float(shape_el.get("diameter"))
                if d:
                    w = h = d
                info["width"] = w or 1.0
                info["height"] = h or w or 1.0
                info["shape"] = "circle" if "ROUND" in shape or "CIRCLE" in shape else \
                                "oval" if "OVAL" in shape else "rect"
                break

            self.padstack_map[ps_id] = info

    def _parse_packages(self):
        """Parse package/footprint definitions."""
        for pkg in self.root.iter("Package"):
            pkg_name = pkg.get("name", pkg.get("id", ""))
            pads = []
            for pin_el in pkg.iter("Pin"):
                pad = {
                    "number": pin_el.get("number", pin_el.get("name", "1")),
                    "x": self._float(pin_el.get("x")),
                    "y": self._float(pin_el.get("y")),
                    "rotation": self._float(pin_el.get("rotation")),
                    "padstack": pin_el.get("padstackRef", pin_el.get("padstack", "")),
                }
                pads.append(pad)
            if pkg_name:
                self.package_map[pkg_name] = pads

    def _parse_components(self):
        """Parse component placements."""
        for cmp in self.root.iter("Component"):
            ref = cmp.get("refDes", cmp.get("refdes", cmp.get("name", "")))
            part = cmp.get("part", cmp.get("packageRef", cmp.get("package", "")))
            x = self._float(cmp.get("x"))
            y = self._float(cmp.get("y"))
            rot = self._float(cmp.get("rotation"))
            side_raw = cmp.get("mountType", cmp.get("side", "TOP")).upper()
            side = "B" if "BOT" in side_raw or side_raw == "B" else "F"

            comp = Component(ref=ref, part=part, x=x, y=y, rotation=rot, side=side)

            # Build pads from package definition + net assignments
            net_assignments = {}
            for pin_ref in cmp.iter("PinRef"):
                pin_num = pin_ref.get("pin", "")
                net_name = ""
                # Net may be on parent <Net> element
                parent_net = pin_ref.get("net", "")
                if parent_net:
                    net_name = parent_net
                net_assignments[pin_num] = net_name

            # Also pick up from NetsFromComp or similar
            for netpin in cmp.iter("Net"):
                net_name = netpin.get("name", "")
                for pr in netpin.iter("PinRef"):
                    if pr.get("component", pr.get("refDes", "")) in (ref, ""):
                        net_assignments[pr.get("pin", "")] = net_name

            pkg_pads = self.package_map.get(part, [])
            for pin_def in pkg_pads:
                ps_id = pin_def["padstack"]
                ps_info = self.padstack_map.get(ps_id, {})
                pad = Pad(
                    net_name=net_assignments.get(pin_def["number"], ""),
                    x=pin_def["x"],
                    y=pin_def["y"],
                    width=ps_info.get("width", 1.0),
                    height=ps_info.get("height", 1.0),
                    shape=ps_info.get("shape", "rect"),
                    rotation=pin_def["rotation"],
                    pad_type=ps_info.get("type", "smd"),
                    drill=ps_info.get("drill", 0.0),
                )
                comp.pads.append(pad)

            self.components.append(comp)

    def _parse_board_outline(self):
        """Parse board outline from Profile or Outline elements."""
        for profile in self.root.iter("Profile"):
            for poly in profile.iter("Polygon"):
                pts = []
                for pt in poly.iter("Point"):
                    pts.append((self._float(pt.get("x")), self._float(pt.get("y"))))
                if pts:
                    self.outline.points = pts
                    return
            for line in profile.iter("Line"):
                # Just grab extents
                x1, y1 = self._float(line.get("x1")), self._float(line.get("y1"))
                x2, y2 = self._float(line.get("x2")), self._float(line.get("y2"))
                self.outline.points.extend([(x1, y1), (x2, y2)])

        # Fallback: parse from BoundingBox
        for bb in self.root.iter("BoundingBox"):
            x = self._float(bb.get("x"))
            y = self._float(bb.get("y"))
            w = self._float(bb.get("width", bb.get("xSize", 200)))
            h = self._float(bb.get("height", bb.get("ySize", 200)))
            self.outline.points = [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
            return

        if not self.outline.points:
            self.outline.points = [(0, 0), (200, 0), (200, 150), (0, 150)]
            self.warnings.append("No board outline found — using default 200x150mm")

    def _parse_layout(self):
        """Parse copper traces, vias from LayerFeature/Conductor elements."""
        for lf in self.root.iter("LayerFeature"):
            layer_ref = lf.get("layer", "")
            kicad_layer = self._kicad_layer_for_ipc(layer_ref)

            for line_el in lf.iter("Line"):
                net = line_el.get("net", "")
                w = self._float(line_el.get("lineWidth", line_el.get("width", 0.25)))
                x1 = self._float(line_el.get("x1"))
                y1 = self._float(line_el.get("y1"))
                x2 = self._float(line_el.get("x2"))
                y2 = self._float(line_el.get("y2"))
                self.tracks.append(Track(x1, y1, x2, y2, w, kicad_layer, net))

            for seg in lf.iter("Conductor"):
                net = seg.get("net", "")
                w = self._float(seg.get("lineWidth", seg.get("width", 0.25)))
                for line_el in seg.iter("Line"):
                    x1 = self._float(line_el.get("x1"))
                    y1 = self._float(line_el.get("y1"))
                    x2 = self._float(line_el.get("x2"))
                    y2 = self._float(line_el.get("y2"))
                    self.tracks.append(Track(x1, y1, x2, y2, w, kicad_layer, net))

        for via_el in self.root.iter("Via"):
            x = self._float(via_el.get("x"))
            y = self._float(via_el.get("y"))
            size = self._float(via_el.get("diameter", via_el.get("size", 0.8)))
            drill = self._float(via_el.get("drill", via_el.get("holeDiameter", size * 0.5)))
            net = via_el.get("net", "")
            self.vias.append(Via(x, y, size, drill, net))


# ─── Writer ───────────────────────────────────────────────────────────────────

class KiCadWriter:
    def __init__(self, parser: IPC2581Parser):
        self.p = parser

    def write(self, out_path: str):
        lines = []
        lines.append('(kicad_pcb (version 20221018) (generator ipc2581_converter)')
        lines.append('')
        lines.append('  (general')
        lines.append('    (thickness 1.6)')
        lines.append('  )')
        lines.append('')

        # Layers
        lines.append('  (layers')
        lines.append(STANDARD_KICAD_LAYERS)
        lines.append('  )')
        lines.append('')

        # Nets
        lines.append('  (net 0 "")')
        for net in self.p.nets:
            lines.append(f'  (net {net.net_id} "{net.name}")')
        lines.append('')

        # Board outline
        lines += self._write_outline()
        lines.append('')

        # Components
        for comp in self.p.components:
            lines += self._write_footprint(comp)

        # Tracks
        for track in self.p.tracks:
            net_id = self.p.net_map.get(track.net_name, 0)
            lines.append(
                f'  (segment (start {track.x1:.4f} {track.y1:.4f}) '
                f'(end {track.x2:.4f} {track.y2:.4f}) '
                f'(width {track.width:.4f}) (layer "{track.layer}") (net {net_id}))'
            )

        # Vias
        for via in self.p.vias:
            net_id = self.p.net_map.get(via.net_name, 0)
            lines.append(
                f'  (via (at {via.x:.4f} {via.y:.4f}) '
                f'(size {via.size:.4f}) (drill {via.drill:.4f}) '
                f'(layers "F.Cu" "B.Cu") (net {net_id}))'
            )

        lines.append(')')
        lines.append('')

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[OK] Written to: {out_path}")

    def _write_outline(self) -> list[str]:
        lines = []
        pts = self.p.outline.points
        if len(pts) < 2:
            return lines
        # Close the polygon
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            lines.append(
                f'  (gr_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f}) '
                f'(layer "Edge.Cuts") (width 0.05))'
            )
        return lines

    def _write_footprint(self, comp: Component) -> list[str]:
        lines = []
        layer = "F.Cu" if comp.side == "F" else "B.Cu"
        fab_layer = "F.Fab" if comp.side == "F" else "B.Fab"
        silk_layer = "F.SilkS" if comp.side == "F" else "B.SilkS"

        lines.append(
            f'  (footprint "{comp.part}" (layer "{layer}")'
        )
        lines.append(
            f'    (at {comp.x:.4f} {comp.y:.4f} {comp.rotation:.2f})'
        )
        lines.append(f'    (attr smd)')

        # Reference and value text
        lines.append(
            f'    (fp_text reference "{comp.ref}" (at 0 -1) (layer "{silk_layer}")'
            f' (effects (font (size 1 1) (thickness 0.15))))'
        )
        lines.append(
            f'    (fp_text value "{comp.part}" (at 0 1) (layer "{fab_layer}") hide'
            f' (effects (font (size 1 1) (thickness 0.15))))'
        )

        # Pads
        for i, pad in enumerate(comp.pads, start=1):
            pad_num = i
            net_id = self.p.net_map.get(pad.net_name, 0)
            net_str = f' (net {net_id} "{pad.net_name}")' if net_id else ''
            shape_str = {"circle": "circle", "oval": "oval"}.get(pad.shape, "rect")

            if pad.pad_type == "thru_hole":
                lines.append(
                    f'    (pad "{pad_num}" thru_hole {shape_str} '
                    f'(at {pad.x:.4f} {pad.y:.4f} {pad.rotation:.2f}) '
                    f'(size {pad.width:.4f} {pad.height:.4f}) '
                    f'(drill {pad.drill:.4f}) '
                    f'(layers "*.Cu" "*.Mask"){net_str})'
                )
            else:
                lines.append(
                    f'    (pad "{pad_num}" smd {shape_str} '
                    f'(at {pad.x:.4f} {pad.y:.4f} {pad.rotation:.2f}) '
                    f'(size {pad.width:.4f} {pad.height:.4f}) '
                    f'(layers "{layer}" "{fab_layer}"){net_str})'
                )

        lines.append('  )')
        return lines


# ─── Main ─────────────────────────────────────────────────────────────────────

def convert(input_path: str, output_path: str):
    print(f"[..] Parsing: {input_path}")
    parser = IPC2581Parser(input_path)
    parser.parse()

    if parser.warnings:
        print("\n[WARNINGS]")
        for w in parser.warnings:
            print(f"  ! {w}")
        print()

    writer = KiCadWriter(parser)
    writer.write(output_path)

    print("\n[SUMMARY]")
    print(f"  Layers:     {len(parser.layers)}")
    print(f"  Nets:       {len(parser.nets)}")
    print(f"  Components: {len(parser.components)}")
    print(f"  Tracks:     {len(parser.tracks)}")
    print(f"  Vias:       {len(parser.vias)}")
    print(f"  Warnings:   {len(parser.warnings)}")

    # Known limitations
    print("\n[KNOWN LIMITATIONS]")
    print("  - Copper pours/zones not fully supported")
    print("  - Arc/curve segments converted to straight lines")
    print("  - Net assignments on pads require package+netlist data in source file")
    print("  - Verify layer mapping matches your stackup after import")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        sys.exit(1)

    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        base = os.path.splitext(os.path.basename(input_file))[0]
        out_dir = os.path.join(os.path.dirname(os.path.abspath(input_file)), "..", "output_PCB")
        os.makedirs(out_dir, exist_ok=True)
        output_file = os.path.join(out_dir, base + ".kicad_pcb")

    convert(input_file, output_file)
