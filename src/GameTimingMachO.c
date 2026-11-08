#include "GameTimingMachO.h"
#include <string.h>

static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t u64(const uint8_t *p) { return u32(p) | (uint64_t)u32(p + 4) << 32; }
static uint32_t be32(const uint8_t *p) {
    return (uint32_t)p[3] | (uint32_t)p[2] << 8 | (uint32_t)p[1] << 16 | (uint32_t)p[0] << 24;
}
static uint64_t be64(const uint8_t *p) { return be32(p + 4) | (uint64_t)be32(p) << 32; }
static void put32(uint8_t *p, uint32_t v) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i));
}

typedef struct {
    uint8_t *data;
    size_t size;
    uint32_t commands;
    uint64_t text, textSize, classes, classSize;
} Image;

// All pointers in on-disk Objective-C metadata are unslid virtual addresses.
// Translate through file-backed segments; VM and file offsets need not match.
static uint8_t *at(Image *image, uint64_t address, uint64_t length) {
    size_t cursor = 32;
    for (uint32_t i = 0; i < image->commands; ++i) {
        uint8_t *cmd = image->data + cursor;
        if (u32(cmd) == 0x19) {
            uint64_t vm = u64(cmd + 24), file = u64(cmd + 40), size = u64(cmd + 48);
            if (address >= vm && address - vm <= size && length <= size - (address - vm))
                return image->data + (size_t)(file + address - vm);
        }
        cursor += u32(cmd + 4);
    }
    return NULL;
}
static bool pointer(Image *image, uint64_t address, uint64_t *value) {
    uint8_t *p = at(image, address, 8);
    if (!p) return false;
    *value = u64(p);
    return true;
}
static bool named(Image *image, uint64_t address, const char *name) {
    size_t length = strlen(name) + 1;
    uint8_t *p = at(image, address, length);
    return p && !memcmp(p, name, length);
}

static int inspect(Image *image) {
    uint8_t *data = image->data;
    if (image->size < 32 || u32(data) != 0xfeedfacf || u32(data + 4) != 0x0100000c) return -1;
    uint32_t bytes = u32(data + 20);
    image->commands = u32(data + 16);
    if (bytes > image->size - 32 || image->commands > bytes / 8) return -1;
    size_t cursor = 32, end = 32 + bytes;
    for (uint32_t i = 0; i < image->commands; ++i) {
        if (cursor > end || end - cursor < 8) return -1;
        uint8_t *cmd = data + cursor;
        uint32_t length = u32(cmd + 4);
        if (length < 8 || length % 8 || length > end - cursor) return -1;
        if (u32(cmd) == 0x19) {
            if (length < 72) return -1;
            uint64_t vm = u64(cmd + 24), vmSize = u64(cmd + 32);
            uint64_t file = u64(cmd + 40), fileSize = u64(cmd + 48);
            uint32_t count = u32(cmd + 64);
            if (file > image->size || fileSize > image->size - file ||
                vmSize > UINT64_MAX - vm || fileSize > vmSize || count > (length - 72) / 80) return -1;
            for (uint32_t j = 0; j < count; ++j) {
                uint8_t *section = cmd + 72 + 80 * j;
                bool text = !memcmp(section, "__text\0", 7) && !memcmp(section + 16, "__TEXT\0", 7);
                bool classes = !memcmp(section, "__objc_classlist", 16);
                if (!text && !classes) continue;
                uint64_t address = u64(section + 32), size = u64(section + 40);
                uint32_t offset = u32(section + 48), flags = u32(section + 64) & 0xff;
                if (address < vm || address - vm > fileSize || size > fileSize - (address - vm) ||
                    (uint64_t)offset != file + address - vm || flags == 1 || flags == 0xc || flags == 0x12) return -1;
                if (text) {
                    if (image->text || !(u32(cmd + 60) & 4)) return -1;
                    image->text = address; image->textSize = size;
                } else {
                    if (image->classes || size % 8) return -1;
                    image->classes = address; image->classSize = size;
                }
            }
        }
        cursor += length;
    }
    if (cursor != end) return -1;
    return image->text && image->classes ? 0 : -2;
}

static bool methodEntry(Image *image, uint64_t list, uint32_t flags, uint32_t stride,
                        uint32_t index, uint64_t *name, uint64_t *implementation) {
    uint64_t address = list + 8 + (uint64_t)index * stride;
    uint8_t *entry = at(image, address, stride);
    if (!entry) return false;
    if (flags & 0x80000000) {
        // Relative method lists optionally use an indirect selector reference.
        *name = address + (int32_t)u32(entry);
        if (!(flags & 0x40000000) && !pointer(image, *name, name)) return false;
        *implementation = address + 8 + (int32_t)u32(entry + 8);
    } else {
        *name = u64(entry);
        *implementation = u64(entry + 16);
    }
    return true;
}

