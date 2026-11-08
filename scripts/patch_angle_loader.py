#!/usr/bin/env python3
"""Bind EGL calls to the same libGLESv2 image as GL, without an executable-path loader."""
from pathlib import Path
import argparse
import re


def patch(root):
    root = Path(root)
    makefile = (root / 'Makefile').read_text()
    kit = (root / 'MGLKit.m').read_text()
    header = root / 'GeodeEGL.h'
    if header.exists() or 'GCGeodeEGLDirectVersion' in kit:
        raise ValueError('Direct EGL binding is already installed; use a clean checkout')
    exports = (root / 'Frameworks/libGLESv2.framework/libGLESv2.tbd').read_text()
    names = set(re.findall(r'\b_EGL_(\w+)\b', exports))
    used = set()
    for source in root.glob('*.mm'):
        used.update(re.findall(r'\begl([A-Z]\w*)\s*\(', source.read_text()))
    if not used or used - names:
        raise ValueError(f'Missing direct EGL exports: {sorted(used - names)}')
    anchor = 'ANGLEGLKit_FRAMEWORKS = libEGL'
    if makefile.count(anchor) != 1 or makefile.count('ANGLEGLKit_CFLAGS = ') != 1:
        raise ValueError('Unexpected ANGLEGLKit build configuration')
    makefile = makefile.replace(anchor, 'ANGLEGLKit_FRAMEWORKS = libGLESv2')
    makefile = makefile.replace('ANGLEGLKit_CFLAGS = ',
                               'ANGLEGLKit_CFLAGS = -include $(THEOS_PROJECT_DIR)/GeodeEGL.h ')
    # Match the minimum ABI version of the OpenGLES dependency being replaced.
    if makefile.count('ANGLEGLKit_LDFLAGS = ') != 1:
        raise ValueError('Unexpected ANGLEGLKit linker configuration')
    makefile = makefile.replace('ANGLEGLKit_LDFLAGS = ',
        'ANGLEGLKit_LDFLAGS = -Wl,-current_version,1.0,-compatibility_version,1.0 ')
    lines = ['// EGL and GL must use the same ANGLE image and thread-local context.', '#pragma once']
    lines += [f'#define egl{name} EGL_{name}' for name in sorted(names)]
    # RTLD_NEXT may find Apple's GL implementation, or NULL, after other modules
    # load. These explicit exports preserve the first-call default-buffer shim.
    before = kit
    kit = kit.replace('orig_glGenFramebuffers = dlsym(RTLD_NEXT, "glGenFramebuffers");',
                      'orig_glGenFramebuffers = GL_GenFramebuffers;')
    kit = kit.replace('orig_glGenRenderbuffers = dlsym(RTLD_NEXT, "glGenRenderbuffers");',
                      'orig_glGenRenderbuffers = GL_GenRenderbuffers;')
    if before == kit or 'dlsym(RTLD_NEXT' in kit:
        raise ValueError('Unexpected ANGLE framebuffer shims')
    kit = kit.replace('void (*orig_glGenFramebuffers)',
        'extern void GL_GenFramebuffers(GLsizei n, GLuint *framebuffers);\n'
        'extern void GL_GenRenderbuffers(GLsizei n, GLuint *renderbuffers);\n\n'
        'void (*orig_glGenFramebuffers)')
    kit += '\n__attribute__((used, visibility("default"))) unsigned GCGeodeEGLDirectVersion = 1;\n'
    header.write_text('\n'.join(lines) + '\n')
    (root / 'Makefile').write_text(makefile)
    (root / 'MGLKit.m').write_text(kit)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    patch(parser.parse_args().source)
