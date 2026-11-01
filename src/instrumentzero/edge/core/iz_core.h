#ifndef IZ_CORE_H
#define IZ_CORE_H
#include <stddef.h>
#include <stdint.h>
#define IZ_MAX_CHANNELS 3
#define IZ_MAX_TAPS 255
/* No heap, hidden globals, I/O, or platform clock in the numerical core. */
typedef struct {
    uint32_t channels, taps, decimation, position, phase;
    uint64_t samples;
    float scale[IZ_MAX_CHANNELS], offset[IZ_MAX_CHANNELS];
    float coefficients[IZ_MAX_TAPS];
    float history[IZ_MAX_CHANNELS][IZ_MAX_TAPS];
} iz_state;
enum { IZ_OK = 0, IZ_ARGUMENT = -1, IZ_CAPACITY = -2, IZ_NONFINITE = -3 };
size_t iz_state_bytes(void);
int iz_init(iz_state *, uint32_t channels, const float *scale, const float *offset,
            const float *coefficients, uint32_t taps, uint32_t decimation);
/* Interleaved frames. Output indices are input indices congruent to d-1 mod d.
 * Output capacity is frames, not floats. On failure state/output stay unchanged.
 * Zero startup state; caller must label/remove the first taps-1 input samples.
 */
int iz_process(iz_state *, const float *input, size_t frames, float *output,
               size_t capacity, size_t *written);
#endif
