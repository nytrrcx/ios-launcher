#!/usr/bin/env python3
"""Run the actual game callback implementation against Apple's Objective-C runtime."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='geode-timing-') as directory:
    binary = str(Path(directory) / 'timing-tests')
    subprocess.run([
        'xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-parameter', '-mmacosx-version-min=13.0',
        '-I' + str(root / 'tests/timing_runtime/stubs'), '-I' + str(root / 'src'),
        str(root / 'src/ProMotionTiming.m'), str(root / 'tests/timing_runtime/main.m'),
        '-framework', 'Foundation', '-o', binary,
    ], check=True)
    subprocess.run([binary], check=True)
    subprocess.run([binary, '--invalid-signature'], check=True)
