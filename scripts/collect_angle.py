#!/usr/bin/env python3
"""Collect the rebuilt wrapper, never the old prebuilt wrapper in Resources."""
from pathlib import Path
import shutil
import sys

search, destination = map(Path, sys.argv[1:])
candidates = [p for p in search.rglob('ANGLEGLKit.framework')
              if (p / 'ANGLEGLKit').is_file() and (p / 'Info.plist').is_file()]
if not candidates:
    raise SystemExit('The ANGLEGLKit framework build did not produce a complete bundle')
source = sorted(candidates, key=lambda p: (len(p.parts), str(p)))[0]
if b'GCGeodeStencilFixVersion' not in (source / 'ANGLEGLKit').read_bytes():
    raise SystemExit('Built renderer is missing the stencil-fix marker')
shutil.copytree(source, destination / 'ANGLEGLKit.framework', dirs_exist_ok=True)
print('Collected renderer:', source)
