#!/usr/bin/env python3
"""
ODB++ to KiCad PCB Converter
Converts ODB++ archives (.tgz, .tar.gz, .zip) or extracted directories
to KiCad .kicad_pcb format.

Usage:
    python odb_to_kicad.py input.tgz output.kicad_pcb
    python odb_to_kicad.py input.tgz          # auto-names output
    python odb_to_kicad.py /path/to/odb/dir   # extracted directory
"""

import os, sys, re, tarfile, zipfile, tempfile, shutil, math
from dataclasses import dataclass, field

# ─── KiCad layer table ────────────────────────────────────────────────────────

KICAD_LAYERS = """    (0 "F.Cu" signal)
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
    (49 "F.Fab" user hide)
    (50 "User.1" user hide)
    (51 "User.2" user hide)
    (52 "User.3" user hide)
    (53 "User.4" user hide)
    (54 "User.5" user hide)
    (55 "User.6" user hide)
    (56 "User.7" user hide)
    (57 "User.8" user hide)
    (58 "User.9" user hide)"""

# ODB layer name → KiCad layer name
ODB_TO_KICAD_LAYER = {
    "f.cu": "F.Cu", "b.cu": "B.Cu",
    "in1.cu": "In1.Cu", "in2.cu": "In2.Cu",
    "in3.cu": "In3.Cu", "in4.cu": "In4.Cu",
    "in5.cu": "In5.Cu", "in6.cu": "In6.Cu",
    "in7.cu": "In7.Cu", "in8.cu": "In8.Cu",
    "f.silkscreen": "F.SilkS", "b.silkscreen": "B.SilkS",
    "f.mask": "F.Mask", "b.mask": "B.Mask",
    "f.paste": "F.Paste", "b.paste": "B.Paste",
    "f.courtyard": "F.CrtYd", "b.courtyard": "B.CrtYd",
    "f.fab": "F.Fab", "b.fab": "B.Fab",
    "f.adhesive": "F.Adhes", "b.adhesive": "B.Adhes",
    "edge.cuts": "Edge.Cuts", "margin": "Margin",
    "user.drawings": "Dwgs.User", "user.comments": "Cmts.User",
    "user.eco1": "Eco1.User", "user.eco2": "Eco2.User",
    # KiCad user layers (user.1 - user.9 map to User.1 - User.9)
    "user.1": "User.1", "user.2": "User.2", "user.3": "User.3",
    "user.4": "User.4", "user.5": "User.5", "user.6": "User.6",
    "user.7": "User.7", "user.8": "User.8", "user.9": "User.9",
}

KICAD_LAYER_IDS = {
    "F.Cu": 0, "B.Cu": 31,
    "In1.Cu": 1, "In2.Cu": 2, "In3.Cu": 3, "In4.Cu": 4,
    "In5.Cu": 5, "In6.Cu": 6, "In7.Cu": 7, "In8.Cu": 8,
    "F.SilkS": 37, "B.SilkS": 36,
    "F.Mask": 39, "B.Mask": 38,
    "F.Paste": 35, "B.Paste": 34,
    "F.CrtYd": 47, "B.CrtYd": 46,
    "F.Fab": 49, "B.Fab": 48,
    "F.Adhes": 33, "B.Adhes": 32,
    "Edge.Cuts": 44, "Margin": 45,
    "Dwgs.User": 40, "Cmts.User": 41,
    "Eco1.User": 42, "Eco2.User": 43,
    "User.1": 50, "User.2": 51, "User.3": 52,
    "User.4": 53, "User.5": 54, "User.6": 55,
    "User.7": 56, "User.8": 57, "User.9": 58,
}

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Track:
    x1: float; y1: float; x2: float; y2: float
    width: float; layer: str; net: str = ""

@dataclass
class Via:
    x: float; y: float
    size: float; drill: float; net: str = ""

@dataclass
class Pad:
    number: str; x: float; y: float
    width: float; height: float
    shape: str  # rect, circle, oval, roundrect
    rotation: float = 0.0
    pad_type: str = "smd"
    drill: float = 0.0
    net: str = ""
    roundrect_ratio: float = 0.0

