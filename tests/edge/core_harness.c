#include "iz_core.h"
#include <assert.h>
#include <math.h>
#include <string.h>
int main(void) {
    iz_state state, backup;
    float scale[3] = {1, -1, 2}, offset[3] = {0, .1f, -.2f};
    float taps[3] = {.25f, .5f, .25f};
    float input[771], output[771];
    size_t written = 17;
    for (size_t i = 0; i < 771; i++) input[i] = (float)(i % 31) * .001f;
    assert(iz_init(&state, 3, scale, offset, taps, 3, 4) == 0);
    backup = state;
    assert(iz_process(&state, input, 257, output, 0, &written) == IZ_CAPACITY);
    assert(!memcmp(&backup, &state, sizeof(state)) && written == 17);
    for (unsigned int k = 0; k < 2000; k++) {
        assert(iz_process(&state, input, k % 258, output, 257, &written) == 0);
        for (size_t i = 0; i < written * 3; i++) assert(isfinite(output[i]));
    }
    backup = state;
    input[3] = NAN;
    assert(iz_process(&state, input, 2, output, 257, &written) == IZ_NONFINITE);
    assert(!memcmp(&backup, &state, sizeof(state)));
    assert(iz_process(&state, NULL, 0, NULL, 0, &written) == 0 && written == 0);
    assert(iz_init(&state, 4, scale, offset, taps, 3, 4) == IZ_ARGUMENT);
    return 0;
}
