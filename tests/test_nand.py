import contextlib
import io
import unittest
from unittest.mock import patch

from veryflashy import nand
from veryflashy import __main__ as cli


class DecoderTests(unittest.TestCase):
    def test_captured_asolid_id_identifies_b58r_with_per_die_density(self):
        result = nand.decode(bytes.fromhex('2cd30832e83012'))
        self.assertEqual(result['manufacturer']['name'], 'Micron')
        self.assertEqual(len(result['candidates']), 1)
        part = result['candidates'][0]
        self.assertEqual(part['description'], 'MT29F1T08EBLCH')
        self.assertEqual(part['family'], 'B58R')
        self.assertEqual(part['cell_type'], 'TLC')
        self.assertEqual(part['layers'], 232)
        self.assertEqual(part['die_capacity_bytes'], 128 * 1024**3)
        self.assertEqual(part['matched_bytes'], 7)
        self.assertNotIn('capacity_bytes', part)
        self.assertNotIn('die_count', part)

    def test_incomplete_or_different_micron_ids_do_not_inherit_b58r(self):
        for value in ('2cd30832e830', '2cd30832e83002', '2cd30832e83112',
                      '2cd30c32ea3012'):
            result = nand.decode(bytes.fromhex(value))
            self.assertEqual(result['manufacturer']['name'], 'Micron')
            self.assertEqual(result['candidates'], [])

    def test_known_nando_part_and_geometry(self):
        result = nand.decode(bytes.fromhex('ecda109544'))
        part, family = result['candidates']
        self.assertEqual(part['description'], 'K9F2G08U0C')
        self.assertEqual(part['capacity_bytes'], 256 * 1024**2)
        self.assertEqual(part['page_bytes'], 2048)
        self.assertEqual(part['erase_bytes'], 128 * 1024)
        self.assertEqual(part['spare_bytes'], 64)
        self.assertEqual(part['matched_bytes'], 5)
        self.assertEqual(family['description'], 'K9F2G08')

    def test_conflicting_parts_are_preserved(self):
        matches = nand.decode(bytes.fromhex('20d385250000'))['candidates']
        self.assertEqual({r['description'] for r in matches},
                         {'NAND08GW3C', 'NAND16GW3C'})

    def test_wildcards_do_not_require_padding_but_required_bytes_do(self):
        for value in ('2cda9095', '2cda909500', '2cda9095ff', '2cda909500ff0000'):
            names = {r['description'] for r in nand.decode(bytes.fromhex(value))['candidates']}
            self.assertIn('MT29F2G08ABAEA', names)
        for value in ('2cda90', '2cda0095'):
            names = {r['description'] for r in nand.decode(bytes.fromhex(value))['candidates']}
            self.assertNotIn('MT29F2G08ABAEA', names)

    def test_unknown_manufacturer_and_erased_data(self):
        for value in ('fe123456', '00000000', 'ffffffff'):
            result = nand.decode(bytes.fromhex(value))
            self.assertIsNone(result['manufacturer'])
            self.assertEqual(result['candidates'], [])

    def test_input_formats_preserve_bytes(self):
        for value in ('2Cd30832e83012', '2c-d3-08-32-e8-30-12',
                      '2c d3 08 32 e8 30 12', '2c:d3:08:32:e8:30:12'):
            self.assertEqual(nand.parse_id(value), bytes.fromhex('2cd30832e83012'))
        for value in ('', '2c', '0x2cd3', '2cd', '2g12', '2-cd3',
                      '2c-d308', '00'*9, '2c;d3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nand.parse_id(value)

    def test_invalid_binary_ids(self):
        for value in (b'', b'\x2c', b'\x2c'*9, '2cd3'):
            with self.assertRaises(ValueError):
                nand.decode(value)

    def test_every_bundled_pattern_is_reachable_and_attributed(self):
        db = nand.database()
        import json
        from importlib.resources import files
        sources = json.loads(files('veryflashy').joinpath('data/nand-sources.json').read_text())
        sources.update(db['curated_sources'])
        self.assertEqual(len(db['records']), 159)
        for record in db['records']:
            with self.subTest(source=record['source'], line=record.get('line')):
                self.assertIn(record['source'], sources)
                if 'line' in record:
                    self.assertGreater(record['line'], 0)
                else:
                    self.assertTrue(sources[record['source']]['references'])
                self.assertTrue(2 <= len(record['pattern']) <= 8)
                value = bytes(v if v is not None else 0 for v in record['pattern'])
                found = nand.decode(value)['candidates']
                self.assertTrue(any(r['source'] == record['source'] and
                                    r.get('line') == record.get('line') for r in found))


class OfflineCLITests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.open = self.enterContext(patch.object(cli.os, 'open'))
        self.read = self.enterContext(patch.object(cli, 'sgread'))

    def test_offline_decode_never_opens_a_device(self):
        with patch('sys.argv', ['veryflashy', '--decode-id', '2c-d3-08-32-e8-30-12']):
            cli.main()
        self.open.assert_not_called()
        self.read.assert_not_called()
        self.assertIn('Manufacturer: Micron', self.output.getvalue())
        self.assertIn('MT29F1T08EBLCH', self.output.getvalue())
        self.assertIn('B58R | 232-layer TLC | 128 GiB raw/die', self.output.getvalue())
        self.assertIn('physical die count remain unknown', self.output.getvalue())

    def test_invalid_arguments_never_open_a_device(self):
        for args in ([], ['--decode-id', 'xyz'],
                     ['--decode-id', 'ecda109544', '/dev/fake'],
                     ['--decode-id', 'ecda109544', '-m', 'asolid']):
            with self.subTest(args=args), patch('sys.argv', ['veryflashy', *args]):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()
                self.assertEqual(exc.exception.code, 2)
        self.open.assert_not_called()
        self.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
