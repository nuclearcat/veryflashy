# veryflashy

Extracts information about the controller chips and
and NAND flash chips used in
[USB flash drives](https://en.wikipedia.org/wiki/USB_flash_drive).

Currently, it can interface with several common brands of USB NAND flash controller chips,
and can extract the NAND flash chip IDs from most of them:

| Manufacturer | Controller chip(s) | Flash chip ID? | Other features |
|:--------|:-----------:|:-------------:|:------------:|
| ASolid | IS918 family, tested with 18002S firmware | ✓ | Model heuristic, firmware, programmed USB identity/capacity and MPTool metadata; [protocol and support limits](docs/asolid.md) |
| Phison | PS23xx | ✓ | Controller chip ID, controller firmware version, [partitioning info](https://gist.github.com/warewolf/e19d6817f1d59939a32fbd9e1a30b9d2) |
| Alcor | AU698x | ✓ | |
| AppoTech | DM82xx | ✓ | |
| iCreate | i80xx | ✓ | |
| ?[^1] | PL2530 | ◌ | |

[^1]: I truly don't what company makes this flash chip, but my crude [fuzzer](#fuzzer)
was able to extract some information from an old USB drive, including the string "PL2530" and
the size of the flash in 512-byte blocks.

## Running it

| ⚠️ Warning |
|:-----------|
| This tool *tries* to issue only read-only commands, but since nearly all of them are undocumented and nonstandard, there's always a chance that it will delete or corrupt data from your USB flash drive. Don't run it unless you're okay with losing all of the data on the device, or even [bricking](https://en.wikipedia.org/wiki/Brick_(electronics)) it permanently. |

Check out this repository, then `sudo uv run veryflashy /dev/sdX` in it
(or `uv run sudo --preserve-env=PATH python -m veryflashy /dev/sdX`).
NAND IDs are automatically decoded using the bundled offline database.
The `-l` / `--lookup` option is still accepted and now uses this same database.
You can also decode an ID without a device or root:

```sh
veryflashy --decode-id 2c-d3-08-32-e8-30-12
```

```text
NAND decode for 2c-d3-08-32-e8-30-12 (offline):
  Manufacturer: Micron (ID 0x2c)
  Database candidates (ID patterns do not uniquely identify a package):
    MT29F1T08EBLCH [micron-b58r; 7 specified ID bytes matched]
      Die family: B58R | 232-layer TLC | 128 GiB raw/die
  Unlisted properties and physical die count remain unknown. NAND density is not USB capacity.
```

The database includes 158 patterns from GPL-compatible NANDO and Allwinner
sources, a curated Micron B58R entry, and manufacturer codes from OpenOCD.
Matching parts are reported
as candidates with source attribution; NANDO entries also include geometry.
See [decoder coverage, licenses and update instructions](docs/nand-decoder.md).

For ASolid drives, use `sudo uv run veryflashy -m asolid /dev/sdX`, or leave
out `-m` for automatic detection. The detector checks the extended SCSI
INQUIRY signature before issuing ASolid commands. NAND IDs, model registers
and programmed configuration are queried only for the tested `18002S`
firmware family. Other ASolid firmware is reported without trying unverified
NAND-ID commands or changing modes.
The exact controller suffix and NAND part number are not inferred from the
USB ID. See [the ASolid protocol notes](docs/asolid.md) for a captured example.

## Credits and inspiration

- [Phison drive mode configuration](https://gist.github.com/warewolf/e19d6817f1d59939a32fbd9e1a30b9d2)
- [Alcor flash controller hacking](https://github.com/tizbac/alcorhack) ([blog](https://linuxehacking.ovh/2014/07/20/alcor-ufd-controller-hacking-update-2/))

## Fuzzer 💡

I wrote a fuzzer ([scsifuzz.py](veryflashy/scsifuzz.py)) which just tries all possible 2-bytes prefixes for
[SCSI commands](https://en.wikipedia.org/wiki/SCSI#SCSI_command_protocol), excluding those which
are [part of the usual USB Mass Storage command set](https://web.archive.org/web/20210302020418/http://aidanmocke.com/blog/2020/12/30/USB-MSD-1/) (and
thus unlikely to access any hidden features) and those which seem like they could be unusually destructive
([having "write" or "format" in the description](https://www.t10.org/lists/2op.htm), for instance).

It's very crude, but seemingly effective. I was able to immediately figure out the AppoTech DM8233
controller chip with it.

## Goal

The goal of this tool is to be like "ChipEasy" or "ChipGenius",
but not some horrific black-box Windows EXE distributed on sketchy
malware-ridden websites, and written in broken
English, Russian, and Chinese.
