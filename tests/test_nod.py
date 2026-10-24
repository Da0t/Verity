"""Compile pure gesture logic on hosts with a C++ compiler; no MCU needed."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class NodTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'Host C++ compiler unavailable')
    def test_nod_logic(self):
        header = (Path(__file__).resolve().parents[1]/'firmware/CircuitGlasses/NodDetector.h').as_posix()
        source = '''
#include "HEADER"
#include <assert.h>
int main() {
 NodDetector n;
 assert(!n.update(0, 0));
 assert(!n.update(20, 100));
 assert(n.update(0, 400));
 assert(!n.update(20, 500));
 assert(!n.update(0, 700));
 assert(!n.update(0, 2500));
 assert(!n.update(20, 2600));
 assert(!n.update(0, 2650)); // too fast
 assert(!n.update(0, 3000));
 assert(!n.update(20, 3100));
 assert(!n.update(20, 5000)); // held too long
 assert(!n.update(0, 5100));
 assert(!n.update(20, 5200));
 assert(n.update(0, 5500));
}
'''.replace('HEADER', header)
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'nod.cpp'; binary=Path(tmp)/'nod'
            src.write_text(source)
            subprocess.run(['g++','-std=c++11',str(src),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)
