"""Native frame-cap rewriting against synthetic Objective-C Mach-O metadata."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x100000000
CAP60 = bytes.fromhex('1ff000f18807805214b0889a')
CAP120 = bytes.fromhex('1fe001f1080f805214b0889a')
INTERVAL = bytes.fromhex('00102e1e0018281e00c0221e080040f9013140f9')


def vm(offset):
    return BASE + (offset if offset < 0x400 else 0x5000 + offset - 0x400)


def image(relative=False, indirect=False):
    def segment(name, address, offset, size, protection, section_name, section_offset, section_size):
        section = struct.pack('<16s16sQQ8I', section_name, name, vm(section_offset),
                              section_size, section_offset, 2, 0, 0, 0, 0, 0, 0)
        return struct.pack('<II16sQQQQ4I', 0x19, 152, name, address, size, offset,
                           size, protection, protection, 1, 0) + section

    commands = segment(b'__TEXT', BASE, 0, 0x400, 5, b'__text', 0x200, 0x100)
    commands += segment(b'__DATA', BASE + 0x5000, 0x400, 0x800, 3, b'__objc_classlist', 0x400, 8)
    header = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 6, 2, len(commands), 0, 0)
    data = bytearray((header + commands).ljust(4096, b'\0'))
    data[0x200:0x300] = bytes.fromhex('1f2003d5') * 64  # NOP padding, not game code.
    data[0x210:0x21c] = CAP60
    data[0x220:0x224] = bytes.fromhex('8802229e')  # scvtf s8,x20
    data[0x240:0x254] = INTERVAL
    struct.pack_into('<Q', data, 0x400, vm(0x440))
    struct.pack_into('<Q', data, 0x460, vm(0x480) | 3)  # class data flags
    struct.pack_into('<Q', data, 0x498, vm(0x4c0))
    struct.pack_into('<Q', data, 0x4a0, vm(0x500))
    data[0x4c0:0x4d1] = b'CCDirectorCaller\0'
    data[0x580:0x58e] = b'startMainLoop\0'
    data[0x5a0:0x5a9] = b'doCaller:\0'
    data[0x5b0:0x5b7] = b'v16@0:8'
    struct.pack_into('<I', data, 0x500, (0x8000000c | (0 if indirect else 0x40000000)) if relative else 24)
    struct.pack_into('<I', data, 0x504, 2)
    for i, (name, imp) in enumerate(((0x580, 0x200), (0x5a0, 0x280))):
        if relative:
            entry = 0x508 + 12 * i
            selector = 0x5c0 + i * 8 if indirect else name
            if indirect:
                struct.pack_into('<Q', data, selector, vm(name))
            struct.pack_into('<3i', data, entry, vm(selector) - vm(entry),
                             vm(0x5b0) - vm(entry + 4), vm(imp) - vm(entry + 8))
        else:
            struct.pack_into('<3Q', data, 0x508 + 24 * i, vm(name), vm(0x5b0), vm(imp))
    return data


class NativeTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name) / 'game-timing.so'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT / 'src/GameTimingMachO.c'), '-o', str(lib)], check=True)
        cls.library = ctypes.CDLL(str(lib))
        cls.patch = cls.library.GCConfigureNativeGameTiming
        cls.patch.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_bool]
        cls.patch.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def apply(self, data, enabled=True):
        return self.patch((ctypes.c_ubyte * len(data)).from_buffer(data), len(data), enabled)

    def test_native_setup_uses_120_for_both_consumers(self):
        data = image()
        original = data[:]
        self.assertEqual(self.apply(data), 1)
        self.assertEqual(data[0x210:0x21c], CAP120)
        self.assertEqual(data[:0x210], original[:0x210])
        self.assertEqual(data[0x21c:], original[0x21c:])
        # Decode the immediates which feed the native min(screenFPS, cap).
        compare, move = struct.unpack_from('<2I', data, 0x210)
        self.assertEqual((compare >> 10) & 0xfff, 120)
        self.assertEqual((move >> 5) & 0xffff, 120)
        self.assertEqual(data[0x240:0x254], INTERVAL)  # Native 1/fps stays intact.

    def test_rollback_and_idempotence(self):
        data = image()
        original = data[:]
        self.assertEqual(self.apply(data, False), 0)
        self.assertEqual(self.apply(data), 1)
        promoted = data[:]
        self.assertEqual(self.apply(data), 0)
        self.assertEqual(data, promoted)
        self.assertEqual(self.apply(data, False), 1)
        self.assertEqual(data, original)

    def test_relative_methods_and_indirect_selectors(self):
        for indirect in (False, True):
            data = image(relative=True, indirect=indirect)
            self.assertEqual(self.apply(data), 1)
            self.assertEqual(data[0x210:0x21c], CAP120)
            self.assertEqual(self.apply(data, False), 1)

    def test_unknown_class_method_or_cap_fails_without_writes(self):
        for offset in (0x4c0, 0x580, 0x210, 0x218, 0x240):
            data = image()
            data[offset] ^= 0x20
            original = data[:]
            self.assertEqual(self.apply(data), -2)
            self.assertEqual(data, original)

    def test_duplicate_or_mixed_caps_rejected(self):
        for other in (CAP60, CAP120):
            data = image()
            data[0x260:0x26c] = other
            original = data[:]
            self.assertEqual(self.apply(data), -2)
            self.assertEqual(data, original)

    def test_cap_outside_target_method_is_not_patched(self):
        data = image()
        data[0x210:0x21c] = bytes(12)
        data[0x290:0x29c] = CAP60
        original = data[:]
        self.assertEqual(self.apply(data), -2)
        self.assertEqual(data, original)

    def test_bad_metadata_and_segment_ranges_rejected(self):
        for offset, fmt, value in ((20, 'I', 999999), (0x400, 'Q', 0),
                                   (0x460, 'Q', (1 << 64) - 1), (0x4a0, 'Q', 0),
                                   (0x500, 'I', 4), (0x504, 'I', 999999),
                                   (32 + 48, 'Q', 999999), (32 + 32, 'Q', (1 << 64) - 1),
                                   (32 + 72 + 48, 'I', 999999)):
            data = image()
            struct.pack_into('<' + fmt, data, offset, value)
            original = data[:]
            self.assertLess(self.apply(data), 0)
            self.assertEqual(data, original)

    def test_unsupported_implementation_bounds(self):
        for address in (0, vm(0x400), vm(0x202), BASE + 0x800):
            data = image()
            struct.pack_into('<Q', data, 0x508 + 16, address)
            original = data[:]
            self.assertEqual(self.apply(data), -2)
            self.assertEqual(data, original)

    def test_truncations(self):
        for length in (0, 7, 31, 80, 180, 500, 1200, 2048):
            self.assertEqual(self.apply(image()[:length]), -1)

    def test_fat32_and_fat64(self):
        for wide in (False, True):
            arch = struct.pack('>IIQQII' if wide else '>5I', 0x0100000c, 0, 4096, 4096,
                               12, *([0] if wide else []))
            data = bytearray(struct.pack('>II', 0xcafebabf if wide else 0xcafebabe, 1) + arch)
            data = data.ljust(4096, b'\0') + image()
            original = data[:]
            self.assertEqual(self.apply(data), 1)
            self.assertEqual(data[4096 + 0x210:4096 + 0x21c], CAP120)
            self.assertEqual(self.apply(data, False), 1)
            self.assertEqual(data, original)

    def test_bad_fat_ranges_and_overlaps(self):
        for offset, size in ((0, 4096), (4096, 999999), (999999, 4096)):
            data = bytearray(struct.pack('>7I', 0xcafebabe, 1, 0x0100000c, 0, offset, size, 12))
            data = data.ljust(4096, b'\0') + image()
            self.assertEqual(self.apply(data), -1)
        arch = struct.pack('>5I', 0x0100000c, 0, 4096, 4096, 12)
        data = bytearray(struct.pack('>II', 0xcafebabe, 2) + arch + arch).ljust(4096, b'\0') + image()
        self.assertEqual(self.apply(data), -1)


if __name__ == '__main__':
    unittest.main()
