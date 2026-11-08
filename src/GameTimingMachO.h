#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
// Raise the game's own display-link setup cap, keeping its animation interval
// and frame-rate request on the same clock. Call before signing/loading.
// 0 unchanged, 1 changed, -1 malformed, -2 unsupported game implementation.
// Discard the buffer on failure (an earlier FAT slice may have changed).
int GCConfigureNativeGameTiming(uint8_t *data, size_t size, bool enabled);
#ifdef __cplusplus
}
#endif
