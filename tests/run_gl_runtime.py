#!/usr/bin/env python3
"""Exercise generated GL bridges with dyld, real arm64 calls, and a mock backend."""
from pathlib import Path
import importlib.util
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gl_patch', root / 'scripts/patch_angle_loader.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

with tempfile.TemporaryDirectory(prefix='geode-gl-') as directory:
    work = Path(directory)
    source = work / 'angle'
    shutil.copytree(root / 'vendor/ANGLEGLKit', source)
    patcher.patch(source)
    targets = set(re.findall(r'    b _GL_(\w+)', (source / 'GeodeGLForwarders.S').read_text()))
    custom = {'BindFramebuffer', 'Uniform4f', 'TexImage2D', 'GetError', 'GetString',
              'RenderbufferStorageMultisampleANGLE', 'BlitFramebufferANGLE'}
    backend = r'''
#include <assert.h>
#include <EGL/egl.h>
#include <GLES2/gl2.h>
static int calls;
int GCBackendCalls(void) { return calls; }
void GL_BindFramebuffer(GLenum target, GLuint buffer) {
    assert(target == GL_FRAMEBUFFER && buffer == 7); calls++;
}
void GL_Uniform4f(GLint location, GLfloat a, GLfloat b, GLfloat c, GLfloat d) {
    assert(location == 9 && a == 1.25f && b == 2.5f && c == 3.75f && d == 4.0f); calls++;
}
void GL_TexImage2D(GLenum target, GLint level, GLint format, GLsizei width, GLsizei height,
                  GLint border, GLenum inputFormat, GLenum type, const void *data) {
    assert(target == GL_TEXTURE_2D && level == 2 && format == GL_RGBA);
    assert(width == 320 && height == 240 && border == 0 && inputFormat == GL_RGBA);
    assert(type == GL_UNSIGNED_BYTE && data == (const void *)0x12345000); calls++;
}
GLenum GL_GetError(void) { calls++; return GL_INVALID_VALUE; }
const GLubyte *GL_GetString(GLenum name) { assert(name == GL_VENDOR); calls++; return (const GLubyte *)"mock ANGLE"; }
void GL_RenderbufferStorageMultisampleANGLE(GLenum target, GLsizei samples, GLenum format, GLsizei width, GLsizei height) {
    assert(target == GL_RENDERBUFFER && samples == 4 && format == 0x8058 && width == 320 && height == 240); calls++;
}
void GL_BlitFramebufferANGLE(GLint x0, GLint y0, GLint x1, GLint y1,
                           GLint a0, GLint b0, GLint a1, GLint b1, GLbitfield mask, GLenum filter) {
    assert(!x0 && !y0 && !a0 && !b0 && x1 == 1280 && y1 == 720 && a1 == 1280 && b1 == 720);
    assert(mask == GL_COLOR_BUFFER_BIT && filter == GL_NEAREST); calls++;
}
EGLDisplay EGL_GetCurrentDisplay(void) { return (EGLDisplay)1; }
EGLSurface EGL_GetCurrentSurface(EGLint which) { assert(which == EGL_DRAW); return (EGLSurface)2; }
EGLBoolean EGL_QuerySurface(EGLDisplay display, EGLSurface surface, EGLint attribute, EGLint *value) {
    assert(display == (EGLDisplay)1 && surface == (EGLSurface)2);
    assert(attribute == EGL_WIDTH || attribute == EGL_HEIGHT);
    *value = attribute == EGL_WIDTH ? 1280 : 720; return EGL_TRUE;
}
'''
    backend += '\n'.join(f'void GL_{name}(void) {{}}' for name in sorted(targets - custom))
    (work / 'backend.c').write_text(backend)
    (work / 'client.c').write_text(r'''
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <GLES2/gl2.h>
extern void glRenderbufferStorageMultisampleAPPLE(GLenum, GLsizei, GLenum, GLsizei, GLsizei);
extern void glResolveMultisampleFramebufferAPPLE(void);
int main(int argc, char **argv) {
    assert(argc == 3);
    void *wrapper = dlopen(argv[1], RTLD_NOW | RTLD_FIRST);
    assert(wrapper);
    Dl_info info;
    assert(dladdr(dlsym(wrapper, "glBindFramebuffer"), &info));
    assert(strstr(info.dli_fname, "libGCGLWrapper"));
    glBindFramebuffer(GL_FRAMEBUFFER, 7);
    glUniform4f(9, 1.25f, 2.5f, 3.75f, 4.0f);
    glTexImage2D(GL_TEXTURE_2D, 2, GL_RGBA, 320, 240, 0, GL_RGBA, GL_UNSIGNED_BYTE, (const void *)0x12345000);
    assert(glGetError() == GL_INVALID_VALUE);
    assert(!strcmp((const char *)glGetString(GL_VENDOR), "mock ANGLE"));
    glRenderbufferStorageMultisampleAPPLE(GL_RENDERBUFFER, 4, 0x8058, 320, 240);
    glResolveMultisampleFramebufferAPPLE();
    void *backend = dlopen(argv[2], RTLD_NOW | RTLD_FIRST);
    assert(backend);
    int (*calls)(void) = dlsym(backend, "GCBackendCalls");
    assert(calls && calls() == 7);
    puts("PASS: direct dyld exports, integer/float/pointer/stack arguments, return values, and Apple MSAA");
    return 0;
}
''')
    common = ['xcrun', 'clang', '-I' + str(source / 'include')]
    backend_lib = work / 'libGCGLBackend.dylib'
    wrapper_lib = work / 'libGCGLWrapper.dylib'
    subprocess.run(common + ['-dynamiclib', '-include', str(source / 'GeodeEGL.h'),
        str(work / 'backend.c'), '-Wl,-install_name,@rpath/libGCGLBackend.dylib',
        '-o', str(backend_lib)], check=True)
    subprocess.run(common + ['-dynamiclib', '-include', str(source / 'GeodeEGL.h'),
        str(source / 'GeodeGLForwarders.S'), str(source / 'GeodeGLCompat.c'),
        '-L' + str(work), '-lGCGLBackend', '-Wl,-rpath,@loader_path',
        '-Wl,-install_name,@rpath/libGCGLWrapper.dylib', '-o', str(wrapper_lib)], check=True)
    client = work / 'client'
    subprocess.run(common + [str(work / 'client.c'), '-L' + str(work), '-lGCGLWrapper',
        '-Wl,-rpath,@loader_path', '-o', str(client)], check=True)
    subprocess.run([str(client), str(wrapper_lib), str(backend_lib)], check=True)
