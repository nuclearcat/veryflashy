# ASolid IS918 identification

The ASolid detector was implemented by inspecting
`IS918MPTool_EN_241121A_S1` (24.0011.21.1) and validating its information
requests on a Kingston DataTraveler 3.0, USB ID `0951:1666`.
The Windows executable was not run against the drive. The two recovered
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
usable six-byte ID for compatibility with existing detectors and lookup.
Slots whose manufacturer byte is zero or `ff` are omitted. Repeated IDs
remain visible; slot positions are not interpreted as physical topology.

## Captured result

The data-in responses are preserved in `tests/fixtures/asolid.json`, without
the drive's USB serial or device path. Firmware and NAND-ID requests both
returned SCSI status 0.

```text
Controller vendor: ASolid (exact chip model unknown)
Firmware: 18002SM3U_4A1005_Oct 25 2024
Flash ID (slot 0): 2c-d3-08-32-e8-30-12
Flash ID (slot 2): 2c-d3-08-32-e8-30-12
```

The code-information trailer is ASCII `405`; its meaning is unverified.
The exact EN/ENX suffix, physical NAND part number, TLC/QLC type and die
count have not been established. The tested commands do not download
firmware, change mode, erase or write user data. A full-media integrity
check was not performed after these reads.

Only the NAND-ID request for firmware beginning `18002S` is enabled.
MPTool has an alternate `ca 04` path for other modes, but it has not been
validated here and is intentionally not used. Recognized ASolid devices
with unsupported firmware still report firmware information and stop;
they do not fall through to unrelated vendor probes. Malformed responses
and failures after recognition propagate as errors.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

Tests replay the captured responses and exercise signature gating,
unsupported firmware modes, short/invalid replies, empty slots, errors
and CLI routing without accessing USB devices.
