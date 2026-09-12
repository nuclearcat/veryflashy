"""ASolid IS918 identification, recovered from IS918EN MPTool.

See docs/asolid.md for the protocol and the hardware capture used to verify it.
"""

from py_sg import SCSIError

from .common import bytesy, sgread
from . import nand


def _ascii_field(data: bytes, offset: int, size: int):
    field = data[offset:offset + size]
    if field[0] in (0, 0xff):
        return None
    field = field.split(b'\0', 1)[0]
    if any(b < 0x20 or b > 0x7e for b in field):
        raise ValueError(f'Nonprintable protocol field at 0x{offset:x}')
    return field.decode('ascii')


def _usb_string(data: bytes, table_offset: int):
    offset = int.from_bytes(data[table_offset:table_offset + 2], 'big')
    size = int.from_bytes(data[table_offset + 2:table_offset + 4], 'big')
    if (offset, size) in ((0, 0), (0xffff, 0xffff)):
        return None
    if (size < 2 or size > 254 or size % 2 or offset + size > 0x200
            or data[offset:offset + 2] != bytes((size, 3))):
        raise ValueError(f'Invalid USB string descriptor at table 0x{table_offset:x}')
    value = data[offset + 2:offset + size].decode('utf-16le')
    if any(not c.isprintable() for c in value):
        raise ValueError('Nonprintable USB string descriptor')
    return value or None


def decode_protocol(data: bytes) -> dict:
    """Decode the verified common fields of the 18002S protocol page."""
    if len(data) != 4096 or data[0x685:0x68d] != b'PROTOCOL':
        raise ValueError('Expected a 4096-byte ASolid PROTOCOL page')
    if data[:2] != b'\x12\x01':
        raise ValueError('Missing protocol USB device descriptor')
    capacity = int.from_bytes(data[0x69d:0x6a1], 'big')
    # Recorded CE/LUN counts, not ID-slot counts or independent channels.
    ce_count = data[0x6fd] if 1 <= data[0x6fd] <= 16 else None
    luns_per_ce = data[0x6fe] if 1 <= data[0x6fe] <= 16 else None
    return {
        'usb_id': f'{int.from_bytes(data[8:10], "little"):04x}:'
                  f'{int.from_bytes(data[10:12], "little"):04x}',
        'manufacturer': _usb_string(data, 0x218),
        'product': _usb_string(data, 0x214),
        'serial': _usb_string(data, 0x21c),
        'firmware': _ascii_field(data, 0x68d, 16),
        'capacity_mib': None if capacity in (0, 0xffffffff) else capacity,
        'mp_version': _ascii_field(data, 0x6a5, 10),
        'mp_timestamp': _ascii_field(data, 0x6af, 32),
        'ce_count': ce_count,
        'luns_per_ce': luns_per_ce,
        'configured_die_count': ce_count * luns_per_ce if ce_count and luns_per_ce else None,
    }


def _print_topology(info: dict, flashids: list[bytes]):
    for key, label in (('ce_count', 'Recorded chip-enable count (CE)'),
                       ('luns_per_ce', 'Recorded NAND LUNs per CE'),
                       ('configured_die_count', 'Configured die count (CE x LUNs per CE)')):
        value = info[key]
        print(f'  {label}: {value if value is not None else "unknown"}')
    print('  Independent NAND channels: unknown')
    print('  Reserve allocation, hidden area, SLC cache and bad-block counts: unknown')

    # Estimate only for a homogeneous ID and unanimous per-die database
    # density. Package capacity_bytes is deliberately not used as die size.
    reason = None
    die_bytes = None
    if not info['configured_die_count'] or info['capacity_mib'] is None:
        reason = 'missing recorded topology or capacity'
    elif not flashids or len(set(flashids)) != 1:
        reason = 'missing or mixed NAND IDs'
    else:
        candidates = nand.decode(flashids[0])['candidates']
        densities = {c.get('die_capacity_bytes') for c in candidates}
        if len(densities) == 1:
            die_bytes = next(iter(densities))
        if not isinstance(die_bytes, int) or die_bytes <= 0:
            reason = 'unknown or ambiguous per-die NAND density'
    if reason:
        print(f'  Capacity-gap estimate unavailable: {reason}')
        return

    dies = info['configured_die_count']
    raw_bytes = dies * die_bytes
    exposed_bytes = info['capacity_mib'] * 2**20
    if raw_bytes < exposed_bytes:
        print('  Capacity-gap estimate unavailable: inferred raw capacity is below programmed capacity')
        return
    gap_bytes = raw_bytes - exposed_bytes
    print(f'  Estimated raw NAND capacity: {raw_bytes / 2**30:g} GiB '
          f'(assuming {dies} dies x {die_bytes / 2**30:g} GiB from NAND database)')
    print(f'  Estimated raw-to-user capacity gap: {gap_bytes / 2**30:g} GiB '
          f'({100 * gap_bytes / raw_bytes:.2f}% of raw; {gap_bytes} bytes)')
    print('  This gap does not identify how capacity is allocated internally; NAND OOB is excluded.')


