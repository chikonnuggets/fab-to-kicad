# Manufacture-to-KiCad File Converter

Converts manufacturing PCB formats (ODB++ and IPC-2581) back into KiCad `.kicad_pcb` files.

Useful for recovering design data from fabrication files when the original KiCad project is unavailable.

---

## Supported Formats

| Format | Script | Revisions |
|--------|--------|-----------|
| ODB++ | `odb_to_kicad.py` | Standard (KiCad 8+ export) |
| IPC-2581 | `ipc2581_to_kicad.py` | A, B, C (partial) |

---

## Project Structure

```
Manufacture-to-KiCad-File-Converter/
  fab_files/          ← place input files here (.tgz, .xml)
  output_PCB/         ← converted .kicad_pcb files appear here
  odb_to_kicad.py
  ipc2581_to_kicad.py
  README.md
```

---

## Requirements

- Python 3.8+
- No external dependencies (standard library only)

---

## Usage

### ODB++

```bash
# Input from fab_files/, output goes to output_PCB/ automatically
python3 odb_to_kicad.py fab_files/myboard-odb.tgz

# Or specify output path explicitly
python3 odb_to_kicad.py fab_files/myboard-odb.tgz output_PCB/myboard.kicad_pcb

# Also accepts extracted ODB++ directory or .zip archive
python3 odb_to_kicad.py fab_files/myboard-odb.zip
python3 odb_to_kicad.py /path/to/extracted/odb/dir/
```

### IPC-2581

```bash
python3 ipc2581_to_kicad.py fab_files/myboard.xml

# Or specify output path explicitly
python3 ipc2581_to_kicad.py fab_files/myboard.xml output_PCB/myboard.kicad_pcb
```

### Opening the output

Open the resulting `.kicad_pcb` file in KiCad's PCB editor (Pcbnew):

```
File → Open → select .kicad_pcb
```

---

## What Gets Converted

| Element | ODB++ | IPC-2581 |
|---------|-------|----------|
| Layer stack | ✓ | ✓ |
| Nets | ✓ (routed only) | ✓ |
| Copper tracks | ✓ | ✓ |
| Vias | ✓ | ✓ |
| Component placements | ✓ | ✓ |
| Board outline | ✓ | ✓ |
| Silkscreen / Fab / Courtyard graphics | ✓ | ✓ |
| Copper pours / zones | ✗ | ✗ |
| Pad net assignments | ✗ | ✗ |
| Silkscreen text | ✗ | ✗ |

---

## Known Limitations

### Both formats
- **Copper pours not converted** — polygon fills are skipped. Zones will be absent in the output.
- **Arc segments approximated** — arcs are converted to straight line segments.
- **Pad net assignments not recovered** — pads will show net 0. Net connectivity is preserved on tracks and vias but not mapped to individual pads.

### ODB++
- **Net count will be lower than original** — ODB++ only contains nets that appear on copper. Nets from the schematic that have no routed copper are not present.
- **Component count may be lower than original** — components with no copper footprint in the ODB++ (e.g. mechanical parts, test points with no copper) will be absent.
- **Mask/paste/inner copper layers** — these layers appear in the output only when components have pads on them. Copper pour fills on these layers are not recovered.

### IPC-2581
- **Revision C partial support** — IPC-2581C (KiCad export format) has a different schema to A/B. Layer mapping is handled but component and net data extraction from C revision files is incomplete.
- **Net and component data** — depends on the completeness of the package and netlist sections in the source file.

---

## Verification

After converting, check the output in KiCad:

1. Open the `.kicad_pcb` in Pcbnew
2. Verify the board outline is correct
3. Toggle layer visibility to confirm copper traces are present
4. Use **Inspect → Board Statistics** to compare track and via counts against the converter summary output

The converter prints a summary after each run showing what was recovered and any warnings.

---

## Example Output

```
[..] Parsing ODB++: fab_files/CM5_MINIMA_3-odb.tgz
[OK] Parsed: 33 layers, 221 nets, 84 components, 1874 tracks, 470 vias
[OK] Written: output_PCB/CM5_MINIMA_3-odb.kicad_pcb

[SUMMARY]
  Layers:     33
  Nets:       221  (note: ODB++ only contains routed nets)
  Components: 84   (note: pad-only components may be absent from ODB++)
  Tracks:     1874
  Vias:       470
  Graphics:   14178
  Warnings:   0
```
