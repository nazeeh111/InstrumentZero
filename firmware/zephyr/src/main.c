/* InstrumentZero Edge provisional ADXL345 adapter. Never flashed by build scripts.
 * Zephyr's mature driver performs interrupt/bus work. Its callback runs in the
 * driver's acquisition thread, timestamps BEFORE reading the sample, and only
 * enqueues bounded samples. Main thread handles packet encoding and UART.
 * Timestamp is callback time, not the physical MEMS sampling aperture. Driver
 * IRQ masking/FIFO behavior can lose samples; timing validation must reject gaps.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/random/random.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/reboot.h>
#include <string.h>
#include <math.h>
#include "generated.h"
#include "iz_core.h"
BUILD_ASSERT(IZ_CHANNELS == 1, "Provisional sensor adapter exposes z only");
BUILD_ASSERT(IZ_ADAPTER_KIND == 2, "Sensor firmware needs a zephyr_adxl345 specification");
BUILD_ASSERT(IZ_BLOCK_SAMPLES <= 64, "Larger blocks require a separately reviewed stack/memory binding");
BUILD_ASSERT(IZ_RATE_HZ == 100 || IZ_RATE_HZ == 200 || IZ_RATE_HZ == 400);
struct sample { uint64_t us; float z; uint32_t sequence; };
K_MSGQ_DEFINE(samples, sizeof(struct sample), IZ_BLOCK_SAMPLES * IZ_QUEUE_BLOCKS, 8);
static const struct device *accel = DEVICE_DT_GET(DT_ALIAS(iz_accelerometer));
static const struct device *uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static atomic_t fault;
static atomic_t acquisition_active;
K_MUTEX_DEFINE(acquisition_lock);
static uint32_t source_sequence, previous_cycles;
static uint64_t total_cycles;
static struct sensor_trigger trigger = { .type = SENSOR_TRIG_DATA_READY, .chan = SENSOR_CHAN_ACCEL_XYZ };
static uint8_t sid[16], hash[32];
#if IZ_MODE > 0
static iz_state processor;
static uint32_t output_sequence;
#endif
static uint32_t crc32(const uint8_t *data, size_t n) {
    uint32_t c = 0xffffffffu;
    for (size_t i = 0; i < n; i++) {
        c ^= data[i];
        for (unsigned b = 0; b < 8; b++) c = (c >> 1) ^ (0xedb88320u & (0u-(c&1)));
    }
    return ~c;
}
static void acquired(const struct device *dev, const struct sensor_trigger *unused) {
    ARG_UNUSED(unused);
    k_mutex_lock(&acquisition_lock,K_FOREVER);
    if (!atomic_get(&acquisition_active) || atomic_get(&fault)) goto done;
    uint32_t cycles = k_cycle_get_32();
    if ((uint32_t)(cycles-previous_cycles)>=0x80000000u) { atomic_set(&fault,2); goto done; }
    total_cycles += (uint32_t)(cycles - previous_cycles);
    previous_cycles = cycles;
    struct sample s = { .us = k_cyc_to_us_floor64(total_cycles), .sequence = source_sequence++ };
    struct sensor_value value;
    if (sensor_sample_fetch(dev) || sensor_channel_get(dev, SENSOR_CHAN_ACCEL_Z, &value)) { atomic_set(&fault, 2); goto done; }
    s.z = sensor_value_to_double(&value);
    /* ADXL345 driver's full-resolution hardware range must be checked physically.
     * ±2g is the conservative software clipping threshold for this provisional binding.
     */
    if (!isfinite(s.z) || fabsf(s.z) >= 19.5936867f) { atomic_set(&fault, 1); goto done; }
    if (k_msgq_put(&samples, &s, K_NO_WAIT)) atomic_set(&fault, 2);
