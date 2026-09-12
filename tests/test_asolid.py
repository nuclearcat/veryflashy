import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from py_sg import SCSIError

from veryflashy import asolid
from veryflashy import __main__ as cli


CAPTURE = json.loads((Path(__file__).parent / 'fixtures' / 'asolid.json').read_text())
INQUIRY, INFO, IDS = (bytes.fromhex(CAPTURE[name]['data_hex'])
                      for name in ('inquiry', 'firmware_info', 'nand_ids'))
DETAILS = [bytes.fromhex(CAPTURE[name]['data_hex'])
           for name in ('register_c1c0', 'register_c1d3', 'protocol')]
PROTOCOL = DETAILS[-1]


class ASolidTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.read = self.enterContext(patch('veryflashy.asolid.sgread'))

    def test_capture_replay(self):
        self.read.side_effect = [INQUIRY, INFO, IDS, *DETAILS]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e83012'))
        self.assertEqual(self.read.call_args_list, [
            unittest.mock.call(7, bytes.fromhex(CAPTURE[name]['cdb']), size)
            for name, size in (('inquiry', 96), ('firmware_info', 512), ('nand_ids', 512),
                               ('register_c1c0', 1), ('register_c1d3', 1), ('protocol', 4096))
        ])
        output = self.output.getvalue()
        self.assertIn('18002SM3U_4A1005_Oct 25 2024', output)
        self.assertIn('IS918-EN (MPTool register heuristic)', output)
        self.assertIn('Recorded MPTool version: 241108A', output)
        self.assertIn('2025-09-21 18:20:18', output)
        self.assertIn('236480 MiB (247967252480 bytes)', output)
        self.assertIn('Recorded chip-enable count (CE): 2', output)
        self.assertIn('Recorded NAND LUNs per CE: 1', output)
        self.assertIn('Configured die count (CE x LUNs per CE): 2', output)
        self.assertIn('Estimated raw NAND capacity: 256 GiB', output)
        self.assertIn('25.0625 GiB (9.79% of raw; 26910654464 bytes)', output)
        self.assertIn('Independent NAND channels: unknown', output)
        self.assertIn('slot 0): 2c-d3-08-32-e8-30-12', output)
        self.assertIn('slot 2): 2c-d3-08-32-e8-30-12', output)
        self.assertEqual(output.count('Flash ID (slot'), 2)

    def test_other_vendor_and_short_inquiry_never_get_vendor_commands(self):
        for inquiry in (b'', INQUIRY[:40], INQUIRY.replace(b'ASolid', b'Phison')):
            with self.subTest(inquiry=inquiry):
                self.read.reset_mock()
                self.read.side_effect = [inquiry]
                with self.assertRaises(NotImplementedError):
                    asolid.probe(7)
                self.assertEqual(self.read.call_count, 1)

    def test_inquiry_error_allows_other_detectors(self):
        self.read.side_effect = SCSIError(2, 0, 8, b'\x70', b'')
        with self.assertRaises(NotImplementedError):
            asolid.probe(7)
        self.assertEqual(self.read.call_count, 1)

    def test_unknown_firmware_is_reported_without_nand_commands(self):
        for prefix in (b'18002B', b'18002M', b'18002D', b'13008S', b'99999S'):
            with self.subTest(prefix=prefix):
                self.read.reset_mock()
                self.read.side_effect = [INQUIRY, prefix + INFO[6:]]
                self.assertIsNone(asolid.probe(7))
                self.assertEqual(self.read.call_count, 2)

    def test_bad_info_stops_after_recognition(self):
        for info in (b'', INFO[:31], b'\0' * 32, b'18002S\xff' + b'\0' * 25):
            with self.subTest(info=info):
                self.read.reset_mock()
                self.read.side_effect = [INQUIRY, info]
                with self.assertRaises(RuntimeError):
                    asolid.probe(7)
                self.assertEqual(self.read.call_count, 2)

    def test_zero_padded_firmware_response(self):
        self.read.side_effect = [INQUIRY, INFO.ljust(512, b'\0'), IDS, *DETAILS]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e83012'))

    def test_id_in_later_slot_and_ff_padding(self):
        data = b'\xff' * 8 + b'\0' * 8 + IDS[16:24] + b'\xff' * 104
        self.read.side_effect = [INQUIRY, INFO, data, *DETAILS]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e83012'))
        self.assertEqual(self.output.getvalue().count('Flash ID (slot'), 1)
        self.assertIn('slot 2)', self.output.getvalue())
        # A single returned ID is not evidence of a single physical die.
        self.assertIn('Configured die count (CE x LUNs per CE): 2', self.output.getvalue())

    def test_invalid_nand_response(self):
        for ids in (b'', IDS[:127], b'\0' * 512, b'\xff' * 512):
            with self.subTest(ids=ids):
                self.read.side_effect = [INQUIRY, INFO, ids]
                with self.assertRaises(RuntimeError):
                    asolid.probe(7)

    def test_vendor_command_errors_are_not_swallowed(self):
        for replies in ([INQUIRY], [INQUIRY, INFO]):
            with self.subTest(reply_count=len(replies)):
                error = SCSIError(2, 0, 8, b'\x70', b'')
                self.read.side_effect = replies + [error]
                with self.assertRaises(SCSIError):
                    asolid.probe(7)

    def test_model_selection_matches_mptool(self):
        for c1c0, c1d3, model in ((0, 0, 'IS918-EN'), (0xa1, 0, 'IS818-EN'),
                                  (0, 0x33, 'IS918-ENX'), (0xa1, 0x33, 'IS918-ENX')):
            with self.subTest(model=model, c1c0=c1c0):
                self.output.seek(0)
                self.output.truncate()
                self.read.side_effect = [INQUIRY, INFO, IDS, bytes([c1c0]), bytes([c1d3]), PROTOCOL]
                asolid.probe(7)
                self.assertIn(f'{model} (MPTool register heuristic)', self.output.getvalue())

    def test_optional_read_failures_preserve_nand_decoding(self):
        error = SCSIError(2, 0, 8, b'\x70', b'')
        for details in ([error, PROTOCOL], [b'', PROTOCOL], [b'\0', error, PROTOCOL],
                        [b'\0', b'\0', error], [b'\0', b'\0', b'']):
            with self.subTest(details=details[:2]):
                self.output.seek(0)
                self.output.truncate()
                self.read.side_effect = [INQUIRY, INFO, IDS, *details]
                self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e83012'))
                self.assertIn('unavailable:', self.output.getvalue())


