#include "iz_core.h"
#include <float.h>

size_t iz_state_bytes(void) { return sizeof(iz_state); }
int iz_init(iz_state *s, uint32_t channels, const float *scale, const float *offset,
            const float *coefficients, uint32_t taps, uint32_t decimation) {
    if (!s || !scale || !offset || !coefficients || !channels || channels > IZ_MAX_CHANNELS ||
        !taps || taps > IZ_MAX_TAPS || !decimation || decimation > 8) return IZ_ARGUMENT;
    for (uint32_t c = 0; c < channels; c++)
        if (!__builtin_isfinite(scale[c]) || !__builtin_isfinite(offset[c]) ||
            scale[c] == 0 || scale[c] > 1000 || scale[c] < -1000 ||
            offset[c] > 1000 || offset[c] < -1000) return IZ_ARGUMENT;
    float l1 = 0;
    for (uint32_t k = 0; k < taps; k++) {
        if (!__builtin_isfinite(coefficients[k])) return IZ_ARGUMENT;
        l1 += coefficients[k] < 0 ? -coefficients[k] : coefficients[k];
    }
    if (!__builtin_isfinite(l1) || l1 > 8) return IZ_ARGUMENT;
    *s = (iz_state){0};
    s->channels = channels; s->taps = taps; s->decimation = decimation;
    for (uint32_t c = 0; c < channels; c++) { s->scale[c] = scale[c]; s->offset[c] = offset[c]; }
    for (uint32_t k = 0; k < taps; k++) s->coefficients[k] = coefficients[k];
    return IZ_OK;
}
int iz_process(iz_state *s, const float *input, size_t frames, float *output,
               size_t capacity, size_t *written) {
    if (!s || !written || (!input && frames) || (!output && capacity) ||
        !s->channels || s->channels > IZ_MAX_CHANNELS || !s->taps || s->taps > IZ_MAX_TAPS ||
        !s->decimation || s->decimation > 8 || s->position >= s->taps || s->phase >= s->decimation ||
        frames > 200000 || frames > SIZE_MAX / s->channels || frames > SIZE_MAX - s->phase ||
        s->samples > UINT64_MAX - frames) return IZ_ARGUMENT;
    size_t needed = (frames + s->phase) / s->decimation;
    if (capacity < needed || (!output && needed)) return IZ_CAPACITY;
    /* Bounded values prevent affine/FIR overflow; reject the entire input chunk. */
    for (size_t i = 0; i < frames * s->channels; i++)
        if (!__builtin_isfinite(input[i]) || input[i] > 1e6f || input[i] < -1e6f) return IZ_NONFINITE;
    size_t out = 0;
    for (size_t i = 0; i < frames; i++) {
        for (uint32_t c = 0; c < s->channels; c++)
            s->history[c][s->position] = (input[i*s->channels+c] - s->offset[c]) * s->scale[c];
        if (++s->phase == s->decimation) {
            s->phase = 0;
            for (uint32_t c = 0; c < s->channels; c++) {
                float y = 0;
                for (uint32_t k = 0; k < s->taps; k++) {
                    uint32_t p = (s->position + s->taps - k) % s->taps;
                    y += s->coefficients[k] * s->history[c][p];
                }
                output[out*s->channels+c] = y;
            }
            out++;
        }
        s->position = (s->position + 1) % s->taps;
        s->samples++;
    }
    *written = out;
    return IZ_OK;
}
