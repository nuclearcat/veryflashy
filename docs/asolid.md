# ASolid IS918 identification

The ASolid detector was implemented by inspecting
`IS918MPTool_EN_241121A_S1` (24.0011.21.1) and validating its information
requests on a Kingston DataTraveler 3.0, USB ID `0951:1666`.
The Windows executable was not run against the drive. The recovered
vendor requests were sent independently through Linux SCSI pass-through.

The package is listed at https://www.usbdev.ru/files/asolid/is918enmpt/.
The analyzed `IS918MPTool.exe` has SHA-256
`c4f90af53b4df1ca601ddae560cbb28a3c8f62db42fa9472bf3a5f094107fb46`.
All executable addresses below use its preferred image base `0x400000`.
No proprietary binaries are included in this repository.

## Detection and commands

| Request | CDB | Requested response |
| --- | --- | --- |
| Standard INQUIRY | `12 00 00 00 60 00` | 96 bytes |
| Firmware information | `ca 00 00 00 00 00 00 00 00 00 00 00 00 00 41 53` | 512 bytes |
| NAND IDs in 18002S firmware | `ca 0f 01 01 00 08 07 00 00 00 00 00 00 00 41 53` | 512 bytes |
| Model register `c1c0` in 18002S firmware | `ca 01 01 c1 c0 00 00 00 00 00 00 00 00 00 41 53` | 1 byte |
| Model register `c1d3` in 18002S firmware | `ca 01 01 c1 d3 00 00 00 00 00 00 00 00 00 41 53` | 1 byte |
| Programmed configuration in 18002S firmware | `ca 00 07 00 00 00 00 00 00 00 00 00 00 00 41 53` | 4096 bytes |

All transfers are device-to-host. The vendor CDBs are 16 bytes long and end
in ASCII `AS`. INQUIRY must contain `ASolid` at offsets `0x28` through
`0x2d`; VID/PID and the ordinary vendor field alone are not sufficient.
This standard query runs before other vendors' probes in automatic mode.

Firmware information is assembled at VA `0x558ce0` (also `0x499960`).
MPTool requests 512 bytes and uses the first 32. The tested drive returns
32 bytes with a residual of 480, which must not be treated as an error.
The printable, NUL-terminated prefix contains its firmware identifier and
date. The remaining trailer bytes are not interpreted.

The mode parser at `0x559470` examines response byte 5: `S` maps to mode 3.
The dispatcher at `0x447c00` selects the NAND-ID builder at `0x5585c0` for
this mode, passing selector 7. That builder uses `ca 0f`, sets byte 5 to 8
and byte 6 to 7, and requests 512 bytes through the SPTI wrapper at
`0x558090`. The wrapper passes the CDB to
`DeviceIoControl(IOCTL_SCSI_PASS_THROUGH_DIRECT, 0x4d014)`.

MPTool copies the first 128 bytes as eight-byte ID slots. The detector
prints seven ID bytes for each nonempty slot, then returns the first
usable seven-byte ID for offline decoding. Other detectors may return fewer
bytes; the decoder does not invent missing bytes.
Slots whose manufacturer byte is zero or `ff` are omitted. Repeated IDs
remain visible; slot positions are not interpreted as physical topology.

## Controller model heuristic

The device-information routine at `0x434100` sets family discriminator 5
at `0x43425e` for A18002. At `0x4342eb` it reads register addresses
`c1c0..c1df`, one byte per request, through `0x55a760` or `0x4f4aa0`.
Both builders use `ca 01 01`, the big-endian address in CDB bytes 3–4,
and a one-byte device-to-host transfer. Only two of those bytes affect the
model name, so veryflashy reads only those addresses.

At `0x43432f`, register `c1d3 == 33` sets device-info flag `0x1b04` to 1;
at `0x434343`, `c1c0 == a1` sets flag `0x1fc8` to 1. The display routine
at `0x41f202` compares these flags against **1** (`edi`, initialized at
`0x41ee32`), in this order:

| Condition | MPTool label |
| --- | --- |
| `c1d3 == 33` | IS918-ENX |
| Otherwise, `c1c0 == a1` | IS818-EN |
| Otherwise | IS918-EN |

The corresponding UTF-16 strings are at `0x69717c`, `0x69719c`, and
`0x6971b8`. The live drive returned `00` at both addresses, with successful
SCSI status and zero residual. This reproduces MPTool's **IS918-EN** label.
It is a heuristic with a default branch, not an authenticated silicon ID:
successful zero-filled replies cannot independently prove the model.
The package marking and silicon revision remain unknown. Other branches
were checked with synthetic tests, not additional physical controllers.

## Programmed configuration

