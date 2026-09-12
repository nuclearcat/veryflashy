# Offline NAND decoder

NAND IDs returned by controller probes are now automatically decoded against
the bundled database. `-l` / `--lookup` remains accepted, but now explicitly
means offline lookup; it no longer attempts to import the missing `fdnext`
module or contact FlashMaster. No network request is made by the decoder.

Decode an existing ID without root or a connected device:

```sh
veryflashy --decode-id 2c-d3-08-32-e8-30-12
veryflashy --decode-id ecda109544
```

Input accepts 2–8 complete hexadecimal bytes, contiguous or separated by
spaces, colons or hyphens. `--decode-id` cannot be combined with a device or
`--model`. Normal device probing still requires permission to access the disk.

## Coverage and interpretation

The initial snapshot contains 158 ID patterns (19 NANDO, 139 Allwinner) and
12 manufacturer codes. These tables primarily cover older parallel NAND;
they are not a comprehensive database of modern 3D NAND or SPI NAND.

* Manufacturer names come from OpenOCD and Allwinner tables.
* NANDO matches include the original part name and database geometry: total
  bytes, page bytes, spare bytes per page and erase-block bytes.
* Allwinner matches preserve descriptive comments, which may contain a family,
  several part numbers, or an interface note. No geometry is imported from
  this controller configuration table.
* Every candidate displays its source file, line and number of specified ID
  bytes matched. Full immutable URLs, hashes and licenses are packaged in
  [nand-sources.json](../veryflashy/data/nand-sources.json).

All specified bytes must match, including the manufacturer byte. Missing input
bytes cannot satisfy specified database bytes. NANDO `-` and Allwinner `0xff`
pattern bytes become wildcards; input `00` and `ff` bytes remain literal. Extra
input bytes beyond a pattern's specified positions neither prove nor disprove
that candidate. All compatible candidates are retained, most-specific first;
the decoder does not silently pick one when tables overlap or disagree.

A pattern match is not proof of a unique physical package. A two-byte match
is particularly weak. Reported geometry belongs to the database candidate,
not the USB device capacity. The decoder does not infer cell type, die count,
process node or capacity from a generic device-byte table.

For the captured Kingston/ASolid ID `2cd30832e83012`, the result is **Micron**,
with no part match. Geometry and TLC/QLC type remain unknown. In particular,
the legacy meaning of device byte `d3` must not be applied to this modern ID.
ASolid now preserves the seven displayed ID bytes when returning the first
usable slot to the decoder. Other controllers may return fewer bytes. Multiple
ASolid slots are still printed, but only the first usable slot is summarized.

## Sources and licenses

The project code stays GPL-3.0-or-later. The combined database is distributed
under GPL-3.0-only, accommodating NANDO's version-3 grant and selecting version
3 for the two GPL-2.0-or-later sources. Full attribution and the GPLv3 text are
packaged alongside the data and included in both source and wheel distributions.
Package metadata records `GPL-3.0-or-later AND GPL-3.0-only` to describe both
components; this does not relicense the existing code.
See [THIRD_PARTY.txt](../veryflashy/data/THIRD_PARTY.txt).

| Source | Imported material | License evidence |
| --- | --- | --- |
| [NANDO](https://github.com/bbogush/nand_programmer/tree/4d840b7afff7c1a1c02eacce3a72761cd0f58c93) | Parallel chip CSV | README License section, LICENSE.txt and qt/chip_db.cpp: GPL version 3 |
| [Allwinner table](https://github.com/linux-sunxi/linux-sunxi/blob/d47d367036be38c5180632ec8a3ad169a4593a88/drivers/block/sunxi_nand/src/scan/nand_id.c) | ID patterns and descriptions | File header: GPL version 2 or later |
| [OpenOCD](https://github.com/openocd-org/openocd/blob/18674aaeb40e644f329285c0927f4abba86a56c5/src/flash/nand/core.c) | Manufacturer table and core.h ID definitions | Both files: SPDX GPL-2.0-or-later |

Not imported: [fdfdb](https://github.com/iTXTech/fdfdb#license), whose
CC BY-NC-SA 4.0 license adds a noncommercial restriction; Linux/U-Boot
GPL-2.0-only NAND tables; FlashcatUSB's restricted-license database; and
unlicensed MPTool databases. Public availability alone is not permission to
redistribute a database. No database data or decoding code is copied from
FlashMaster/fdnext.

## Reproducing the snapshot

Download each immutable URL in `veryflashy/data/nand-sources.json` into a local
directory using the manifest key as its filename. Then run:

```sh
python tools/import_nand_db.py /path/to/downloads --output /tmp/nand.json
cmp veryflashy/data/nand.json /tmp/nand.json
python -m unittest discover -s tests -v
```

The importer checks all input SHA-256 hashes before parsing, executes no
upstream code, and produces deterministic output. When updating a source,
review its license and schema again before changing the manifest hash.
