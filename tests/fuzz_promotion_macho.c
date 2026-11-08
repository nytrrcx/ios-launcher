// Feed a valid thin/universal Mach-O fixture on stdin; exercise bounded mutations.
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "PromotionMachO.h"
#include "GameTimingMachO.h"

int main(void) {
    uint8_t seed[16384], buffer[16384];
    size_t length = fread(seed, 1, sizeof(seed), stdin);
    if (!length) return 1;
    uint32_t random = 12345;
    for (unsigned i = 0; i < 50000; ++i) {
        memcpy(buffer, seed, length);
        random = random * 1664525u + 1013904223u;
        size_t size = i % 3 == 0 ? random % (length + 1) : length;
        for (unsigned j = 0; j < 1 + i % 8; ++j) {
            random = random * 1664525u + 1013904223u;
            size_t offset = random % length;
            random = random * 1664525u + 1013904223u;
            buffer[offset] = (uint8_t)(random >> 24);
        }
        GCPatchRenderer(buffer, size, "/private/var/mobile/Containers/Example/Frameworks", i % 2);
        GCConfigureNativeGameTiming(buffer, size, i % 2);
    }
    puts("50000 mutated inputs passed");
    return 0;
}
