"""Regression for duplicate socket rows during concurrent /proc TCP-table reads."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('memory_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ConnectionCountTests(unittest.TestCase):
    def test_duplicate_rows_do_not_invent_connections(self):
        # The same established socket can occur twice while unrelated sockets
        # change in the kernel's non-atomic proc table walk.
        row = '0: 0100007F:480B 0200007F:9000 01 0:0 00:0 0 0 0 12345'
        other = '1: 0100007F:480B 0300007F:9001 01 0:0 00:0 0 0 0 12346'
        closing = '2: 0100007F:480B 0400007F:9002 06 0:0 00:0 0 0 0 0'
        upstream = '3: 0100007F:9003 0100007F:238D 01 0:0 00:0 0 0 0 12347'
        tcp = '\n'.join(['header', row, other, row, closing, upstream])
        with patch.object(runner.Path, 'read_text', side_effect=[tcp, 'header\n']):
            self.assertEqual(runner.established_connections(), 2)

    def test_ipv6_and_unowned_sockets_stay_distinct(self):
        # Zero inodes can occur before acceptance: preserve distinct endpoints.
        tcp = 'header\n0: 0100007F:480B 0200007F:9000 01 0:0 00:0 0 0 0 0\n'
        tcp += '1: 0100007F:480B 0300007F:9001 01 0:0 00:0 0 0 0 0\n'
        tcp6 = 'header\n0: 0000000000000000FFFF00000100007F:480B 0000000000000000FFFF00000200007F:9002 01 0:0 00:0 0 0 0 12348\n'
        with patch.object(runner.Path, 'read_text', side_effect=[tcp, tcp6]):
            self.assertEqual(runner.established_connections(), 3)


if __name__ == '__main__':
    unittest.main()
