"""Offline parallel-NAND identification using attributed database patterns."""
from functools import lru_cache
from importlib.resources import files
import json
import re


def parse_id(value):
    """Accept contiguous hex or complete bytes separated by spaces, : or -."""
    value = value.strip()
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}){2,8}|'
                        r'[0-9a-fA-F]{2}(?:[ :\-]+[0-9a-fA-F]{2}){1,7}', value):
        raise ValueError('NAND ID must contain 2 to 8 complete hexadecimal bytes')
    return bytes.fromhex(re.sub(r'[ :\-]', '', value))


@lru_cache(maxsize=1)
def database():
    return json.loads(files('veryflashy').joinpath('data/nand.json').read_text())


def decode(flash_id):
    """Return all compatible patterns; never guess missing required ID bytes.

    Database matches are candidates, not unique physical-package identities.
    Null pattern bytes are wildcards; literal 00/ff input bytes stay literal.
    """
    if not isinstance(flash_id, bytes) or not 2 <= len(flash_id) <= 8:
        raise ValueError('NAND ID must be 2 to 8 bytes')
    db = database()
    matches = []
    for record in db['records']:
        required = [(i, v) for i, v in enumerate(record['pattern']) if v is not None]
        if all(i < len(flash_id) and flash_id[i] == v for i, v in required):
            matches.append({**record, 'matched_bytes': len(required)})
    matches.sort(key=lambda r: (-r['matched_bytes'], r['source'], r['line']))
    return {
        'id': flash_id.hex(),
        'manufacturer': db['manufacturers'].get(f'{flash_id[0]:02x}'),
        'candidates': matches,
    }


def print_summary(flash_id):
    result = decode(flash_id)
    print(f'NAND decode for {flash_id.hex("-")} (offline):')
    manufacturer = result['manufacturer']
    if manufacturer:
        print(f'  Manufacturer: {manufacturer["name"]} (ID 0x{flash_id[0]:02x})')
    else:
        print(f'  Manufacturer: unknown (ID 0x{flash_id[0]:02x})')
    if not result['candidates']:
        print('  No part match in the bundled database.')
        print('  Part number, geometry and cell type remain unknown.')
        return
    print('  Database candidates (ID patterns do not uniquely identify a package):')
    for candidate in result['candidates']:
        print(f'    {candidate["description"]} '
              f'[{candidate["source"]}:{candidate["line"]}; '
              f'{candidate["matched_bytes"]} specified ID bytes matched]')
        if 'capacity_bytes' in candidate:
            print(f'      Database geometry: {candidate["capacity_bytes"]} bytes total, '
                  f'{candidate["page_bytes"]} bytes/page + '
                  f'{candidate["spare_bytes"]} spare, '
                  f'{candidate["erase_bytes"]} bytes/erase block')
    print('  Cell type and die count are not inferred. Geometry is not USB capacity.')
