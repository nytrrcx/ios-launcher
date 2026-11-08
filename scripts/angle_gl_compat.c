// Compatibility entry points used by Geometry Dash's Cocos iOS renderer.
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>

extern void GL_RenderbufferStorageMultisampleANGLE(GLenum, GLsizei, GLenum, GLsizei, GLsizei);
extern void GL_BlitFramebufferANGLE(GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLbitfield, GLenum);

void glRenderbufferStorageMultisampleAPPLE(GLenum target, GLsizei samples, GLenum format,
                                         GLsizei width, GLsizei height) {
    GL_RenderbufferStorageMultisampleANGLE(target, samples, format, width, height);
}

void glResolveMultisampleFramebufferAPPLE(void) {
    // Cocos binds its MSAA framebuffer for reading and the window backbuffer
    // for drawing before calling Apple's no-argument resolve entry point.
    EGLDisplay display = eglGetCurrentDisplay();
    EGLSurface surface = eglGetCurrentSurface(EGL_DRAW);
    EGLint width = 0, height = 0;
    if (surface != EGL_NO_SURFACE &&
        eglQuerySurface(display, surface, EGL_WIDTH, &width) &&
        eglQuerySurface(display, surface, EGL_HEIGHT, &height) && width > 0 && height > 0) {
        GL_BlitFramebufferANGLE(0, 0, width, height, 0, 0, width, height,
                                GL_COLOR_BUFFER_BIT, GL_NEAREST);
    }
}
