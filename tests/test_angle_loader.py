from pathlib import Path
import importlib.util
import json
import shutil
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('loader_patch', ROOT / 'scripts/patch_angle_loader.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


def exports(binary):
    """Read real exported definitions, rather than trusting only the linker stub."""
    cursor = 32
    for _ in range(struct.unpack_from('<I', binary, 16)[0]):
        kind, length = struct.unpack_from('<II', binary, cursor)
        if kind == 2:
            offset, count, strings, size = struct.unpack_from('<4I', binary, cursor + 8)
            result = set()
            for i in range(count):
                name, flags, _, _, _ = struct.unpack_from('<IBBHQ', binary, offset + i * 16)
                if name and not flags & 0xe0 and flags & 0xe and flags & 1:
                    start = strings + name
                    result.add(binary[start:binary.index(b'\0', start, strings + size)].decode())
            return result
        cursor += length
    raise ValueError('Missing Mach-O symbol table')


class LoaderPatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        for name in ('Makefile', 'MGLKit.m', 'MGLContext.mm', 'MGLDisplay.mm', 'MGLLayer.mm',
                     'MGLKViewController.mm', 'Frameworks/libGLESv2.framework/libGLESv2.tbd'):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / 'vendor/ANGLEGLKit' / name, destination)

    def tearDown(self):
        self.directory.cleanup()

    def test_direct_entry_points_exist_in_shipped_angle(self):
        import re
        patcher.patch(self.root)
        header = (self.root / 'GeodeEGL.h').read_text()
        mapped = set(re.findall(r'^#define egl\w+ (EGL_\w+)$', header, re.M))
        actual = exports((ROOT / 'Resources/GDFrameworks/libGLESv2.framework/libGLESv2').read_bytes())
        self.assertGreater(len(mapped), 50)
        self.assertFalse({'_' + name for name in mapped} - actual)
        self.assertIn('_GL_GenFramebuffers', actual)
        self.assertIn('_GL_GenRenderbuffers', actual)
        kit = (self.root / 'MGLKit.m').read_text()
        self.assertNotIn('dlsym(RTLD_NEXT', kit)
        self.assertIn('orig_glGenFramebuffers = GL_GenFramebuffers;', kit)
        self.assertIn('orig_glGenRenderbuffers = GL_GenRenderbuffers;', kit)
        self.assertIn('#define eglGetDisplay EGL_GetDisplay', header)
        makefile = (self.root / 'Makefile').read_text()
        self.assertIn('ANGLEGLKit_FRAMEWORKS = libGLESv2', makefile)
        self.assertNotIn('ANGLEGLKit_FRAMEWORKS = libEGL', makefile)
        self.assertFalse({'_GL_GenFramebuffers', '_GL_GenRenderbuffers'} - actual)
        kit = (self.root / 'MGLKit.m').read_text()
        self.assertNotIn('dlsym(RTLD_NEXT', kit)
        self.assertIn('orig_glGenFramebuffers = GL_GenFramebuffers', kit)

    def test_missing_entry_point_rejected_before_writing(self):
        source = self.root / 'MGLContext.mm'
        source.write_text(source.read_text() + '\nvoid test() { eglUnknownEntryPoint(); }\n')
        original = (self.root / 'Makefile').read_bytes()
        with self.assertRaises(ValueError):
            patcher.patch(self.root)
        self.assertEqual((self.root / 'Makefile').read_bytes(), original)
        self.assertFalse((self.root / 'GeodeEGL.h').exists())

    def test_real_game_imports_have_direct_definitions(self):
        import re
        patcher.patch(self.root)
        required = set(json.loads((ROOT / 'tests/fixtures/gd-2.208-renderer-imports.json').read_text())['symbols'])
        assembly = (self.root / 'GeodeGLForwarders.S').read_text()
        provided = set(re.findall(r'^\.globl (_gl\w+)$', assembly, re.M))
        targets = set(re.findall(r'    b (_GL_\w+)$', assembly, re.M))
        actual = exports((ROOT / 'Resources/GDFrameworks/libGLESv2.framework/libGLESv2').read_bytes())
        self.assertFalse(targets - actual)
        provided |= {'_glGenFramebuffers', '_glGenRenderbuffers',
            '_glRenderbufferStorageMultisampleAPPLE', '_glResolveMultisampleFramebufferAPPLE',
            '_OBJC_CLASS_$_EAGLContext', '_kEAGLColorFormatRGB565', '_kEAGLColorFormatRGBA8',
            '_kEAGLDrawablePropertyColorFormat', '_kEAGLDrawablePropertyRetainedBacking'}
        self.assertEqual(len(required), 79)
        self.assertFalse(required - provided)
        self.assertIn('_glBindFramebuffer:\n    b _GL_BindFramebuffer', assembly)
        self.assertNotIn('-reexport_framework', (self.root / 'Makefile').read_text())

    def test_repeated_patch_rejected_without_writing(self):
        patcher.patch(self.root)
        original = (self.root / 'Makefile').read_bytes()
        with self.assertRaises(ValueError):
            patcher.patch(self.root)
        self.assertEqual((self.root / 'Makefile').read_bytes(), original)
