#include "JITLessMachO.h"
#include <string.h>

static uint32_t read32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t read64(const uint8_t *p) {
    return read32(p) | (uint64_t)read32(p + 4) << 32;
}
static int named(const uint8_t *p, const char *name) {
    size_t n = strlen(name);
    return n < 16 && !memcmp(p, name, n) && p[n] == 0;
}

int GCCommonHandlerStorageOffset(const uint8_t *data, size_t size, uint64_t *offset) {
    if (!offset) return 0;
    *offset = 0;
    if (!data || size < 32 || read32(data) != 0xfeedfacf || read32(data + 4) != 0x0100000c) return 0;
    uint32_t count = read32(data + 16), commands = read32(data + 20);
    if (commands > size - 32 || count > commands / 8) return 0;
    size_t cursor = 32;
    uint64_t base = 0, storage = 0;
    int foundText = 0, foundStorage = 0;
    for (uint32_t i = 0; i < count; ++i) {
        if (cursor > 32 + commands || 32 + commands - cursor < 8) return 0;
        const uint8_t *cmd = data + cursor;
        uint32_t length = read32(cmd + 4);
        if (length < 8 || length % 8 || length > 32 + commands - cursor) return 0;
        if (read32(cmd) == 0x19) { // LC_SEGMENT_64
            if (length < 72) return 0;
            uint32_t sections = read32(cmd + 64);
            if (sections > (length - 72) / 80) return 0;
            if (named(cmd + 8, "__TEXT")) {
                if (foundText++) return 0;
                base = read64(cmd + 24);
            }
            if (named(cmd + 8, "__STORAGE")) {
                if (!(read32(cmd + 60) & 2)) return 0; // VM_PROT_WRITE
                uint64_t start = read64(cmd + 24), span = read64(cmd + 32);
                for (uint32_t j = 0; j < sections; ++j) {
                    const uint8_t *section = cmd + 72 + j * 80;
                    if (!named(section, "__storage")) continue;
                    if (!named(section + 16, "__STORAGE") || foundStorage++) return 0;
                    storage = read64(section + 32);
                    uint64_t bytes = read64(section + 40);
                    if (bytes < sizeof(uint64_t) || storage < start || storage - start > span ||
                        bytes > span - (storage - start) || storage % sizeof(uint64_t)) return 0;
                }
            }
        }
        cursor += length;
    }
    if (cursor != 32 + commands || !foundText || !foundStorage || storage <= base) return 0;
    *offset = storage - base;
    return 1;
}
