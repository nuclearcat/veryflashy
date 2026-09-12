"""ASolid IS918 identification, recovered from IS918EN MPTool.

See docs/asolid.md for the protocol and the hardware capture used to verify it.
"""

from py_sg import SCSIError

from .common import bytesy, sgread


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
    print('  Controller vendor: ASolid (exact chip model unknown)')
    print(f'  Firmware: {firmware.decode("ascii")}')

    # MPTool selects a different NAND-ID command outside S mode. Only this
    # 18002S path has been tested; never switch modes or try alternate commands.
    if not firmware.startswith(b'18002S'):
        print('  NAND ID query is only verified for 18002S firmware; skipping')
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
    # Preserve every displayed ID byte for the offline decoder.
    return flashids[0]
