# Micron B58R identification

The locally observed seven-byte ID `2c d3 08 32 e8 30 12` identifies the
**MT29F1T08EBLCH / B58R** candidate. Family properties are **232-layer TLC**
and **1 Tbit per die (128 GiB raw)**. These are identification facts, not a
measurement of this drive's usable capacity or physical package arrangement.

## Evidence

* The Kingston/ASolid capture in `tests/fixtures/asolid.json` contains this ID
  in slots 0 and 2. Slot positions do not establish the physical die count.
* [Micron's part catalog](https://www.micron.com/products/storage/nand-flash/3d-nand/part-catalog/part-detail/mt29f1t08eblchd4-r-c)
  lists the ordering variant **MT29F1T08EBLCHD4-R:C**. The public product-data
  endpoint used by that page confirms TLC, 1 Tb component density, x8 bus,
  1.2 V I/O, and a 154-ball VFBGA package (checked 2026-09-12). This confirms
  the base part's existence and TLC/density information, but not that our
  physical device has this complete suffix or package. Package-specific
  properties are therefore not attached to the detected candidate.
* [ACE Lab technical support](https://forum.acelab.eu.com/viewtopic.php?f=179&t=11541),
  reply by Roman_TS dated 2026-07-24, associates the six-byte prefix
  `2cd30832e830` with MT29F1T08EBLCH and B58R.
* [TechInsights' B58R transistor characterization](https://www.techinsights.com/products/tcr-2303-802),
  released 2023-08-15, identifies the family as 232-layer, 1 Tb TLC 3D NAND.
* Local static inspection of IS918MPTool_EN_241121A_S1 found a matching named
  record in `18002CF6C_CB10010.bin` (32,873,296 bytes; SHA-256
  `38efb5e955c515c3e748c0bc8087f39f2223e33a2bb16f53d6446cb556744932`).
  The name starts at offset `0x7760`, and the exact seven-byte ID at `0x778a`.
  This corroborates the public part association. No MPTool code or database
  record is redistributed or required at runtime.

## Matching and limits

Micron's product data lists `128Gb x8` as the component configuration and
`1Tb` as the total component density. The x8 organization is already
included in that total; it must not multiply the 1 Tbit density again.
Using the nominal binary NAND density, `128 * 2^30` eight-bit locations
hold **137438953472 bytes (128 GiB)** per die. Two such dies therefore
give **256 GiB (274.877906944 decimal GB)** nominal main-data capacity,
excluding NAND OOB/spare bytes. A USB drive advertised as **256 GB** uses
a separate decimal capacity basis; see the
[captured drive's capacity comparison](asolid.md#advertised-gb-versus-nominal-nand-gib).

The curated entry requires all seven observed bytes. Six-byte queries and
other seventh-byte variants do not receive this candidate. This deliberately
limits the entry to the observed variant even though public reports use the
six-byte prefix. Additional variants need their own reviewed evidence.

The part remains a database candidate. Complete ordering suffix, package
marking, grade, page/erase geometry, physical die count and package count are
not verified. The raw density belongs to one B58R die, not the whole USB drive.

## Data provenance

`veryflashy/data/nand-curated.json` is an independently authored factual entry
under GPL-3.0-or-later, with references retained alongside it. It is not an
import or relicensing of the MPTool database, forum text, Micron catalog or
TechInsights report. Those sources' licenses remain their own. No prose,
firmware parameters, binary records or third-party database compilation from
these sources is bundled.

The decoder combines curated entries with the reproducibly imported snapshot
at runtime. Rebuilding `nand.json` does not overwrite curated entries.