done:
    k_mutex_unlock(&acquisition_lock);
}
static int stop_acquisition(void) {
    atomic_set(&acquisition_active,0);
    /* Wait for an in-flight driver-thread fetch before touching driver state or
     * resetting counters. Later callbacks see the inactive gate under this lock.
     */
    k_mutex_lock(&acquisition_lock,K_FOREVER);
    int rc=sensor_trigger_set(accel,&trigger,NULL);
    k_msgq_purge(&samples);
    k_mutex_unlock(&acquisition_lock);
    return rc; /* A failed disable ends the program, never opens a new session. */
}
static void send_packet(struct sample *block, uint16_t n, uint16_t flags, uint8_t kind) {
    uint8_t packet[84 + IZ_BLOCK_SAMPLES * 8];
    memcpy(packet, "IZP1", 4); packet[4]=1; packet[5]=kind;
    sys_put_le16(flags, packet+6); memcpy(packet+8, sid, 16);
    sys_put_le32(0, packet+24); sys_put_le32(block[0].sequence, packet+28);
    sys_put_le64(block[0].us, packet+32); sys_put_le32(kind==3 ? IZ_RATE_HZ/IZ_DECIMATION : IZ_RATE_HZ, packet+40);
    sys_put_le16(n, packet+44); sys_put_le16(1, packet+46); memcpy(packet+48, hash, 32);
    for (uint16_t i=0; i<n; i++) {
        sys_put_le32((uint32_t)(block[i].us-block[0].us),packet+80+4*i);
        uint32_t bits; memcpy(&bits, &block[i].z, 4);
        sys_put_le32(bits,packet+80+4*n+4*i);
    }
    size_t size=80+n*8;
    sys_put_le32(crc32(packet,size),packet+size); size+=4;
    uint8_t length[4]; sys_put_le32(size,length);
    for (size_t i=0; i<4; i++) uart_poll_out(uart,length[i]);
    for (size_t i=0; i<size; i++) uart_poll_out(uart,packet[i]);
}
static void process_and_send(struct sample *block, uint16_t n, uint16_t flags) {
    if (IZ_MODE==0 || IZ_RAW_VALIDATION || flags) send_packet(block,n,flags,1);
#if IZ_MODE > 0
    if (IZ_MODE==0 || flags) return;
    float input[IZ_BLOCK_SAMPLES], output[IZ_BLOCK_SAMPLES];
    for (uint16_t i=0;i<n;i++) input[i]=block[i].z;
    uint64_t before=processor.samples;
    size_t written=0;
    if (iz_process(&processor,input,n,output,IZ_BLOCK_SAMPLES,&written)) { atomic_set(&fault,2); return; }
    struct sample transformed[IZ_BLOCK_SAMPLES]; size_t j=0;
    for (uint16_t i=0;i<n;i++) {
        if (IZ_MODE==1 || (before+i+1)%IZ_DECIMATION==0) {
            transformed[j]=(struct sample){.us=block[i].us,.z=output[j],.sequence=output_sequence++}; j++;
        }
    }
    if (j!=written) { atomic_set(&fault,2); return; }
    if (j) send_packet(transformed,j,0,IZ_MODE==1?2:3);
#endif
}
int main(void) {
    if (!device_is_ready(accel) || !device_is_ready(uart)) return -ENODEV;
    for (size_t i=0;i<32;i++) {
        unsigned a=IZ_SPEC_SHA256[2*i],b=IZ_SPEC_SHA256[2*i+1];
        hash[i]=((a<='9'?a-'0':a-'a'+10)<<4)|(b<='9'?b-'0':b-'a'+10);
    }
    sys_rand_get(sid,sizeof(sid)); sid[6]=(sid[6]&15)|64; sid[8]=(sid[8]&63)|128;
restart_session:
    while (true) { uint8_t command; if (!uart_poll_in(uart,&command) && command=='G') break; k_sleep(K_MSEC(10)); }
    k_mutex_lock(&acquisition_lock,K_FOREVER);
    atomic_set(&fault,0); source_sequence=0; total_cycles=0; k_msgq_purge(&samples);
    sys_rand_get(sid,sizeof(sid)); sid[6]=(sid[6]&15)|64; sid[8]=(sid[8]&63)|128;
    previous_cycles=k_cycle_get_32();
#if IZ_MODE > 0
    output_sequence=0;
    const float unity=1.0f;
    if (iz_init(&processor,1,iz_scale,iz_offset,IZ_MODE==2?iz_coefficients:&unity,IZ_MODE==2?IZ_TAPS:1,IZ_MODE==2?IZ_DECIMATION:1)) { k_mutex_unlock(&acquisition_lock); return -EINVAL; }
#endif
    struct sensor_value odr={.val1=IZ_RATE_HZ};
    int start_error=sensor_attr_set(accel,SENSOR_CHAN_ACCEL_XYZ,SENSOR_ATTR_SAMPLING_FREQUENCY,&odr);
    if (!start_error) start_error=sensor_trigger_set(accel,&trigger,acquired);
    if (!start_error) atomic_set(&acquisition_active,1);
    k_mutex_unlock(&acquisition_lock);
    if (start_error) return -EIO;
    struct sample block[IZ_BLOCK_SAMPLES]; uint16_t count=0;
    int64_t last_heartbeat=k_uptime_get();
    for (;;) {
        uint8_t command;
        while (!uart_poll_in(uart,&command)) {
            if (command=='K') last_heartbeat=k_uptime_get();
            if (command=='S') { if (stop_acquisition()) return -EIO; goto restart_session; }
        }
        if (k_uptime_get()-last_heartbeat>2000) { if (stop_acquisition()) return -EIO; goto restart_session; }
        struct sample next;
        if (!k_msgq_get(&samples,&next,K_MSEC(100))) block[count++]=next;
        uint16_t error=atomic_get(&fault);
        if (count==IZ_BLOCK_SAMPLES || (error && count)) { process_and_send(block,count,error); count=0; }
        if (error) { (void)stop_acquisition(); return -EIO; }
        /* A silent/unplugged I2C sensor times out at host. Reboot/reconnect yields
         * a new UUID. No fabricated timestamps or padded samples are emitted.
         */
    }
}