class ProtocolTests(unittest.TestCase):
    def test_captured_configuration(self):
        self.assertEqual(asolid.decode_protocol(PROTOCOL), {
            'usb_id': '0951:1666', 'manufacturer': 'Kingston', 'product': 'DataTraveler 3.0',
            'serial': '000000000000000000000001', 'firmware': '18002SM3U_4A1005',
            'capacity_mib': 236480, 'mp_version': '241108A',
            'mp_timestamp': '2025-09-21 18:20:18',
            'ce_count': 2, 'luns_per_ce': 1, 'configured_die_count': 2,
        })

    def test_short_wrong_tag_and_wrong_descriptor(self):
        for data in (PROTOCOL[:4095], PROTOCOL + b'\0', b'\0' * 4096,
                     PROTOCOL.replace(b'PROTOCOL', b'UNKNOWN!'), b'\0\0' + PROTOCOL[2:]):
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    asolid.decode_protocol(data)

    def test_invalid_string_pointers_and_lengths(self):
        for entry in ('ffff0022', '01ff0022', '007d0001', '007d0021', '007d0020', '007d0100'):
            with self.subTest(entry=entry):
                data = bytearray(PROTOCOL)
                data[0x214:0x218] = bytes.fromhex(entry)
                with self.assertRaises(ValueError):
                    asolid.decode_protocol(data)

    def test_usb_strings_are_utf16_and_reject_controls_and_bad_encoding(self):
        data = bytearray(PROTOCOL)
        data[0xbf:0xc1] = '北'.encode('utf-16le')
        self.assertEqual(asolid.decode_protocol(data)['manufacturer'], '北ingston')
        for bad in (b'\x1b\x00', b'\x00\xd8'):
            data[0xbf:0xc1] = bad
            with self.assertRaises(ValueError):
                asolid.decode_protocol(data)

    def test_nonprintable_ascii_rejected(self):
        data = bytearray(PROTOCOL)
        data[0x6a6] = 0x1b
        with self.assertRaises(ValueError):
            asolid.decode_protocol(data)

    def test_absent_fields_are_not_invented(self):
        for fill in (0, 255):
            data = bytearray(PROTOCOL)
            for offset, length in ((0x214, 12), (0x68d, 16), (0x69d, 4),
                                   (0x6a5, 42), (0x6fd, 2)):
                data[offset:offset + length] = bytes([fill]) * length
            info = asolid.decode_protocol(data)
            self.assertTrue(all(value is None for key, value in info.items() if key != 'usb_id'))

    def test_missing_or_invalid_counts_do_not_produce_die_count(self):
        for offset in (0x6fd, 0x6fe):
            for count in (0, 17, 255):
                with self.subTest(offset=offset, count=count):
                    data = bytearray(PROTOCOL)
                    data[offset] = count
                    self.assertIsNone(asolid.decode_protocol(data)['configured_die_count'])


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.info = asolid.decode_protocol(PROTOCOL)
        self.ids = [IDS[:7]]

    def test_unknown_mixed_and_package_densities_do_not_produce_estimate(self):
        candidates = ([], [{'capacity_bytes': 128 * 2**30}],
                      [{'die_capacity_bytes': 128 * 2**30}, {}],
                      [{'die_capacity_bytes': 128 * 2**30}, {'die_capacity_bytes': 64 * 2**30}])
        for matches in candidates:
            with self.subTest(matches=matches):
                self.output.seek(0)
                self.output.truncate()
                with patch('veryflashy.asolid.nand.decode', return_value={'candidates': matches}):
                    asolid._print_topology(self.info, self.ids)
                self.assertIn('estimate unavailable:', self.output.getvalue())
                self.assertNotIn('Estimated raw NAND capacity:', self.output.getvalue())

    def test_mixed_ids_are_not_assumed_to_have_the_first_ids_density(self):
        asolid._print_topology(self.info, [IDS[:7], bytes.fromhex('ecda109544')])
        self.assertIn('missing or mixed NAND IDs', self.output.getvalue())
        self.assertNotIn('Estimated raw NAND capacity:', self.output.getvalue())

    def test_missing_topology_and_inconsistent_capacity(self):
        self.info['configured_die_count'] = None
        asolid._print_topology(self.info, self.ids)
        self.assertIn('missing recorded topology or capacity', self.output.getvalue())
        self.info['configured_die_count'] = 1
        asolid._print_topology(self.info, self.ids)
        self.assertIn('inferred raw capacity is below programmed capacity', self.output.getvalue())
        self.assertNotIn('Estimated raw-to-user capacity gap:', self.output.getvalue())

    def test_equal_capacity_is_a_valid_zero_gap(self):
        self.info['capacity_mib'] = 256 * 1024
        asolid._print_topology(self.info, self.ids)
        self.assertIn('0 GiB (0.00% of raw; 0 bytes)', self.output.getvalue())


