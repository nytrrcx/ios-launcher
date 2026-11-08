#!/usr/bin/env python3
"""Give ANGLEGLKit a real depth/stencil attachment before Cocos caches its bits."""
from pathlib import Path
import argparse
import re

SYMBOL = 'GCGeodeStencilFixVersion'


def replace_once(text, pattern, replacement):
    text, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f'Expected one source anchor, found {count}: {pattern}')
    return text


def patch(root):
    root = Path(root)
    layer = (root / 'MGLLayer.mm').read_text()
    context = (root / 'MGLContext.mm').read_text()
    if SYMBOL in layer:
        raise ValueError('ANGLEGLKit is already patched; use a clean pinned checkout')
    layer = replace_once(layer, r'_drawableDepthFormat\s*=\s*MGLDrawableDepthFormatNone;',
                         '_drawableDepthFormat = MGLDrawableDepthFormat24;')
    layer = replace_once(layer, r'_drawableStencilFormat\s*=\s*MGLDrawableStencilFormatNone;',
                         '_drawableStencilFormat = MGLDrawableStencilFormat8;')
    # The context and the window surface must select compatible EGL configurations.
    context = replace_once(context,
        r'EGL_DEPTH_SIZE,\s*EGL_DONT_CARE,\s*EGL_STENCIL_SIZE,\s*EGL_DONT_CARE,',
        'EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 8,')
    context = replace_once(context, r'#include <EGL/egl.h>',
                           '#include <GLES2/gl2.h>\n#include <EGL/egl.h>')
    context = replace_once(context,
        r'return \[self setCurrentContextForLayer:\(id\)drawable\];',
        'if (![self setCurrentContextForLayer:(id)drawable]) return NO;\n'
        '    GLint framebuffer = 0, stencilBits = 0;\n'
        '    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &framebuffer);\n'
        '    if (framebuffer == 0) {\n'
        '        glGetIntegerv(GL_STENCIL_BITS, &stencilBits);\n'
        '        if (stencilBits < 8) {\n'
        '            NSLog(@"[Geode ProMotion] Expected 8 stencil bits, got %d", stencilBits);\n'
        '            return NO;\n'
        '        }\n'
        '    }\n'
        '    return YES;')
    layer = replace_once(layer, r'@implementation MGLLayer\b',
        'extern "C" {\n'
        '__attribute__((used, visibility("default"))) unsigned GCGeodeStencilFixVersion = 1;\n'
        '}\n\n@implementation MGLLayer')
    # Do not lie about GL_STENCIL_BITS or substitute rectangular scissoring.
    (root / 'MGLLayer.mm').write_text(layer)
    (root / 'MGLContext.mm').write_text(context)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    patch(parser.parse_args().source)
