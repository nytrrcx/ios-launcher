#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
// Offset relative to __TEXT of the writable __STORAGE,__storage section.
// Returns 0 for an absent, truncated or invalid layout; never guesses by game version.
int GCCommonHandlerStorageOffset(const uint8_t *data, size_t size, uint64_t *offset);
#ifdef __cplusplus
}
#endif
