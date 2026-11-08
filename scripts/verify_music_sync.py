"""Verify the separate iOS music-sync mod and record build provenance."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

directory = Path(sys.argv[1])
mods = list(directory.glob('*.geode'))
if len(mods) != 1:
    raise SystemExit('Expected one music-sync .geode package')
package = mods[0]
with zipfile.ZipFile(package) as archive:
    if archive.testzip() is not None:
        raise SystemExit('Corrupt mod archive')
    metadata = json.loads(archive.read('mod.json'))
    assert metadata['id'] == 'nytrrcx.promotion_music_sync'
    assert metadata['geode'] == '5.11.2'
    assert metadata['gd']['ios'] == '2.2081'
    assert not metadata.get('requires-patching', False), 'Mod must support JIT-less hooks'
    binary = archive.read('nytrrcx.promotion_music_sync.ios.dylib')
    assert struct.unpack_from('<II', binary) == (0xfeedfacf, 0x0100000c), 'Expected thin arm64 Mach-O'
    assert b'ProMotion Music Sync: song corrected' in binary
    assert b'ProMotionMusicSyncLayer' in binary
    cursor = 32
    imports = []
    for _ in range(struct.unpack_from('<I', binary, 16)[0]):
        command, length = struct.unpack_from('<II', binary, cursor)
        if command in (0xc, 0x80000018, 0x8000001f):
            offset = struct.unpack_from('<I', binary, cursor + 8)[0]
            imports.append(binary[cursor + offset:cursor + length].split(b'\0')[0].decode())
        cursor += length
    assert not any('/OpenGLES.framework/' in name for name in imports), 'Audio mod must not load native EAGL into ANGLE'
    assert any(name.endswith('/Geode.ios.dylib') for name in imports), 'Expected native Geode dependency'
    assert not any('click_between_frames' in name for name in archive.namelist()), 'Do not replace CBF'
provenance = {
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'geode_sdk': '5.11.2',
    'gd_ios_sdk_version': '2.2081',
    'bindings_commit': '28b0e0d870f3f230a85a8c47a00093d37ebb1124',
    'native_opengles_dependency': False,
    'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
    'device_tested': False,
}
(directory / 'music-sync-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
print('Verified iOS Music Sync:', package.name)