In S mode, `0x4344c5` calls the direct data-in builder at `0x5592b0`
(`ca 00 07`, 4096 bytes). It does not require a mode switch. The parser
checks the eight-byte `PROTOCOL` tag at `0x685` and consumes these fields:

| Offset | Encoding | Meaning / evidence |
| --- | --- | --- |
| `0x008`, `0x00a` | Little-endian 16-bit | USB VID/PID; parsed at `0x434aa5` |
| `0x214`, `0x218`, `0x21c` | Big-endian 16-bit offset + 16-bit length | Product, manufacturer, serial USB string descriptors |
| `0x68d` | 16 ASCII bytes | Recorded firmware identifier; `0x434c00` |
| `0x69d` | Big-endian 32-bit | Capacity in MiB; `0x43497c`, shifted by 11 for 512-byte sectors at `0x4349cd` |
| `0x6a5` | 10 ASCII bytes | MPTool version; copied at `0x434db0` |
| `0x6af` | 32 ASCII bytes | Programming timestamp; copied at `0x434de0` |

The configuration construction code at `0x45fd45` takes MPTool's version
string (`241121A_S1` at `0x69169c` in this executable) and stores it at
`0x6a5`. At `0x45ff66..0x46003d` it formats the host time with
`%Y-%m-%d %H:%M:%S` (`0x6a2854`) into `0x6af`. These are recorded metadata,
not the version of the locally downloaded tool or a current device clock;
the timestamp has no timezone. The captured version is **241108A**.

The decoder requires the full page and tag, checks descriptor bounds,
lengths and type, decodes UTF-16LE, rejects nonprintable text, and omits
unprogrammed fields. The captured capacity, 236480 MiB, equals
247967252480 bytes, matching the separate SCSI capacity query.

The page also contains manufacturing-host details: the code logs a port
index at `0x6cf`, a 12-character MAC address at `0x6d0`, and a computer name
at `0x6dc` (`0x434df5..0x434f1a`). These are not printed by the decoder.
The committed capture substitutes synthetic USB serial, host MAC and
computer-name values, including duplicate ASCII/UTF-16 serial copies.

Additional captured strings are `20.12.04.01` at `0x703`, `2025-09-21` at
`0x71f`, and `18002CF6C_CB10065` at `0x732`. Their precise semantics are
not established. In particular, this executable treats `0x732` as a
numeric parameter in another path (`0x43d5be`), whereas this drive stores
text there. The later layout cannot safely be applied wholesale. Unknown
flags and erased `ff` fields are not presented as NAND timing, ECC,
overprovisioning, cache, or physical topology settings. Full manufacturing
settings and NAND tables would require further protocol work; the MPTool
paths inspected for those involve mode changes and are not used here.

## Captured result

The data-in responses are preserved in `tests/fixtures/asolid.json`, with
the identifying strings sanitized as described above and without the device
path. All captured requests returned SCSI status 0.

```text
Controller vendor: ASolid
Firmware: 18002SM3U_4A1005_Oct 25 2024
Flash ID (slot 0): 2c-d3-08-32-e8-30-12
Flash ID (slot 2): 2c-d3-08-32-e8-30-12
Controller model: IS918-EN (MPTool register heuristic)
Model registers: c1c0=00, c1d3=00; silicon revision unknown
Programmed USB ID: 0951:1666
USB manufacturer: Kingston
USB product: DataTraveler 3.0
USB serial: 000000000000000000000001
Recorded firmware: 18002SM3U_4A1005
Recorded MPTool version: 241108A
Recorded programming timestamp (timezone unknown): 2025-09-21 18:20:18
Programmed capacity: 236480 MiB (247967252480 bytes)
```

The code-information trailer is ASCII `405`; its meaning is unverified.
The separately sourced [NAND identification](micron-b58r.md) matches the
MT29F1T08EBLCH B58R family; exact package suffix and physical die count
remain unknown. The tested commands do not download
firmware, change mode, erase or write user data. A full-media integrity
check was not performed after these reads.

NAND-ID, model-register and configuration requests are enabled only for
firmware beginning `18002S`.
MPTool has an alternate `ca 04` path for other modes, but it has not been
validated here and is intentionally not used. Recognized ASolid devices
with unsupported firmware still report firmware information and stop;
they do not fall through to unrelated vendor probes. Malformed responses
and failures in the core firmware/NAND reads after recognition propagate as
errors. Optional model/configuration reads report failures without preventing
NAND decoding; they never trigger other vendors' probes or alternate commands.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

Tests replay the captured responses and exercise signature gating,
unsupported firmware modes, short/invalid replies, empty slots, errors
and CLI routing without accessing USB devices. Additional tests cover model
selection, configuration decoding, descriptor bounds, malformed text, erased
fields, and preservation of NAND decoding when optional queries fail.
