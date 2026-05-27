# fab-to-kicad

Converts manufacturing PCB formats (ODB++ and IPC-2581) back into KiCad `.kicad_pcb` files.

Useful for recovering design data from fabrication files when the original KiCad project is unavailable.

---

## Supported Formats

| Format | Script | Revisions |
|--------|--------|-----------|
| ODB++ | `odb_to_kicad.py` | Standard (KiCad 8+ export) |
| IPC-2581 | `ipc2581_to_kicad.py` | A, B, C |

---

## Project Structure

```
fab-to-kicad/
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
# Output is saved as <filename>_IPC.kicad_pcb to avoid overwriting originals
python3 ipc2581_to_kicad.py fab_files/myboard.xml

# Or specify output path explicitly
python3 ipc2581_to_kicad.py fab_files/myboard.xml output_PCB/myboard.kicad_pcb
```

### Opening the output

Open the resulting `.kicad_pcb` in KiCad's PCB editor (Pcbnew):

```
File → Open → select .kicad_pcb
```

---

## What Gets Converted

| Element | ODB++ | IPC-2581 |
|---------|-------|----------|
| Layer stack | ✓ | ✓ |
| Nets | ✓ (routed only) | ✓ (routed only) |
| Copper tracks | ✓ | ✓ |
| Vias | ✓ | ✓ |
| Component placements (ref + position) | ✓ | ✓ |
| Board outline | ✓ | ✓ |
| Silkscreen / Fab / Courtyard graphics | ✓ | ✓ |
| Copper pours / zones | ✗ | ✗ |
| Component footprints (pad geometry) | ✗ | ✗ |
| Pad net assignments | ✗ | ✗ |
| Silkscreen text | ✗ | ✗ |

---

## Known Limitations

### Both formats
- **Copper pours not converted** — polygon fills are skipped. Zones will be absent in the output.
- **Component footprints not restored** — component reference designators and positions are recovered but pad geometry requires the original KiCad library. Footprints can be reassigned manually in KiCad after import.
- **Arc segments approximated** — arcs are converted to straight line segments.
- **Pad net assignments not recovered** — pads show net 0. Net connectivity is preserved on tracks and vias only.

### ODB++
- **Net count will be lower than original** — ODB++ only contains nets that appear on copper. Schematic-only nets are not present.
- **Component count may be lower than original** — components with no copper footprint (mechanical parts, some test points) are absent from ODB++.

### IPC-2581
- **Net count will be lower than original** — same as ODB++, only routed nets are present.
- **Revision C tested with KiCad exports** — behaviour with other EDA tool exports may vary.

---

## Verification

After converting, check the output in KiCad:

1. Open the `.kicad_pcb` in Pcbnew
2. Verify the board outline is correct
3. Toggle layer visibility to confirm copper traces and vias are present
4. Use **Inspect → Board Statistics** to compare counts against the converter summary

The converter prints a summary after each run:

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

[KNOWN LIMITATIONS]
  - Copper pours/polygon fills not converted
  - Component footprints not restored — reassign libraries in KiCad after import
  ...
```

---

## Future Work

- Copper pour / zone recovery
- Component footprint library matching
- Arc segment proper conversion
- Pad net assignment from EDA netlist cross-reference
