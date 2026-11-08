#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
// Rewrites dependency paths in thin arm64 or universal Mach-O data.
// 0: unchanged, 1: changed, -1: malformed/unsupported, -2: no header space.
// On failure discard the buffer; a previous universal slice may have changed.
int GCPatchRenderer(uint8_t *data, size_t size, const char *frameworks, bool enabled);
#ifdef __cplusplus
}
#endif