@dataclass
class Footprint:
    ref: str; value: str
    x: float; y: float; rotation: float
    layer: str  # F.Cu or B.Cu
    pads: list = field(default_factory=list)

@dataclass
class GraphicLine:
    x1: float; y1: float; x2: float; y2: float
    width: float; layer: str

@dataclass
class GraphicArc:
    cx: float; cy: float
    sx: float; sy: float
    angle: float
    width: float; layer: str

# ─── ODB Units ────────────────────────────────────────────────────────────────

def odb_to_mm(val: float, units: str) -> float:
    """ODB++ coords in features files are in units*10000 (micro-units)."""
    # Features files store coords as floats already in the declared unit
    # but symbol sizes come as integers in micro-units (1/10000 mm or 1/10000 inch)
    if units.upper() in ("MM", "MILLIMETER"):
        return val
    elif units.upper() in ("INCH", "IN"):
        return val * 25.4
    return val

def sym_size_to_mm(val: float, units: str) -> float:
    """Symbol dimensions in features files are in micro-units (divide by 10000)."""
    raw = val / 10000.0
    if units.upper() in ("INCH", "IN"):
        raw *= 25.4
    return raw

# ─── Feature file parser ──────────────────────────────────────────────────────

def parse_features(path: str, units: str, net_names: dict) -> tuple:
    """
    Parse ODB++ features file.
    Returns (tracks, vias, pads, graphics)
    net_names: {index: name}
    """
    tracks, vias, pads_out, graphics = [], [], [], []
    if not os.path.exists(path):
        return tracks, vias, pads_out, graphics

    symbols = {}   # index -> (type, w, h, roundrect_ratio)
    current_net = ""

    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Parse symbol table first
    in_sym = False
    sym_idx = 0
    for line in lines:
        line = line.rstrip()
        if line.startswith("$"):
            parts = line[1:].split(" ", 1)
            if len(parts) == 2:
                idx = int(parts[0])
                sym_def = parts[1].strip()
                symbols[idx] = _parse_sym_def(sym_def, units)

    kicad_layer = ODB_TO_KICAD_LAYER.get(
        os.path.basename(os.path.dirname(path)).lower(), "F.Cu"
    )
    is_copper = kicad_layer.endswith(".Cu")

    in_polygon = False
    post_polygon_lines = False  # L lines immediately after SE are polygon outlines
    for line in lines:
        line = line.rstrip()
        if not line or line.startswith("#") or line.startswith("@") or \
           line.startswith("&") or line.startswith("$") or line.startswith("F ") or \
           line.startswith("UNITS"):
            continue

        # Surface polygon markers — skip polygon fill boundary lines
        if line.startswith("S P") or line.startswith("OB"):
            in_polygon = True
            post_polygon_lines = False
            continue
        if line.startswith("SE") or line.startswith("OE"):
            in_polygon = False
            post_polygon_lines = True  # L lines after SE are polygon outlines
            continue
        if line.startswith("OS") or in_polygon:
            continue
        # L lines immediately after a polygon SE block are polygon outline duplicates
        if post_polygon_lines and line.startswith("L "):
            continue
        # Any non-L line resets the post-polygon flag
        if post_polygon_lines and not line.startswith("L "):
            post_polygon_lines = False

        parts = line.split()
        if not parts:
            continue

        ftype = parts[0]

        try:
            if ftype == "L" and is_copper:
                # Line: L x1 y1 x2 y2 width_sym_idx polarity
                if len(parts) >= 6:
                    x1 = float(parts[1]);  y1 = -float(parts[2])
                    x2 = float(parts[3]);  y2 = -float(parts[4])
                    sym_idx = int(parts[5])
                    w_info = symbols.get(sym_idx, (None, 0.1, 0.1, 0))
                    width = w_info[1] if w_info else 0.1
                    net = _extract_net(line, net_names)
                    tracks.append(Track(x1, y1, x2, y2, width, kicad_layer, net))

            elif ftype == "A" and is_copper:
                # Arc: A x y sym_idx polarity start_angle end_angle cw
                # ODB arc: A cx cy sym_idx P se_angle ee_angle dir
                if len(parts) >= 8:
                    cx = float(parts[1]); cy = -float(parts[2])
                    sym_idx = int(parts[3])
                    w_info = symbols.get(sym_idx, (None, 0.1, 0.1, 0))
                    width = w_info[1] if w_info else 0.1
                    sa = math.radians(float(parts[5]))
                    ea = math.radians(float(parts[6]))
                    cw = parts[7] == "Y" if len(parts) > 7 else False
                    r = width  # arc radius not directly available from sym; skip for now
                    # Convert to two endpoints approximation
                    r_est = 1.0
                    x1 = cx + r_est * math.cos(sa); y1 = cy + r_est * math.sin(sa)
                    x2 = cx + r_est * math.cos(ea); y2 = cy + r_est * math.sin(ea)
                    net = _extract_net(line, net_names)
                    tracks.append(Track(x1, y1, x2, y2, max(width, 0.05), kicad_layer, net))

            elif ftype == "P":
                # Pad: P x y sym_idx polarity orient [attribs]
                if len(parts) >= 6:
                    x = float(parts[1]); y = -float(parts[2])
                    sym_idx = int(parts[3])
                    orient = float(parts[5]) if len(parts) > 5 else 0.0
                    sym_info = symbols.get(sym_idx, ("circle", 1.0, 1.0, 0))
                    shape, w, h, rr = sym_info
                    net = _extract_net(line, net_names)

                    # Determine if via (on copper, round, no net or via attribute)
                    is_via = is_copper and shape == "circle" and ".via" in line.lower()
                    if is_via:
                        vias.append(Via(x, y, w, w * 0.5, net))
                    else:
                        pad = Pad(
                            number="1", x=x, y=y,
                            width=w, height=h, shape=shape,
                            rotation=orient, pad_type="smd",
                            drill=0.0, net=net,
                            roundrect_ratio=rr
                        )
                        pads_out.append((kicad_layer, pad))

            elif ftype in ("L",) and not is_copper:
                # Graphic line on non-copper layer
                if len(parts) >= 6:
                    x1 = float(parts[1]); y1 = -float(parts[2])
                    x2 = float(parts[3]); y2 = -float(parts[4])
                    sym_idx = int(parts[5])
                    w_info = symbols.get(sym_idx, (None, 0.05, 0.05, 0))
                    width = w_info[1] if w_info else 0.05
                    graphics.append(GraphicLine(x1, y1, x2, y2, width, kicad_layer))

        except (ValueError, IndexError):
            continue

    return tracks, vias, pads_out, graphics


