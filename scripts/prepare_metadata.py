#!/usr/bin/env python3
"""Stamp this fork build; keep game-download credentials out of Actions logs."""
from pathlib import Path
import os
import subprocess

path = Path('src/main.m')
revision = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
path.write_text(path.read_text().replace('__COMMIT_HASH__', revision + '-promotion'))
# These optional repository secrets are never printed or interpolated into shell code.
path = Path('src/RootViewController.m')
text = path.read_text()
for marker, variable in (('__DOWNLOAD_LINK__', 'GD_DOWNLOAD'), ('__KEY_PART1__', 'KEYONE'), ('__KEY_PART2__', 'KEYTWO')):
    value = os.environ.get(variable)
    if value:
        text = text.replace(marker, value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r'))
path.write_text(text)
