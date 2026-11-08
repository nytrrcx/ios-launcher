"""Host regression tests; no Apple SDK needed. Run python3 -m unittest discover -s tests -v."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GLES = b'/System/Library/Frameworks/OpenGLES.framework/OpenGLES'
FRAMEWORKS = b'/private/var/mobile/Containers/Data/Application/test/Applications/GeometryJump.app/Frameworks'
TARGET = FRAMEWORKS + b'/ANGLEGLKit.framework/ANGLEGLKit'


def command(path, kind=0xc):
    length = (24 + len(path) + 1 + 7) & ~7
    return struct.pack('<6I', kind, length, 24, 42, 0x10000, 0x10000) + (path + b'\0').ljust(length - 24, b'\0')


def image(paths=(GLES,), section_offset=2048, trailing=True):
    section = struct.pack('<16s16sQQ8I', b'__text', b'__TEXT', 0x100000000 + section_offset,
                          32, section_offset, 2, 0, 0, 0, 0, 0, 0)
    segment = struct.pack('<II16sQQQQ4I', 0x19, 152, b'__TEXT', 0x100000000, 4096,
                          0, 4096, 5, 5, 1, 0) + section
    cmds = segment + b''.join(command(p) for p in paths)
    if trailing:
        cmds += struct.pack('<II16s', 0x1b, 24, b'preserved-uuid!!')
    header = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 6, 1 + len(paths) + trailing, len(cmds), 0, 0)
    data = bytearray((header + cmds).ljust(4096, b'\0'))
    data[section_offset:section_offset + 32] = b'X' * 32
    return data


def commands(data):
    offset = 32
    result = []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        kind, length = struct.unpack_from('<II', data, offset)
        result.append((kind, data[offset:offset + length]))
        offset += length
    return result


def paths(data):
    return [bytes(c[24:]).split(b'\0')[0] for kind, c in commands(data) if kind == 0xc]


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name) / 'renderer.so'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT / 'src/PromotionMachO.c'), '-o', str(lib)], check=True)
        cls.library = ctypes.CDLL(str(lib))
        cls.patch = cls.library.GCPatchRenderer
        cls.patch.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_bool]
        cls.patch.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def apply(self, data, enabled=True, directory=FRAMEWORKS):
        buffer = (ctypes.c_ubyte * len(data)).from_buffer(data)
        return self.patch(buffer, len(data), directory, enabled)

    def test_enable_preserves_payload_and_other_commands(self):
        data = image()
        uuid = commands(data)[-1]
        self.assertEqual(self.apply(data), 1)
        self.assertEqual(paths(data), [TARGET])
        self.assertEqual(commands(data)[-1], uuid)
        self.assertEqual(data[2048:2080], b'X' * 32)
        self.assertEqual(struct.unpack_from('<I', data, 12)[0], 6)  # Keep file type.

    def test_idempotent(self):
        data = image()
        self.apply(data)
        expected = data[:]
        self.assertEqual(self.apply(data), 0)
        self.assertEqual(data, expected)

    def test_disable_restores_native_dependency(self):
        data = image()
        self.apply(data)
        self.assertEqual(self.apply(data, False), 1)
        self.assertEqual(paths(data), [GLES])
        self.assertEqual(self.apply(data, False), 0)

    def test_relocation_updates_old_container_path(self):
        data = image()
        self.apply(data)
        self.assertEqual(self.apply(data, directory=FRAMEWORKS + b'-new'), 1)
        self.assertEqual(paths(data), [FRAMEWORKS + b'-new/ANGLEGLKit.framework/ANGLEGLKit'])

    def test_egl_dependencies_relocated_together(self):
        data = image((b'@rpath/libEGL.framework/libEGL', b'@rpath/libGLESv2.framework/libGLESv2'))
        self.assertEqual(self.apply(data), 1)
        self.assertEqual(paths(data), [FRAMEWORKS + b'/libEGL.framework/libEGL', FRAMEWORKS + b'/libGLESv2.framework/libGLESv2'])

    def test_unrelated_and_id_dylib_unchanged(self):
        data = image((b'/usr/lib/libSystem.B.dylib',))
        expected = data[:]
        self.assertEqual(self.apply(data), 0)
        self.assertEqual(data, expected)
        data = image()
        struct.pack_into('<I', data, 32 + 152, 0xd)  # LC_ID_DYLIB is not an import.
        self.assertEqual(self.apply(data), 0)

    def test_weak_reexport_lazy_upward_imports(self):
        for kind in (0x80000018, 0x8000001f, 0x20, 0x80000023):
            data = image()
            struct.pack_into('<I', data, 184, kind)
            self.assertEqual(self.apply(data), 1)
            self.assertIn(TARGET, data)

    def test_no_space_rejected_without_writing(self):
        data = image(section_offset=320)
        expected = data[:]
        self.assertEqual(self.apply(data), -2)
        self.assertEqual(data, expected)

    def test_nonzero_header_padding_rejected(self):
        data = image()
        end = 32 + struct.unpack_from('<I', data, 20)[0]
        data[end] = 99
        expected = data[:]
        self.assertEqual(self.apply(data), -2)
        self.assertEqual(data, expected)

    def test_invalid_commands_and_strings_rejected(self):
        for offset, value in ((20, 999999), (16, 999999), (188, 0), (192, 99999), (192, 0)):
            data = image()
            struct.pack_into('<I', data, offset, value)
            expected = data[:]
            self.assertEqual(self.apply(data), -1)
            self.assertEqual(data, expected)
        data = image()
        length = struct.unpack_from('<I', data, 188)[0]
        data[208:184 + length] = b'A' * (length - 24)
        self.assertEqual(self.apply(data), -1)

    def test_truncations_rejected(self):
        for length in (0, 7, 31, 50, 180, 250):
            self.assertEqual(self.apply(image()[:length]), -1)

    def test_fat32_and_fat64(self):
        for wide in (False, True):
            data = bytearray(struct.pack('>II', 0xcafebabf if wide else 0xcafebabe, 1))
            data += struct.pack('>IIQQII' if wide else '>5I', 0x0100000c, 0, 4096, 4096, 12, *([0] if wide else []))
            data = data.ljust(4096, b'\0') + image()
            self.assertEqual(self.apply(data), 1)
            self.assertEqual(paths(data[4096:]), [TARGET])
            self.assertEqual(self.apply(data, False), 1)
            self.assertEqual(paths(data[4096:]), [GLES])

    def test_bad_fat_tables_rejected(self):
        for offset, size in ((0, 4096), (4096, 999999), (999999, 4096)):
            data = bytearray(struct.pack('>7I', 0xcafebabe, 1, 0x0100000c, 0, offset, size, 12)).ljust(4096, b'\0') + image()
            self.assertEqual(self.apply(data), -1)

    def test_overlapping_fat_slices_rejected(self):
        arch = struct.pack('>5I', 0x0100000c, 0, 4096, 4096, 12)
        data = bytearray(struct.pack('>II', 0xcafebabe, 2) + arch + arch).ljust(4096, b'\0') + image()
        self.assertEqual(self.apply(data), -1)

    def test_second_enable_after_disable_does_not_grow(self):
        data = image()
        self.apply(data)
        size = struct.unpack_from('<I', data, 20)[0]
        self.apply(data, False)
        self.apply(data)
        self.assertEqual(struct.unpack_from('<I', data, 20)[0], size)


if __name__ == '__main__':
    unittest.main()