class CLITests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(patch('veryflashy.__main__.os.open', return_value=7))
        self.enterContext(patch('veryflashy.__main__.sgread', side_effect=[
            bytes.fromhex('0000000f00000200'),
            bytes.fromhex('000000080000001000000200'),
        ]))
        self.read = self.enterContext(patch('veryflashy.asolid.sgread'))
        self.others = [self.enterContext(patch.object(module, 'probe'))
                       for name, module in cli.models.items() if name != 'asolid']

    def test_auto_detection_stops_at_asolid(self):
        self.read.side_effect = [INQUIRY, INFO, IDS, *DETAILS]
        with patch('sys.argv', ['veryflashy', '/dev/fake']):
            cli.main()
        for probe in self.others:
            probe.assert_not_called()

    def test_explicit_asolid(self):
        self.read.side_effect = [INQUIRY, INFO, IDS, *DETAILS]
        with patch('sys.argv', ['veryflashy', '-m', 'asolid', '/dev/fake']):
            cli.main()
        self.assertIn('2c-d3-08-32-e8-30-12', self.output.getvalue())
        for probe in self.others:
            probe.assert_not_called()

    def test_unknown_asolid_firmware_does_not_probe_other_vendors(self):
        self.read.side_effect = [INQUIRY, b'18002B' + INFO[6:]]
        with patch('sys.argv', ['veryflashy', '/dev/fake']):
            cli.main()
        self.assertEqual(self.read.call_count, 2)
        for probe in self.others:
            probe.assert_not_called()

    def test_non_asolid_continues_existing_detection(self):
        self.read.side_effect = [INQUIRY.replace(b'ASolid', b'Phison')]
        self.others[0].return_value = b'\x89\xd7\xd5\x3e\x78\0'
        with patch('sys.argv', ['veryflashy', '/dev/fake']):
            cli.main()
        self.others[0].assert_called_once_with(7)
        self.assertEqual(self.read.call_count, 1)
        for probe in self.others[1:]:
            probe.assert_not_called()

    def test_lookup_uses_offline_database(self):
        self.read.side_effect = [INQUIRY, INFO, IDS, *DETAILS]
        with patch('sys.argv', ['veryflashy', '-l', '/dev/fake']):
            cli.main()
        self.assertIn('Manufacturer: Micron', self.output.getvalue())
        self.assertIn('MT29F1T08EBLCH', self.output.getvalue())
        self.assertIn('B58R | 232-layer TLC | 128 GiB raw/die', self.output.getvalue())
        self.assertIn('decode for 2c-d3-08-32-e8-30-12', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
