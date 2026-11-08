#include "PromotionMachO.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t read64(const uint8_t *p) {
    return read32(p) | (uint64_t)read32(p + 4) << 32;
}
static uint32_t be32(const uint8_t *p) {
    return (uint32_t)p[3] | (uint32_t)p[2] << 8 | (uint32_t)p[1] << 16 | (uint32_t)p[0] << 24;
}
static uint64_t be64(const uint8_t *p) {
    return be32(p + 4) | (uint64_t)be32(p) << 32;
}
static void write32(uint8_t *p, uint32_t n) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(n >> (8 * i));
}
static bool endsWith(const char *path, const char *suffix) {
    size_t a = strlen(path), b = strlen(suffix);
    return a >= b && !strcmp(path + a - b, suffix);
}
static bool isDependency(uint32_t cmd) {
    return cmd == 0xc || cmd == 0x80000018 || cmd == 0x8000001f ||
           cmd == 0x20 || cmd == 0x80000023;
}
static const char *replacement(const char *path, const char *frameworks, bool enabled, char **allocated) {
    static const char *gles = "/System/Library/Frameworks/OpenGLES.framework/OpenGLES";
    static const char *names[] = {"ANGLEGLKit", "libEGL", "libGLESv2"};
    for (unsigned i = 0; i < 3; ++i) {
        char suffix[96];
        snprintf(suffix, sizeof(suffix), "/%s.framework/%s", names[i], names[i]);
        if ((i == 0 && !strcmp(path, gles)) || endsWith(path, suffix)) {
            if (!enabled) return i == 0 ? gles : NULL;
            size_t length = strlen(frameworks) + strlen(suffix) + 1;
            *allocated = malloc(length);
            if (!*allocated) return ""; // Distinguish allocation failure from an unrelated dependency.
            snprintf(*allocated, length, "%s%s", frameworks, suffix);
            return *allocated;
        }
    }
    return NULL;
}

static int patchSlice(uint8_t *data, size_t size, const char *frameworks, bool enabled) {
    if (size < 32 || read32(data) != 0xfeedfacf || read32(data + 4) != 0x0100000c) return -1;
    uint32_t count = read32(data + 16), oldSize = read32(data + 20);
    if (oldSize > size - 32 || count > oldSize / 8) return -1;
    // Never grow a command table across the first section/segment containing data.
    size_t limit = size, cursor = 32, newSize = 0;
    uint8_t *table = calloc(1, size);
    if (!table) return -1;
    int result = 0;
    for (uint32_t i = 0; i < count; ++i) {
        if (cursor > 32 + oldSize || 32 + oldSize - cursor < 8) { result = -1; break; }
        uint32_t cmd = read32(data + cursor), length = read32(data + cursor + 4);
        if (length < 8 || length % 8 || length > 32 + oldSize - cursor) { result = -1; break; }
        if (cmd == 0x19) { // LC_SEGMENT_64 and section_64
            if (length < 72) { result = -1; break; }
            uint64_t fileoff = read64(data + cursor + 40);
            uint32_t sections = read32(data + cursor + 64);
            if (sections > (length - 72) / 80) { result = -1; break; }
            if (fileoff && fileoff < limit) limit = (size_t)fileoff;
            for (uint32_t j = 0; j < sections; ++j) {
                const uint8_t *section = data + cursor + 72 + j * 80;
                uint32_t type = read32(section + 64) & 0xff;
                uint32_t offset = read32(section + 48);
                // S_ZEROFILL, S_GB_ZEROFILL and S_THREAD_LOCAL_ZEROFILL have no file bytes.
                if (type != 1 && type != 0xc && type != 0x12 && read64(section + 40) && offset < limit)
                    limit = offset;
            }
        }
        const char *target = NULL;
        char *allocated = NULL;
        uint32_t nameOffset = 0, outputLength = length;
        if (isDependency(cmd)) {
            if (length < 24) { result = -1; break; }
            nameOffset = read32(data + cursor + 8);
            if (nameOffset < 24 || nameOffset >= length ||
                !memchr(data + cursor + nameOffset, 0, length - nameOffset)) { result = -1; break; }
            const char *path = (const char *)data + cursor + nameOffset;
            target = replacement(path, frameworks, enabled, &allocated);
            if (target && !*target) { result = -1; break; }
            if (target && strcmp(path, target)) {
                size_t needed = nameOffset + strlen(target) + 1;
                if (needed > UINT32_MAX - 7) { free(allocated); result = -1; break; }
                outputLength = ((uint32_t)needed + 7) & ~7u;
                if (outputLength < length) outputLength = length;
                result = 1;
            } else target = NULL;
        }
        if (newSize > size || outputLength > size - newSize) { free(allocated); result = -2; break; }
        memcpy(table + newSize, data + cursor, length);
        if (target) {
            memset(table + newSize + nameOffset, 0, outputLength - nameOffset);
            memcpy(table + newSize + nameOffset, target, strlen(target) + 1);
            write32(table + newSize + 4, outputLength);
        }
        free(allocated);
        newSize += outputLength;
        cursor += length;
    }
    if (result >= 0 && cursor != 32 + oldSize) result = -1;
    if (result > 0) {
        if (limit < 32 || newSize > limit - 32 || newSize > UINT32_MAX) result = -2;
        // Unknown commands may refer to payloads not described by sections. Require zero padding too.
        for (size_t i = 32 + oldSize; result > 0 && i < 32 + newSize; ++i)
            if (data[i]) result = -2;
        if (result > 0) {
            memcpy(data + 32, table, newSize);
            write32(data + 20, (uint32_t)newSize);
        }
    }
    free(table);
    return result;
}

int GCPatchRenderer(uint8_t *data, size_t size, const char *frameworks, bool enabled) {
    if (!data || !frameworks || size < 8) return -1;
    uint32_t magic = be32(data);
    if (magic != 0xcafebabe && magic != 0xcafebabf) return patchSlice(data, size, frameworks, enabled);
    uint32_t count = be32(data + 4);
    size_t stride = magic == 0xcafebabf ? 32 : 20;
    if (!count || count > (size - 8) / stride) return -1;
    int changed = 0;
    bool foundArm64 = false;
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *arch = data + 8 + i * stride;
        uint64_t offset = stride == 32 ? be64(arch + 8) : be32(arch + 8);
        uint64_t length = stride == 32 ? be64(arch + 16) : be32(arch + 12);
        if (offset < 8 + count * stride || offset > size || length > size - offset) return -1;
        for (uint32_t j = 0; j < i; ++j) {
            const uint8_t *other = data + 8 + j * stride;
            uint64_t start = stride == 32 ? be64(other + 8) : be32(other + 8);
            uint64_t span = stride == 32 ? be64(other + 16) : be32(other + 12);
            if (offset < start + span && start < offset + length) return -1;
        }
        if (be32(arch) != 0x0100000c) continue; // Only arm64 is loadable by this launcher.
        foundArm64 = true;
        int result = patchSlice(data + offset, (size_t)length, frameworks, enabled);
        if (result < 0) return result;
        changed |= result;
    }
    return foundArm64 ? changed : -1;
}