def _read_details(fd: int, flashids: list[bytes]):
    # Only called after recognizing 18002S. These optional reads must not
    # prevent NAND decoding if an older firmware rejects them.
    print('Reading ASolid controller model registers:')
    try:
        values = []
        for address in (0xc1c0, 0xc1d3):
            cdb = bytesy('ca 01 01 00 00 00 00 00 00 00 00 00 00 00 41 53')
            cdb = cdb[:3] + address.to_bytes(2, 'big') + cdb[5:]
            value = sgread(fd, cdb, 1)
            if len(value) != 1:
                raise ValueError('Controller register read did not return one byte')
            values.append(value[0])
        c1c0, c1d3 = values
        # MPTool's display heuristic, not an authenticated silicon chip ID.
        model = 'IS918-ENX' if c1d3 == 0x33 else (
            'IS818-EN' if c1c0 == 0xa1 else 'IS918-EN')
        print(f'  Controller model: {model} (MPTool register heuristic)')
        print(f'  Model registers: c1c0={c1c0:02x}, c1d3={c1d3:02x}; silicon revision unknown')
    except (SCSIError, ValueError) as exc:
        print(f'  Controller model unavailable: {exc}')

    print('Reading ASolid programmed configuration (SCSI command ca 00 07 ... 41 53):')
    try:
        data = sgread(fd, bytesy('ca 00 07 00 00 00 00 00 00 00 00 00 00 00 41 53'), 4096)
        info = decode_protocol(data)
    except (SCSIError, ValueError) as exc:
        print(f'  Programmed configuration unavailable: {exc}')
        return
    for field, label in (
        ('usb_id', 'Programmed USB ID'), ('manufacturer', 'USB manufacturer'),
        ('product', 'USB product'), ('serial', 'USB serial'),
        ('firmware', 'Recorded firmware'), ('mp_version', 'Recorded MPTool version'),
        ('mp_timestamp', 'Recorded programming timestamp (timezone unknown)'),
    ):
        if info[field] is not None:
            print(f'  {label}: {info[field]}')
    if info['capacity_mib'] is not None:
        mib = info['capacity_mib']
        print(f'  Programmed capacity: {mib} MiB ({mib * 1048576} bytes)')
    _print_topology(info, flashids)


def probe(fd: int):
    # Check the extended standard INQUIRY before sending any vendor command.
    # Kingston rebrands these drives, so the normal vendor field and VID/PID
    # do not identify the controller reliably.
    try:
        inquiry = sgread(fd, bytesy('12 00 00 00 60 00'), 96)
    except SCSIError as exc:
        raise NotImplementedError('Standard INQUIRY failed') from exc
    if inquiry[0x28:0x2e] != b'ASolid':
        raise NotImplementedError('No ASolid signature in standard INQUIRY')

    print('Reading ASolid firmware info (SCSI command ca 00 ... 41 53):')
    info = sgread(fd, bytesy('ca 00 00 00 00 00 00 00 00 00 00 00 00 00 41 53'), 512)
    # This drive returns only 32 bytes (resid=480), not the requested 512.
    # Once ASolid is recognized, errors must not fall through to other probes.
    if len(info) < 32:
        raise RuntimeError('ASolid firmware information is shorter than 32 bytes')
    firmware = info[:32].split(b'\0', 1)[0]
    if not firmware or any(b < 0x20 or b > 0x7e for b in firmware):
        raise RuntimeError('ASolid firmware information is not printable ASCII')
    print('  Controller vendor: ASolid')
    print(f'  Firmware: {firmware.decode("ascii")}')

    # MPTool selects a different NAND-ID command outside S mode. Only this
    # 18002S path has been tested; never switch modes or try alternate commands.
    if not firmware.startswith(b'18002S'):
        print('  NAND ID and detail queries are only verified for 18002S firmware; skipping')
        return None

    print('Reading ASolid NAND IDs (SCSI command ca 0f ... 41 53):')
    ids = sgread(fd, bytesy('ca 0f 01 01 00 08 07 00 00 00 00 00 00 00 41 53'), 512)
    if len(ids) < 128:
        raise RuntimeError('ASolid NAND ID response is shorter than 128 bytes')

    flashids = []
    # MPTool copies the first 128 bytes as sixteen eight-byte ID slots.
    # Slot numbers are not necessarily physical package or channel numbers.
    for offset in range(0, 128, 8):
        slot = ids[offset:offset + 8]
        if slot[0] in (0x00, 0xff):
            continue
        print(f'  Flash ID (slot {offset // 8}): {slot[:7].hex(sep="-")}')
        flashids.append(slot[:7])

    if not flashids:
        raise RuntimeError('ASolid returned no usable NAND IDs')
    _read_details(fd, flashids)
    # Preserve every displayed ID byte for the offline decoder.
    return flashids[0]
