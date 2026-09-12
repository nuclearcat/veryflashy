#!/usr/bin/env python3
"""Regenerate the bundled database from checksum-verified upstream files.

Download the URLs in veryflashy/data/nand-sources.json to a directory, using
their keys as filenames, then run this script with that directory as argument.
No upstream code is executed. See docs/nand-decoder.md for licensing and scope.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def generate(directory):
    sources = json.loads((ROOT / 'veryflashy/data/nand-sources.json').read_text())
    texts = {}
    for name, source in sources.items():
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError(f'Checksum mismatch: {name}')
        texts[name] = data.decode('utf-8')

    definitions = dict(re.findall(r'NAND_MFR_(\w+)\s*=\s*(0x[0-9a-f]+)',
                                  texts['openocd-core.h']))
    manufacturers = {
        f'{int(definitions[key], 16):02x}': {'name': name, 'source': 'openocd-core.c'}
        for key, name in re.findall(r'\{NAND_MFR_(\w+), "([^"]+)"\}',
                                    texts['openocd-core.c'])
    }
    records = []
    for line_number, line in enumerate(texts['nando.csv'].splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        row = next(csv.reader([line], skipinitialspace=True))
        if len(row) != 41:
            raise ValueError(f'Unexpected NANDO row {line_number}')
        records.append({
            'pattern': [None if v.strip() == '-' else int(v) for v in row[36:]],
            'description': row[0], 'page_bytes': int(row[1]),
            'erase_bytes': int(row[2]), 'capacity_bytes': int(row[3]),
            'spare_bytes': int(row[4]), 'source': 'nando.csv', 'line': line_number,
        })

    vendor = None
    for line_number, line in enumerate(texts['sunxi-nand_id.c'].splitlines(), 1):
        table = re.match(r'struct __NandPhyInfoPar_t (\w+)NandTbl\[\]', line)
        if table:
            vendor = table[1]
        row = re.match(r'\s*\{ \{([^}]+)\},(.*?)\},\s*//\s*(.*)', line)
        if not row:
            continue
        ids = [int(v.strip(), 16) for v in row[1].split(',')]
        if ids[0] == 255:  # sentinel/default, not a real device
            continue
        if len(ids) != 8 or vendor is None:
            raise ValueError(f'Unexpected Allwinner row {line_number}')
        manufacturers.setdefault(f'{ids[0]:02x}',
                                 {'name': vendor, 'source': 'sunxi-nand_id.c'})
        # Preserve table labels verbatim: some are families or multiple parts.
        # Geometry is deliberately not imported from this controller table.
        records.append({
            'pattern': [None if v == 255 else v for v in ids],
            'description': row[3].strip(), 'source': 'sunxi-nand_id.c',
            'line': line_number,
        })
    if len(records) < 100 or len(manufacturers) < 8:
        raise ValueError('Unexpectedly small import')
    return {'schema_version': 1, 'manufacturers': manufacturers, 'records': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'veryflashy/data/nand.json')
    args = parser.parse_args()
    database = generate(args.directory)
    args.output.write_text(json.dumps(database, indent=2) + '\n')
    print(f"Imported {len(database['records'])} patterns and "
          f"{len(database['manufacturers'])} manufacturers")
