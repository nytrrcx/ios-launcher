#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import plistlib
import struct
import subprocess
import sys
import zipfile


def dependencies(binary):
    result = []
    cursor = 32
    for _ in range(struct.unpack_from('<I', binary, 16)[0]):
        kind, length = struct.unpack_from('<II', binary, cursor)
        if kind in (0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023):
            offset = struct.unpack_from('<I', binary, cursor + 8)[0]
            result.append(binary[cursor + offset:binary.index(b'\0', cursor + offset, cursor + length)].decode())
        cursor += length
    return result

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
        if name == 'ANGLEGLKit':
            if b'GCGeodeEGLDirectVersion' not in binary:
                raise SystemExit('IPA renderer does not include direct EGL binding')
            imports = dependencies(binary)
            if any('/libEGL.framework/' in path or '/OpenGLES.framework/' in path for path in imports):
                raise SystemExit('Renderer still depends on an executable-path EGL loader or native OpenGLES')
            if not any('/libGLESv2.framework/' in path for path in imports):
                raise SystemExit('Renderer does not link directly to ANGLE')
    if any(name.endswith('/CAHighFPS.dylib') for name in archive.namelist()):
        raise SystemExit('IPA still contains the timing library that crashed during preload')
    launcher = archive.read(base + 'Geode')
    if b'GCInstallGameProMotionTiming' not in launcher or b'Game callback timing installed' not in launcher:
        raise SystemExit('Launcher does not include explicit game callback timing')
    info = plistlib.loads(archive.read(base + 'Info.plist'))
    if not info.get('CADisableMinimumFrameDurationOnPhone'):
        raise SystemExit('Launcher does not opt into ProMotion')
provenance = {
    'launcher_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'angle_commit': subprocess.check_output(['git', '-C', 'vendor/ANGLEGLKit', 'rev-parse', 'HEAD'], text=True).strip(),
    'stencil_fix_version': 1,
    'jitless_storage': 'derived-from-game-mach-o',
    'egl_binding': 'direct-libglesv2',
    'timing': 'launcher-game-callback',
    'ipa_sha256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
    'device_tested': False,
}
(packages / 'promotion-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
print('Verified IPA contents:', ipa.name)
