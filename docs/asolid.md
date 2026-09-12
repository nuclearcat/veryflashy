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
| `0x6fd` | Byte | Recorded CE count; written at `0x460162..0x46016f` |
| `0x6fe` | Byte | Recorded NAND LUNs per CE; written at `0x460175..0x460193` |

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

## Recorded topology and capacity estimate

The protocol builder copies device-context byte `0x12e9b` into `0x6fd`.
The same byte is logged as **CE count** at `0x449bae..0x449bcc`, using
the format string at `0x69de1c`. The accompanying die count is that value
multiplied by AFMI byte `0x44`, labeled `u8LUNCount` in the AFMI dump
(string file offset `0x2a739c`). The builder copies this AFMI byte into
`0x6fe`, substituting 1 if zero. The captured values are **2 CEs** and
**1 NAND LUN per CE**, giving **2 configured dies** by MPTool's calculation.
These are recorded configuration values, not physical package inspection.
The decoder accepts counts from 1 to 16; zero, erased `ff`, and values
outside this supported range remain unknown. It does not substitute counts
for missing fields or derive them from the number of returned ID slots.

CE count does not establish independent channel count. MPTool's separate
`FlashChannel` INI setting is loaded into settings byte `0x1a54` at
`0x411696..0x4116bf`. The packaged defaults (`FlashChannel=0`,
`ExtraReserve=4`, `HiddenAreaSize=0`) do not identify this drive's settings.
AFMI's `u8PlaneNum` byte `0x79` is also copied into protocol `0x6fc`, which
contains `01` here; its encoding is not yet decoded as a physical plane count.

For identical returned NAND IDs, if all matching database candidates agree
on an explicit `die_capacity_bytes`, veryflashy estimates raw main-data
capacity as configured dies times per-die density. It never substitutes
package-level `capacity_bytes`. Missing counts/capacity, mixed IDs, unknown
or conflicting die densities, and inferred raw capacity below programmed
capacity suppress the estimate. The estimate does not require a new command.

For this capture, assuming two 128 GiB B58R dies gives 256 GiB raw and a
**25.0625 GiB gap (9.79% of raw)** from the 230.9375 GiB exposed capacity.
This is not a measurement of free replacement blocks, extra reserve,
hidden user area or SLC cache; it does not split internal allocations.
NAND OOB/spare bytes are excluded from this calculation. Channel count,
reserve allocation, hidden area, SLC cache and bad-block counts remain
explicitly unknown in the output.

### Advertised GB versus nominal NAND GiB

The owner reports that this drive is branded **256 GB**. That label uses
decimal capacity: `1 GB = 1,000,000,000 bytes`, as explained in
[Kingston's Flash Memory Guide](https://media.kingston.com/pdfs/MKF-283.3-Flash-Memory-Guide_EN.pdf).
Here, `1 GiB = 1,073,741,824 bytes`. The nominal NAND estimate uses the
[Micron die density](micron-b58r.md), while the exposed capacity comes from
the controller's SCSI response, before filesystem overhead.

| Capacity basis | Bytes | Decimal GB | Binary GiB |
| --- | ---: | ---: | ---: |
| Estimated two 128 GiB NAND dies | 274877906944 | 274.877907 | 256 |
| Owner-reported advertised capacity | 256000000000 | 256 | 238.418579 |
| Controller-exposed capacity | 247967252480 | 247.967252 | 230.9375 |

These give two different comparisons:

* Advertised minus exposed: **8032747520 bytes**, or **8.03274752 GB**
  (7.4810791 GiB), **3.137792% of advertised capacity**.
* Estimated raw NAND minus exposed: **26910654464 bytes**, or
  **25.0625 GiB**, **9.7900391% of estimated raw capacity**.

The printed 9.79% uses estimated raw NAND as its denominator. It is not
the shortfall from the 256 GB label or a measured reserve percentage.
The advertised capacity is owner-supplied context, not a field recovered
from MPTool or SCSI; veryflashy does not infer a marketing capacity from
VID/PID, round up the measured capacity, or use this example for other drives.

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
Recorded chip-enable count (CE): 2
Recorded NAND LUNs per CE: 1
Configured die count (CE x LUNs per CE): 2
Independent NAND channels: unknown
Reserve allocation, hidden area, SLC cache and bad-block counts: unknown
Estimated raw NAND capacity: 256 GiB (assuming 2 dies x 128 GiB from NAND database)
Estimated raw-to-user capacity gap: 25.0625 GiB (9.79% of raw; 26910654464 bytes)
This gap does not identify how capacity is allocated internally; NAND OOB is excluded.
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
Topology tests also cover missing/invalid counts, mixed NAND IDs, ambiguous
or package-only density, and inconsistent or equal capacities.
