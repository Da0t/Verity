"""Host tests for wire parsing, freshness, restart fencing and bounded delivery."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

class EspNowTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'Host C++ compiler unavailable')
    def test_protocol_and_lifecycle(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'link-test'
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I', str(root/'firmware/libraries/VerityLink/src'),
                str(root/'firmware/tests/link_test.cpp'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