static int patchSlice(uint8_t *data, size_t size, bool enabled) {
    Image image = {.data = data, .size = size};
    int result = inspect(&image);
    if (result) return result;
    uint64_t methods = 0;
    for (uint64_t i = 0; i < image.classSize; i += 8) {
        uint64_t cls, ro, name, list;
        if (!pointer(&image, image.classes + i, &cls) || cls > UINT64_MAX - 32 ||
            !pointer(&image, cls + 32, &ro)) return -1;
        ro &= UINT64_C(0x00007ffffffffff8); // FAST_DATA_MASK: remove class data flags.
        if (ro > UINT64_MAX - 32 || !pointer(&image, ro + 24, &name) || !pointer(&image, ro + 32, &list)) return -1;
        if (!named(&image, name, "CCDirectorCaller")) continue;
        if (methods || !list) return -2;
        methods = list;
    }
    if (!methods) return -2;
    uint8_t *header = at(&image, methods, 8);
    if (!header) return -1;
    uint32_t flags = u32(header), count = u32(header + 4), stride = flags & 0xfffc;
    if (stride < (flags & 0x80000000 ? 12u : 24u) || stride > 512 ||
        count > 4096 || !at(&image, methods, 8 + (uint64_t)stride * count)) return -1;
    uint64_t start = 0, finish = UINT64_MAX;
    for (uint32_t i = 0; i < count; ++i) {
        uint64_t name, imp;
        if (!methodEntry(&image, methods, flags, stride, i, &name, &imp)) return -1;
        if (!named(&image, name, "startMainLoop")) continue;
        if (start) return -2;
        start = imp;
    }
    if (!start || start % 4 || start < image.text || start - image.text >= image.textSize) return -2;
    // The next method bounds this known implementation. Refuse unfamiliar
    // layouts instead of searching the whole executable for a coincidental cap.
    for (uint32_t i = 0; i < count; ++i) {
        uint64_t name, imp;
        if (!methodEntry(&image, methods, flags, stride, i, &name, &imp)) return -1;
        if (imp > start && imp < finish) finish = imp;
    }
    if (finish == UINT64_MAX || finish <= start || finish - start > 4096 ||
        finish - image.text > image.textSize || (finish - start) % 4) return -2;
    size_t length = (size_t)(finish - start);
    uint8_t *code = at(&image, start, length);
    if (!code) return -1;
    // cmp x0,#cap; mov w8,#cap; csel x20,x0,x8,lt.
    // Both consumers use x20: CADisplayLink's range and 1/fps passed to the
    // native director. Preserve those consumers, timestamps, physics and audio.
    size_t capOffset = 0, capCount = 0, intervalCount = 0;
    static const uint8_t interval[] = {
        0x00,0x10,0x2e,0x1e, // fmov s0,#1
        0x00,0x18,0x28,0x1e, // fdiv s0,s0,s8
        0x00,0xc0,0x22,0x1e, // fcvt d0,s0
        0x08,0x00,0x40,0xf9, // ldr x8,[x0]
        0x01,0x31,0x40,0xf9  // ldr x1,[x8,#0x60] (setAnimationInterval)
    };
    for (size_t i = 0; i + 12 <= length; i += 4) {
        uint32_t cmp = u32(code + i), mov = u32(code + i + 4);
        if (((cmp == 0xf100f01f && mov == 0x52800788) ||
             (cmp == 0xf101e01f && mov == 0x52800f08)) && u32(code + i + 8) == 0x9a88b014) {
            capOffset = i; capCount++;
        }
        if (i + sizeof(interval) <= length && !memcmp(code + i, interval, sizeof(interval))) intervalCount++;
    }
    if (capCount != 1 || intervalCount != 1) return -2;
    uint32_t cmp = enabled ? 0xf101e01f : 0xf100f01f;
    uint32_t mov = enabled ? 0x52800f08 : 0x52800788;
    if (u32(code + capOffset) == cmp) return 0;
    put32(code + capOffset, cmp);
    put32(code + capOffset + 4, mov);
    return 1;
}

int GCConfigureNativeGameTiming(uint8_t *data, size_t size, bool enabled) {
    if (!data || size < 8) return -1;
    uint32_t magic = be32(data);
    if (magic != 0xcafebabe && magic != 0xcafebabf) return patchSlice(data, size, enabled);
    uint32_t count = be32(data + 4);
    size_t stride = magic == 0xcafebabf ? 32 : 20;
    if (!count || count > (size - 8) / stride) return -1;
    bool found = false;
    int changed = 0;
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *arch = data + 8 + i * stride;
        uint64_t offset = stride == 32 ? be64(arch + 8) : be32(arch + 8);
        uint64_t length = stride == 32 ? be64(arch + 16) : be32(arch + 12);
        if (offset < 8 + (uint64_t)count * stride || offset > size || length > size - offset) return -1;
        for (uint32_t j = 0; j < i; ++j) {
            const uint8_t *other = data + 8 + j * stride;
            uint64_t begin = stride == 32 ? be64(other + 8) : be32(other + 8);
            uint64_t span = stride == 32 ? be64(other + 16) : be32(other + 12);
            if (offset < begin + span && begin < offset + length) return -1;
        }
        if (be32(arch) != 0x0100000c) continue;
        found = true;
        int result = patchSlice(data + offset, (size_t)length, enabled);
        if (result < 0) return result;
        changed |= result;
    }
    return found ? changed : -1;
}
