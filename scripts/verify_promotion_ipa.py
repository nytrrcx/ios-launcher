#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import plistlib
import subprocess
import sys
import zipfile

packages = Path(sys.argv[1])
ipas = list(packages.glob('*.ipa'))
if len(ipas) != 1:
    raise SystemExit(f'Expected one IPA, found {len(ipas)}')
ipa = ipas[0]
with zipfile.ZipFile(ipa) as archive:
    base = 'Payload/Geode.app/'
    for name in ('ANGLEGLKit', 'libEGL', 'libGLESv2'):
        prefix = base + 'Frameworks/' + name + '.framework/'
        binary = archive.read(prefix + name)
        if binary[:4] != b'\xcf\xfa\xed\xfe':
            raise SystemExit(f'{name} is not a thin 64-bit Mach-O')
        plistlib.loads(archive.read(prefix + 'Info.plist'))
        if name == 'ANGLEGLKit' and b'GCGeodeStencilFixVersion' not in binary:
            raise SystemExit('IPA contains an unpatched renderer')
    archive.read(base + 'Frameworks/CAHighFPS.dylib')
    info = plistlib.loads(archive.read(base + 'Info.plist'))
    if not info.get('CADisableMinimumFrameDurationOnPhone'):
        raise SystemExit('Launcher does not opt into ProMotion')
provenance = {
    'launcher_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'angle_commit': subprocess.check_output(['git', '-C', 'vendor/ANGLEGLKit', 'rev-parse', 'HEAD'], text=True).strip(),
    'stencil_fix_version': 1,
    'jitless_storage': 'derived-from-game-mach-o',
    'ipa_sha256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
    'device_tested': False,
}
(packages / 'promotion-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
print('Verified IPA contents:', ipa.name)