def _parse_sym_def(sym_def: str, units: str) -> tuple:
    """
    Parse ODB symbol definition string.
    Returns (shape, width_mm, height_mm, roundrect_ratio)
    Examples: r4500.0  rect1800.0x2200.0  oval1500.0x3300.0  rect1200.0x1800.0xr250.0
    """
    sym_def = sym_def.strip()
    try:
        if sym_def.startswith("r") and not sym_def.startswith("rect"):
            d = sym_size_to_mm(float(sym_def[1:]), units)
            return ("circle", d, d, 0)
        elif sym_def.startswith("oval"):
            rest = sym_def[4:]
            parts = rest.split("x")
            w = sym_size_to_mm(float(parts[0]), units)
            h = sym_size_to_mm(float(parts[1]), units) if len(parts) > 1 else w
            return ("oval", w, h, 0)
        elif sym_def.startswith("rect"):
            rest = sym_def[4:]
            parts = rest.split("x")
            w = sym_size_to_mm(float(parts[0]), units)
            h = sym_size_to_mm(float(parts[1]), units) if len(parts) > 1 else w
            rr = 0.0
            if len(parts) > 2 and parts[2].startswith("r"):
                corner = sym_size_to_mm(float(parts[2][1:]), units)
                rr = min(corner / (min(w, h) / 2), 0.5) if min(w, h) > 0 else 0
            shape = "roundrect" if rr > 0 else "rect"
            return (shape, w, h, rr)
        elif sym_def.startswith("s"):
            # Square: s<size>
            d = sym_size_to_mm(float(sym_def[1:]), units)
            return ("rect", d, d, 0)
        else:
            # Unknown — try to parse as number (line width)
            d = sym_size_to_mm(float(sym_def), units)
            return ("circle", d, d, 0)
    except (ValueError, IndexError):
        return ("circle", 0.1, 0.1, 0)


