"""Validate handler storage discovery for different game layouts, without iOS."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x100000000


def segment(name, address, size, section=None, protection=5):
    length = 72 + (80 if section else 0)
    data = struct.pack('<II16sQQQQ4I', 0x19, length, name, address, size, 0, 0, 7, protection,
                       int(section is not None), 0)
    if section:
        data += struct.pack('<16s16sQQ8I', b'__storage', b'__STORAGE', section[0], section[1],
                            0, 3, 0, 0, 0, 0, 0, 0)
    return data


def image(offset, protection=3, section_size=32, section_shift=0, storage=True, duplicate_text=False):
    commands = [segment(b'__PAGEZERO', 0, BASE), segment(b'__TEXT', BASE, offset)]
    if storage:
        commands.append(segment(b'__STORAGE', BASE + offset, 0x4000,
                                (BASE + offset + section_shift, section_size), protection))
    if duplicate_text:
        commands.append(commands[1])
    data = b''.join(commands)
    return bytearray(struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 6, len(commands), len(data), 0, 0) + data)


class StorageOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name) / 'jitless.so'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT / 'src/JITLessMachO.c'), '-o', str(library)], check=True)
        cls.library = ctypes.CDLL(str(library))
        cls.read = cls.library.GCCommonHandlerStorageOffset
        cls.read.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint64)]
        cls.read.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def offset(self, data):
        buffer = (ctypes.c_ubyte * len(data)).from_buffer(data)
        offset = ctypes.c_uint64(0xdeadbeef)
        valid = self.read(buffer, len(data), ctypes.byref(offset))
        return valid, offset.value

    def test_gd_2208_uses_actual_storage(self):
        self.assertEqual(self.offset(image(0x8c4000)), (1, 0x8c4000))

    def test_newer_game_uses_its_own_storage(self):
        self.assertEqual(self.offset(image(0xa4c000)), (1, 0xa4c000))

    def test_other_layout_and_section_offset(self):
        self.assertEqual(self.offset(image(0x900000, section_shift=0x100)), (1, 0x900100))

    def test_missing_storage_never_uses_old_constant(self):
        self.assertEqual(self.offset(image(0x8c4000, storage=False)), (0, 0))

    def test_readonly_storage_rejected(self):
        self.assertEqual(self.offset(image(0x8c4000, protection=5)), (0, 0))

    def test_storage_bounds_and_alignment(self):
        for values in ({'section_size': 0}, {'section_size': 4}, {'section_shift': 1},
                       {'section_shift': 0x4000}, {'section_shift': -8}):
            self.assertEqual(self.offset(image(0x8c4000, **values)), (0, 0))

    def test_duplicate_text_rejected(self):
        self.assertEqual(self.offset(image(0x8c4000, duplicate_text=True)), (0, 0))

    def test_truncated_or_corrupt_table(self):
        data = image(0x8c4000)
        for length in (0, 7, 31, 50, len(data) - 1):
            self.assertEqual(self.offset(data[:length]), (0, 0))
        struct.pack_into('<I', data, 20, 0xffffffff)
        self.assertEqual(self.offset(data), (0, 0))

    def test_bad_command_size(self):
        data = image(0x8c4000)
        struct.pack_into('<I', data, 36, 0)
        self.assertEqual(self.offset(data), (0, 0))

    def test_executable_and_containerized_game(self):
        for kind in (2, 6):
            data = image(0x8c4000)
            struct.pack_into('<I', data, 12, kind)
            self.assertEqual(self.offset(data), (1, 0x8c4000))
