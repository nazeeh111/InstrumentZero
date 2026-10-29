// C++17 consumer of the reviewed C99 numerical API. No hardware or heap.
extern "C" {
#include "iz_core.h"
}
#include <cassert>
int main() {
    iz_state state;
    const float gain[] = {1.0f}, offset[] = {0.0f}, coefficients[] = {1.0f};
    const float input[] = {0.0f, 1.0f, -1.0f};
    float output[3] = {};
    size_t written = 0;
    assert(iz_init(&state, 1, gain, offset, coefficients, 1, 1) == IZ_OK);
    assert(iz_process(&state, input, 3, output, 3, &written) == IZ_OK);
    assert(written == 3 && output[1] == 1.0f && output[2] == -1.0f);
}
