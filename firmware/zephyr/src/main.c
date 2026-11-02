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
#include "iz_control.h"
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
static uint8_t sid[16];
static iz_rx_ring uart_rx;
static iz_config current, pending;
static iz_control_guard control;
static uint8_t control_rx[IZ_CONFIG_MAX_BYTES];
static bool trigger_enabled;
static iz_state processor;
static uint32_t output_sequence;
BUILD_ASSERT(sizeof(current)+sizeof(pending)+sizeof(control_rx)+sizeof(uart_rx)+sizeof(control)+sizeof(sid)+IZ_ACK_BYTES <= IZ_CONTROL_RESERVE_BYTES);
static void uart_received(const struct device *dev, void *unused) {
    ARG_UNUSED(unused);
    while (uart_irq_update(dev) && uart_irq_rx_ready(dev)) {
        uint8_t bytes[32];
        int n=uart_fifo_read(dev,bytes,sizeof(bytes));
        if (n<=0) break;
        if (iz_rx_put(&uart_rx,bytes,(size_t)n)!=(size_t)n) {
            atomic_set(&fault,2);
            uart_irq_rx_disable(dev);
            break;
        }
    }
}
static void acquired(const struct device *dev, const struct sensor_trigger *unused) {
    ARG_UNUSED(unused);
    k_mutex_lock(&acquisition_lock,K_FOREVER);
    if (!atomic_get(&acquisition_active) || atomic_get(&fault)) goto done;
    if (source_sequence>=200000u) { atomic_set(&fault,2); goto done; }
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
    int rc=trigger_enabled ? sensor_trigger_set(accel,&trigger,NULL) : 0;
    if (!rc) trigger_enabled=false;
    k_msgq_purge(&samples);
    k_mutex_unlock(&acquisition_lock);
    return rc; /* A failed disable ends the program, never opens a new session. */
}
static void send_packet(struct sample *block, uint16_t n, uint16_t flags, uint8_t kind) {
    uint8_t packet[84 + IZ_BLOCK_SAMPLES * 8];
    memcpy(packet, "IZP1", 4); packet[4]=1; packet[5]=kind;
    sys_put_le16(flags, packet+6); memcpy(packet+8, sid, 16);
    sys_put_le32(control.epoch, packet+24); sys_put_le32(block[0].sequence, packet+28);
    sys_put_le64(block[0].us, packet+32); sys_put_le32(kind==3 ? current.rate_hz/current.decimation : current.rate_hz, packet+40);
    sys_put_le16(n, packet+44); sys_put_le16(1, packet+46); memcpy(packet+48, current.spec_sha256, 32);
    for (uint16_t i=0; i<n; i++) {
        sys_put_le32((uint32_t)(block[i].us-block[0].us),packet+80+4*i);
        uint32_t bits; memcpy(&bits, &block[i].z, 4);
        sys_put_le32(bits,packet+80+4*n+4*i);
    }
    size_t size=80+n*8;
    sys_put_le32(iz_crc32(packet,size),packet+size); size+=4;
    uint8_t length[4]; sys_put_le32(size,length);
    for (size_t i=0; i<4; i++) uart_poll_out(uart,length[i]);
    for (size_t i=0; i<size; i++) uart_poll_out(uart,packet[i]);
}
static void process_and_send(struct sample *block, uint16_t n, uint16_t flags) {
    if (current.mode==0 || current.flags || flags) send_packet(block,n,flags,1);
    if (current.mode==0 || flags) return;
    float input[IZ_BLOCK_SAMPLES], output[IZ_BLOCK_SAMPLES];
    for (uint16_t i=0;i<n;i++) input[i]=block[i].z;
    uint64_t before=processor.samples;
    size_t written=0;
    if (iz_process(&processor,input,n,output,IZ_BLOCK_SAMPLES,&written)) { atomic_set(&fault,2); return; }
    struct sample transformed[IZ_BLOCK_SAMPLES]; size_t j=0;
    for (uint16_t i=0;i<n;i++) {
        if (current.mode==1 || (before+i+1)%current.decimation==0) {
            transformed[j]=(struct sample){.us=block[i].us,.z=output[j],.sequence=output_sequence++}; j++;
        }
    }
    if (j!=written) { atomic_set(&fault,2); return; }
    if (j) send_packet(transformed,j,0,current.mode==1?2:3);
}
/* Reception owns every byte until its bounded deadline. Invalid frames cannot
 * turn embedded G/K/S characters into commands. A fresh configuration is needed
 * after every stop, timeout, rejection or start. */