def _extract_net(line: str, net_names: dict) -> str:
    """Extract net name from ODB feature line attribute section."""
    # Net index appears after semicolon: ;0=0 or with N= prefix
    m = re.search(r';\s*(\d+)=', line)
    if m:
        return net_names.get(int(m.group(1)), "")
    return ""

# ─── ODB parser ───────────────────────────────────────────────────────────────

class ODBParser:
    def __init__(self, odb_root: str):
        # Find actual odb root (may be nested)
        self.root = self._find_odb_root(odb_root)
        self.units = "MM"
        self.layers = []         # list of (odb_name, kicad_name, type)
        self.net_names = {}      # int -> str
        self.tracks = []
        self.vias = []
        self.footprints = []
        self.graphics = []
        self.outline_pts = []
        self.warnings = []

    def _find_odb_root(self, path: str) -> str:
        """Navigate to the directory containing matrix/ and steps/."""
        for dirpath, dirnames, _ in os.walk(path):
            if "matrix" in dirnames and "steps" in dirnames:
                return dirpath
        return path

    def parse(self):
        self._parse_matrix()
        self._parse_netlist()
        self._parse_profile()
        self._parse_eda()
        self._parse_layers()
        print(f"[OK] Parsed: {len(self.layers)} layers, {len(self.net_names)} nets, "
              f"{len(self.footprints)} components, {len(self.tracks)} tracks, "
              f"{len(self.vias)} vias")

    def _read_file(self, *parts) -> list:
        path = os.path.join(self.root, *parts)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()

    def _parse_matrix(self):
        lines = self._read_file("matrix", "matrix")
        current = {}
        for line in lines:
            line = line.strip()
            if line == "LAYER {":
                current = {}
            elif line == "}":
                if current:
                    name = current.get("NAME", "").lower()
                    ltype = current.get("TYPE", "")
                    kicad = ODB_TO_KICAD_LAYER.get(name)
                    if kicad:
                        self.layers.append((name, kicad, ltype))
            elif "=" in line:
                k, _, v = line.partition("=")
                current[k.strip()] = v.strip()
        if not self.layers:
            self.warnings.append("No recognized layers in matrix")

    def _parse_netlist(self):
        lines = self._read_file("steps", "pcb", "netlists", "cadnet", "netlist")
        for line in lines:
            line = line.strip()
            m = re.match(r'^\$(\d+)\s+(.+)$', line)
            if m:
                self.net_names[int(m.group(1))] = m.group(2).strip()

    def _parse_profile(self):
        lines = self._read_file("steps", "pcb", "profile")
        for line in lines:
            line = line.strip()
            if line.startswith("UNITS="):
                self.units = line.split("=")[1].strip()
            elif line.startswith("OS "):
                parts = line.split()
                if len(parts) >= 3:
                    x = float(parts[1])
                    y = -float(parts[2])
                    self.outline_pts.append((x, y))
        if not self.outline_pts:
            self.outline_pts = [(0,0),(200,0),(200,150),(0,150)]
            self.warnings.append("No board outline found — using 200x150mm default")

    def _parse_eda(self):
        """Parse eda/data for component placements and pad-net assignments."""
        lines = self._read_file("steps", "pcb", "eda", "data")
        if not lines:
            return

        # Parse units
        for line in lines:
            if line.startswith("UNITS="):
                self.units = line.split("=")[1].strip()
                break

        # Build component list from SNT records
        # SNT side type pkg_idx cmp_idx  -> gives position of each component pin
        # CMP records give placement; parse NET blocks for pad-net mapping
        net_pad_map = {}  # (cmp_idx, pin_idx) -> net_name
        current_net = ""
        cmp_placements = {}  # cmp_idx -> {ref, pkg, x, y, rot, side}

        i = 0
        while i < len(lines):
            line = lines[i].rstrip()

            if line.startswith("NET "):
                current_net = line[4:].strip()

            elif line.startswith("SNT "):
                # SNT side type pkg_idx cmp_idx
                parts = line.split()
                if len(parts) >= 5:
                    cmp_idx = int(parts[4])
                    pin_idx = 0  # will be assigned by FID lines
                    # next lines are FID records
                    j = i + 1
                    while j < len(lines) and lines[j].startswith("FID"):
                        fid_parts = lines[j].split()
                        if len(fid_parts) >= 3 and fid_parts[1] == "C":
                            cmp_i = int(fid_parts[2])
                            net_pad_map[(cmp_i, int(fid_parts[3]) if len(fid_parts) > 3 else 0)] = current_net
                        j += 1

            i += 1

        # Parse CMP block for actual placements (in some ODB++ exports from KiCad)
        # Try looking in the component layer files instead
        self._parse_component_layers(net_pad_map)

    def _parse_component_layers(self, net_pad_map: dict):
        """Parse COMP_+_TOP and COMP_+_BOT component placement files."""
        for comp_file, side in [
            (os.path.join(self.root, "steps", "pcb", "layers", "comp_+_top", "components"), "F"),
            (os.path.join(self.root, "steps", "pcb", "layers", "comp_+_bot", "components"), "B"),
        ]:
            if not os.path.exists(comp_file):
                continue
            with open(comp_file, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            units = self.units
            for line in lines:
                line = line.rstrip()
                if line.startswith("UNITS="):
                    units = line.split("=")[1].strip()
                    continue
                if not line or line.startswith("#") or line.startswith("@") or line.startswith("&"):
                    continue
                # CMP record: CMP pkg_idx x y rot mirror ref pkg ;attrs
                if line.startswith("CMP "):
                    line_clean = line.split(";")[0].strip()
                    parts = line_clean.split()
                    if len(parts) >= 7:
                        try:
                            x = float(parts[2]); y = -float(parts[3])
                            rot = float(parts[4])
                            mirror = parts[5] == "M"
                            ref = parts[6].strip("'\"")
                            pkg = parts[7].strip("'\"") if len(parts) > 7 else ""
                            kicad_layer = "B.Cu" if (side == "B" or mirror) else "F.Cu"
                            fp = Footprint(
                                ref=ref, value=pkg,
                                x=x, y=y, rotation=rot,
                                layer=kicad_layer
                            )
                            self.footprints.append(fp)
                        except (ValueError, IndexError):
                            pass

    def _parse_layers(self):
        """Parse feature files for each copper and doc layer."""
        layers_dir = os.path.join(self.root, "steps", "pcb", "layers")
        if not os.path.exists(layers_dir):
            self.warnings.append("No layers directory found")
            return

        for layer_dir in os.listdir(layers_dir):
            feat_path = os.path.join(layers_dir, layer_dir, "features")
            if not os.path.exists(feat_path):
                continue

            layer_lower = layer_dir.lower()

            # Handle drill layers separately — all P records are vias/holes
            if "drill" in layer_lower:
                self._parse_drill_layer(
                    feat_path,
                    os.path.join(layers_dir, layer_dir, "tools"),
                    is_plated="non-plated" not in layer_lower
                )
                continue

            kicad_layer = ODB_TO_KICAD_LAYER.get(layer_lower)
            if not kicad_layer:
                continue

            is_copper = kicad_layer.endswith(".Cu")
            tracks, vias, pads, graphics = parse_features(
                feat_path, self.units, self.net_names
            )

            if is_copper:
                self.tracks.extend(tracks)
                self.vias.extend(vias)
            self.graphics.extend(graphics)

        if not self.tracks and not self.vias:
            self.warnings.append("No routed tracks or vias found — copper may be all polygon fills (not yet supported)")

    def _parse_drill_layer(self, feat_path: str, tools_path: str, is_plated: bool):
        """Parse ODB++ drill layer — all P records become vias or holes."""
        # Parse tool sizes (in micro-units, divide by 10000 for mm)
        tool_sizes = {}  # tool_num -> drill_size_mm
        if os.path.exists(tools_path):
            current_tool = {}
            with open(tools_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line == "TOOLS {":
                        current_tool = {}
                    elif line == "}":
                        if "NUM" in current_tool and "FINISH_SIZE" in current_tool:
                            num = int(current_tool["NUM"])
                            size = float(current_tool["FINISH_SIZE"]) / 10000.0
                            tool_sizes[num] = size
                    elif "=" in line:
                        k, _, v = line.partition("=")
                        current_tool[k.strip()] = v.strip()

        # Parse features
        symbols = {}
        with open(feat_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        units = self.units
        for line in lines:
            line = line.rstrip()
            if line.startswith("UNITS="):
                units = line.split("=")[1].strip()
            elif line.startswith("$"):
                parts = line[1:].split(" ", 1)
                if len(parts) == 2:
                    idx = int(parts[0])
                    sym_info = _parse_sym_def(parts[1].strip(), units)
                    symbols[idx] = sym_info

        for line in lines:
            line = line.rstrip()
            if not line.startswith("P "):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            try:
                x = float(parts[1]); y = -float(parts[2])
                sym_idx = int(parts[3])
                tool_num = int(parts[5]) if len(parts) > 5 else 0

                # Get drill size from tools file, fallback to symbol size
                drill = tool_sizes.get(tool_num, 0)
                if drill == 0:
                    sym_info = symbols.get(sym_idx, ("circle", 0.3, 0.3, 0))
                    drill = sym_info[1]

                pad_size = drill * 1.8  # typical annular ring
                net = _extract_net(line, self.net_names)
                self.vias.append(Via(x, y, pad_size, drill, net))
            except (ValueError, IndexError):
                continue


# ─── KiCad writer ─────────────────────────────────────────────────────────────

class KiCadWriter:
    def __init__(self, parser: ODBParser):
        self.p = parser
        # Build net id map
        self.net_id = {"": 0}
        for i, name in parser.net_names.items():
            self.net_id[name] = i + 1

    def _nid(self, name: str) -> int:
        return self.net_id.get(name, 0)

    def write(self, out_path: str):
        out = []
        out.append('(kicad_pcb (version 20221018) (generator odb_to_kicad)')
        out.append('')
        out.append('  (general')
        out.append('    (thickness 1.6)')
        out.append('  )')
        out.append('')
        out.append('  (layers')
        out.append(KICAD_LAYERS)
        out.append('  )')
        out.append('')

        # Nets
        out.append('  (net 0 "")')
        for idx, name in sorted(self.p.net_names.items()):
            out.append(f'  (net {idx + 1} "{name}")')
        out.append('')

        # Board outline
        pts = self.p.outline_pts
        for i in range(len(pts)):
            x1, y1 = pts[i]; x2, y2 = pts[(i+1) % len(pts)]
            out.append(f'  (gr_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})'
                       f' (layer "Edge.Cuts") (width 0.05))')
        out.append('')

        # Footprints
        for fp in self.p.footprints:
            out += self._write_footprint(fp)

        # Tracks
        for t in self.p.tracks:
            out.append(
                f'  (segment (start {t.x1:.4f} {t.y1:.4f}) (end {t.x2:.4f} {t.y2:.4f})'
                f' (width {t.width:.4f}) (layer "{t.layer}") (net {self._nid(t.net)}))'
            )

        # Vias
        for v in self.p.vias:
            out.append(
                f'  (via (at {v.x:.4f} {v.y:.4f}) (size {v.size:.4f})'
                f' (drill {v.drill:.4f}) (layers "F.Cu" "B.Cu") (net {self._nid(v.net)}))'
            )

        # Graphics
        for g in self.p.graphics:
            out.append(
                f'  (gr_line (start {g.x1:.4f} {g.y1:.4f}) (end {g.x2:.4f} {g.y2:.4f})'
                f' (layer "{g.layer}") (width {g.width:.4f}))'
            )

        out.append(')')
        out.append('')

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        print(f"[OK] Written: {out_path}")

    def _write_footprint(self, fp: Footprint) -> list:
        out = []
        silk = "F.SilkS" if fp.layer == "F.Cu" else "B.SilkS"
        fab  = "F.Fab"   if fp.layer == "F.Cu" else "B.Fab"
        out.append(f'  (footprint "{fp.value}" (layer "{fp.layer}")')
        out.append(f'    (at {fp.x:.4f} {fp.y:.4f} {fp.rotation:.2f})')
        out.append(f'    (attr smd)')
        out.append(f'    (fp_text reference "{fp.ref}" (at 0 -1) (layer "{silk}")'
                   f' (effects (font (size 1 1) (thickness 0.15))))')
        out.append(f'    (fp_text value "{fp.value}" (at 0 1) (layer "{fab}") hide'
                   f' (effects (font (size 1 1) (thickness 0.15))))')
        for pad in fp.pads:
            out += self._write_pad(pad, fp.layer)
        out.append('  )')
        return out

    def _write_pad(self, pad: Pad, fp_layer: str) -> list:
        out = []
        if pad.pad_type == "thru_hole":
            layers = '"*.Cu" "*.Mask"'
        else:
            mask = "F.Mask" if fp_layer == "F.Cu" else "B.Mask"
            layers = f'"{fp_layer}" "{mask}"'

        net_str = f' (net {self._nid(pad.net)} "{pad.net}")' if pad.net else ''
        rr_str = f' (roundrect_rratio {pad.roundrect_ratio:.4f})' if pad.shape == "roundrect" else ''
        drill_str = f' (drill {pad.drill:.4f})' if pad.pad_type == "thru_hole" else ''

        out.append(
            f'    (pad "{pad.number}" {pad.pad_type} {pad.shape}'
            f' (at {pad.x:.4f} {pad.y:.4f} {pad.rotation:.2f})'
            f' (size {pad.width:.4f} {pad.height:.4f})'
            f'{drill_str} (layers {layers}){rr_str}{net_str})'
        )
        return out


# ─── Main ─────────────────────────────────────────────────────────────────────

def convert(input_path: str, output_path: str):
    tmp_dir = None
    odb_dir = input_path

    # Extract archive if needed
    if os.path.isfile(input_path):
        tmp_dir = tempfile.mkdtemp(prefix="odb2kicad_")
        try:
            if tarfile.is_tarfile(input_path):
                with tarfile.open(input_path) as tf:
                    tf.extractall(tmp_dir)
            elif zipfile.is_zipfile(input_path):
                with zipfile.ZipFile(input_path) as zf:
                    zf.extractall(tmp_dir)
            else:
                print("Error: not a .tgz/.zip archive and not a directory")
                sys.exit(1)
        except Exception as e:
            print(f"Error extracting: {e}")
            sys.exit(1)
        odb_dir = tmp_dir

    print(f"[..] Parsing ODB++: {input_path}")
    parser = ODBParser(odb_dir)
    parser.parse()

    if parser.warnings:
        print("\n[WARNINGS]")
        for w in parser.warnings:
            print(f"  ! {w}")

    writer = KiCadWriter(parser)
    writer.write(output_path)

    print("\n[SUMMARY]")
    print(f"  Layers:     {len(parser.layers)}")
    print(f"  Nets:       {len(parser.net_names)}  (note: ODB++ only contains routed nets, not full schematic netlist)")
    print(f"  Components: {len(parser.footprints)}  (note: unrouted or pad-only components may be absent from ODB++)")
    print(f"  Tracks:     {len(parser.tracks)}")
    print(f"  Vias:       {len(parser.vias)}")
    print(f"  Graphics:   {len(parser.graphics)}")
    print(f"  Warnings:   {len(parser.warnings)}")

    print("\n[KNOWN LIMITATIONS]")
    print("  - Copper pours/polygon fills not converted (they are skipped; zones not yet supported)")
    print("  - Net count reflects routed nets only — full schematic netlist is not in ODB++")
    print("  - Components absent from ODB++ comp layer (no copper footprint) will be missing")
    print("  - Arc segments approximated as straight lines")
    print("  - Pad net assignment requires EDA data cross-referencing (pads show net 0)")
    print("  - Mask/paste/inner copper layers appear only if component pads reference them")

    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    inp = sys.argv[1]

    if len(sys.argv) > 2:
        out = sys.argv[2]
    else:
        # Default: output goes to output_PCB/ folder next to input
        base = os.path.splitext(os.path.basename(inp))[0]
        out_dir = os.path.join(os.path.dirname(os.path.abspath(inp)), "..", "output_PCB")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, base + ".kicad_pcb")

    convert(inp, out)
