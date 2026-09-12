import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from py_sg import SCSIError

from veryflashy import asolid
from veryflashy import __main__ as cli


CAPTURE = json.loads((Path(__file__).parent / 'fixtures' / 'asolid.json').read_text())
INQUIRY, INFO, IDS = (bytes.fromhex(CAPTURE[name]['data_hex'])
                      for name in ('inquiry', 'firmware_info', 'nand_ids'))


class ASolidTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.read = self.enterContext(patch('veryflashy.asolid.sgread'))

    def test_capture_replay(self):
        self.read.side_effect = [INQUIRY, INFO, IDS]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e830'))
        self.assertEqual(self.read.call_args_list, [
            unittest.mock.call(7, bytes.fromhex(CAPTURE[name]['cdb']), size)
            for name, size in (('inquiry', 96), ('firmware_info', 512), ('nand_ids', 512))
        ])
        output = self.output.getvalue()
        self.assertIn('18002SM3U_4A1005_Oct 25 2024', output)
        self.assertIn('exact chip model unknown', output)
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
        self.read.side_effect = [INQUIRY, INFO.ljust(512, b'\0'), IDS]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e830'))

    def test_id_in_later_slot_and_ff_padding(self):
        data = b'\xff' * 8 + b'\0' * 8 + IDS[16:24] + b'\xff' * 104
        self.read.side_effect = [INQUIRY, INFO, data]
        self.assertEqual(asolid.probe(7), bytes.fromhex('2cd30832e830'))
        self.assertEqual(self.output.getvalue().count('Flash ID (slot'), 1)
        self.assertIn('slot 2)', self.output.getvalue())

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
        self.read.side_effect = [INQUIRY, INFO, IDS]
        with patch('sys.argv', ['veryflashy', '/dev/fake']):
            cli.main()
        for probe in self.others:
            probe.assert_not_called()

    def test_explicit_asolid(self):
        self.read.side_effect = [INQUIRY, INFO, IDS]
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

    def test_unavailable_lookup_fails_before_device_access(self):
        errors = io.StringIO()
        with patch.dict(sys.modules, {'veryflashy.fdnext': None}), \
                patch('sys.argv', ['veryflashy', '-l', '/dev/fake']), \
                contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as exc:
                cli.main()
        self.assertEqual(exc.exception.code, 2)
        self.assertIn('optional veryflashy.fdnext module', errors.getvalue())
        cli.os.open.assert_not_called()
        self.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
