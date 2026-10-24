"""Host compile of the shared gesture detector tests (not an MCU build)."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class NodTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'Host C++ compiler unavailable')
    def test_nod_logic(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'nod'
            subprocess.run(['g++','-std=c++17','-I',str(root/'firmware/CircuitGlasses'),
                str(root/'firmware/tests/nod_detector_test.cpp'),'-o',str(binary)],
                check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)