static int receive_byte(uint8_t *out,int64_t deadline) {
    while (k_uptime_get()<deadline) {
        int rc=iz_rx_get(&uart_rx,out);
        if (rc==0) return 0;
        if (rc<0) return -EOVERFLOW;
        k_sleep(K_MSEC(1));
    }
    return -ETIMEDOUT;
}
static int configure_device(void) {
    if (stop_acquisition()) return -EIO;
    iz_control_stop(&control);
    pending=(iz_config){0};
    int64_t deadline=k_uptime_get()+500;
    uint8_t length[2];
    uint8_t status=IZ_CONFIG_TIMEOUT;
    size_t received=0;
    if (!receive_byte(length,deadline) && !receive_byte(length+1,deadline)) {
        uint16_t n=sys_get_le16(length);
        if (n<=IZ_CONFIG_MAX_BYTES && n>=IZ_CONFIG_HEADER_BYTES+4) {
            while (received<n && !receive_byte(control_rx+received,deadline)) received++;
            if (received==n) status=iz_control_stage(&control,&pending,control_rx,n,IZ_BLOCK_SAMPLES,IZ_QUEUE_BLOCKS);
        } else {
            /* Drain a rejected envelope until timeout, never parse its contents
             * as G/start or as another configuration transaction. */
            uint8_t ignored;
            while (!receive_byte(&ignored,deadline)) {}
            status=IZ_CONFIG_INVALID;
        }
    }
    if (status==IZ_CONFIG_OK) {
        const float unity=1.0f;
        int rc=iz_init(&processor,1,&pending.scale,&pending.offset,
                       pending.mode==2?pending.coefficients:&unity,
                       pending.mode==2?pending.taps:1,pending.mode==2?pending.decimation:1);
        struct sensor_value odr={.val1=pending.rate_hz};
        if (!rc) rc=sensor_attr_set(accel,SENSOR_CHAN_ACCEL_XYZ,SENSOR_ATTR_SAMPLING_FREQUENCY,&odr);
        if (rc) { status=IZ_CONFIG_INVALID; iz_control_stop(&control); }
        else {
            current=pending;
            sys_rand_get(sid,sizeof(sid)); sid[6]=(sid[6]&15)|64; sid[8]=(sid[8]&63)|128;
        }
    }
    if (status!=IZ_CONFIG_OK) {
        iz_control_stop(&control);
        pending=(iz_config){0};
        if (received>=12) pending.request_id=sys_get_le32(control_rx+8);
    }
    uint8_t ack[IZ_ACK_BYTES];
    iz_config_ack(ack,&pending,status,control.epoch,sid);
    for (size_t i=0;i<sizeof(ack);i++) uart_poll_out(uart,ack[i]);
    return 0;
}
int main(void) {
    if (!device_is_ready(accel) || !device_is_ready(uart)) return -ENODEV;
    if (uart_irq_callback_user_data_set(uart,uart_received,NULL)) return -ENOTSUP;
    uart_irq_rx_enable(uart);
    struct sample block[IZ_BLOCK_SAMPLES]; uint16_t count=0;
    int64_t last_heartbeat=0, configured_at=0;
    for (;;) {
        uint8_t command;
        if (atomic_load_explicit(&uart_rx.overflow,memory_order_acquire)) {
            iz_control_stop(&control); (void)stop_acquisition(); return -EOVERFLOW;
        }
        if (control.armed && k_uptime_get()-configured_at>2000) iz_control_stop(&control);
        while (iz_rx_get(&uart_rx,&command)==0) {
            if (control.armed && k_uptime_get()-configured_at>2000) iz_control_stop(&control);
            if (command=='S') {
                iz_control_stop(&control); count=0;
                if (stop_acquisition()) return -EIO;
            } else if (command=='C') {
                count=0;
                if (configure_device()) return -EIO;
                configured_at=k_uptime_get();
            } else if (command=='G' && iz_control_start(&control)==IZ_CONFIG_OK) {
                k_mutex_lock(&acquisition_lock,K_FOREVER);
                atomic_set(&fault,0); source_sequence=0; output_sequence=0; total_cycles=0;
                k_msgq_purge(&samples); previous_cycles=k_cycle_get_32();
                int rc=sensor_trigger_set(accel,&trigger,acquired);
                if (!rc) { trigger_enabled=true; atomic_set(&acquisition_active,1); }
                k_mutex_unlock(&acquisition_lock);
                if (rc) return -EIO;
                last_heartbeat=k_uptime_get();
            } else if (command=='K' && atomic_get(&acquisition_active)) last_heartbeat=k_uptime_get();
        }
        if (!atomic_get(&acquisition_active)) { k_sleep(K_MSEC(1)); continue; }
        if (k_uptime_get()-last_heartbeat>2000) {
            iz_control_stop(&control); count=0;
            if (stop_acquisition()) return -EIO;
            continue;
        }
        struct sample next;
        if (!k_msgq_get(&samples,&next,K_MSEC(10))) block[count++]=next;
        uint16_t error=atomic_get(&fault);
        if (count==IZ_BLOCK_SAMPLES || (error && count)) { process_and_send(block,count,error); count=0; }
        if (error) { (void)stop_acquisition(); return -EIO; }
        /* A silent/unplugged I2C sensor times out at host. No fabricated samples. */
    }
}
