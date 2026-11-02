#ifndef IZ_CONTROL_H
#define IZ_CONTROL_H
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>
#define IZ_CONFIG_HEADER_BYTES 68u
#define IZ_CONFIG_MAX_BYTES 1092u
#define IZ_ACK_BYTES 68u
/* Accounts for active + pending configurations, RX frame and ACK workspace.
 * The processing state is reserved separately, in every runtime placement. */
#define IZ_CONTROL_RESERVE_BYTES 6144u
#define IZ_CONFIG_MAX_TAPS 255u
#define IZ_UART_BYTES_PER_SECOND 11520u /* 115200 baud, 8N1 nominal upper bound only. */
#define IZ_RX_CAPACITY 2048u
typedef struct {
    _Atomic uint32_t read, written, overflow;
    uint8_t bytes[IZ_RX_CAPACITY];
} iz_rx_ring;
/* One UART ISR producer and one main-thread consumer. Overflow poisons the
 * stream; do not reset a live ring or treat its remaining bytes as commands. */
size_t iz_rx_put(iz_rx_ring *, const uint8_t *, size_t);
int iz_rx_get(iz_rx_ring *, uint8_t *); /* 0=byte, 1=empty, -1=poisoned */
typedef struct {
    uint32_t request_id, rate_hz;
    uint16_t flags, block_samples, queue_blocks, taps;
    uint8_t decimation, mode, spec_sha256[32];
    float scale, offset, coefficients[IZ_CONFIG_MAX_TAPS];
} iz_config;
typedef struct { uint32_t epoch; uint8_t armed; } iz_control_guard;
int iz_control_stage(iz_control_guard *, iz_config *, const uint8_t *, size_t, uint16_t block, uint16_t queue);
int iz_control_start(iz_control_guard *);
void iz_control_stop(iz_control_guard *);
enum { IZ_CONFIG_OK=0, IZ_CONFIG_INVALID=1, IZ_CONFIG_TIMEOUT=2, IZ_CONFIG_EPOCH=3 };
uint32_t iz_crc32(const uint8_t *, size_t);
/* Transactional: invalid input never modifies destination. This checks the
 * device envelope, not full JSON graph/filter response or physical calibration. */
int iz_config_decode(iz_config *, const uint8_t *, size_t, uint16_t block, uint16_t queue);
void iz_config_ack(uint8_t out[IZ_ACK_BYTES], const iz_config *, uint8_t status,
                   uint32_t epoch, const uint8_t session[16]);
#endif
