from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stencil_patch', ROOT / 'scripts/patch_angle_stencil.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class StencilPatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        for name in ('MGLLayer.mm', 'MGLContext.mm'):
            shutil.copy(ROOT / 'vendor/ANGLEGLKit' / name, self.root / name)

    def tearDown(self):
        self.directory.cleanup()

    def test_real_stencil_and_compatible_context(self):
        patcher.patch(self.root)
        layer = (self.root / 'MGLLayer.mm').read_text()
        context = (self.root / 'MGLContext.mm').read_text()
        self.assertIn('_drawableDepthFormat = MGLDrawableDepthFormat24;', layer)
        self.assertIn('_drawableStencilFormat = MGLDrawableStencilFormat8;', layer)
        self.assertIn('EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 8,', context)
        self.assertIn('glGetIntegerv(GL_STENCIL_BITS, &stencilBits)', context)
        self.assertIn('GCGeodeStencilFixVersion = 1', layer)

    def test_already_patched_rejected(self):
        patcher.patch(self.root)
        expected = (self.root / 'MGLLayer.mm').read_bytes()
        with self.assertRaises(ValueError):
            patcher.patch(self.root)
        self.assertEqual((self.root / 'MGLLayer.mm').read_bytes(), expected)

    def test_unexpected_source_rejected_before_writing(self):
        path = self.root / 'MGLContext.mm'
        path.write_text(path.read_text().replace('EGL_DEPTH_SIZE', 'INCOMPATIBLE_UPSTREAM_CHANGE'))
        expected = (self.root / 'MGLLayer.mm').read_bytes()
        with self.assertRaises(ValueError):
            patcher.patch(self.root)
        self.assertEqual((self.root / 'MGLLayer.mm').read_bytes(), expected)
