#include "iz_control.h"
static uint16_t get16(const uint8_t *p) { return (uint16_t)p[0] | (uint16_t)p[1]<<8; }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static void put32(uint8_t *p,uint32_t v) { for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i)); }
static float get_float(const uint8_t *p) { union { uint32_t u; float f; } bits={.u=get32(p)}; return bits.f; }
uint32_t iz_crc32(const uint8_t *p,size_t n) {
    uint32_t c=0xffffffffu;
    for (size_t i=0;i<n;i++) {
        c^=p[i];
        for (unsigned b=0;b<8;b++) c=(c>>1)^(0xedb88320u&(0u-(c&1)));
    }
    return ~c;
}
int iz_config_decode(iz_config *out,const uint8_t *p,size_t n,uint16_t block,uint16_t queue) {
    if (!out || !p || n<IZ_CONFIG_HEADER_BYTES+4 || n>IZ_CONFIG_MAX_BYTES ||
        p[0]!='I' || p[1]!='Z' || p[2]!='C' || p[3]!='1' || p[4]!=1 || p[5]!=1 ||
        get16(p+6)>1 || iz_crc32(p,n-4)!=get32(p+n-4)) return IZ_CONFIG_INVALID;
    iz_config c={0};
    c.flags=get16(p+6); c.request_id=get32(p+8); c.rate_hz=get32(p+12);
    c.block_samples=get16(p+16); c.queue_blocks=get16(p+18); c.taps=get16(p+20);
    c.decimation=p[22]; c.mode=p[23];
    if ((c.rate_hz!=100 && c.rate_hz!=200 && c.rate_hz!=400) ||
        !block || block>64 || !queue || queue>64 || c.block_samples!=block || c.queue_blocks!=queue ||
        c.taps<3 || c.taps>IZ_CONFIG_MAX_TAPS || !(c.taps&1) ||
        (c.decimation!=1 && c.decimation!=2 && c.decimation!=4 && c.decimation!=8) ||
        c.rate_hz%c.decimation || c.mode>2 || n!=IZ_CONFIG_HEADER_BYTES+4*c.taps+4) return IZ_CONFIG_INVALID;
    for (unsigned i=0;i<32;i++) c.spec_sha256[i]=p[24+i];
    c.scale=get_float(p+56); c.offset=get_float(p+60);
    /* bytes64..67 reserved for forward-compatible framing; must be zero. */
    if (get32(p+64) || !__builtin_isfinite(c.scale) || !__builtin_isfinite(c.offset) ||
        c.scale==0 || c.scale < -1000 || c.scale > 1000 || c.offset < -1000 || c.offset > 1000) return IZ_CONFIG_INVALID;
    float l1=0;
    for (unsigned i=0;i<c.taps;i++) {
        c.coefficients[i]=get_float(p+IZ_CONFIG_HEADER_BYTES+4*i);
        if (!__builtin_isfinite(c.coefficients[i])) return IZ_CONFIG_INVALID;
        l1+=c.coefficients[i]<0?-c.coefficients[i]:c.coefficients[i];
    }
    if (!__builtin_isfinite(l1) || l1>8) return IZ_CONFIG_INVALID;
    *out=c;
    return IZ_CONFIG_OK;
}
void iz_config_ack(uint8_t p[IZ_ACK_BYTES],const iz_config *c,uint8_t status,uint32_t epoch,const uint8_t sid[16]) {
    for (unsigned i=0;i<IZ_ACK_BYTES;i++) p[i]=0;
    p[0]='I';p[1]='Z';p[2]='A';p[3]='1';p[4]=1;p[5]=status;
    p[6]=c->mode;p[7]=(uint8_t)c->flags;put32(p+8,c->request_id);put32(p+12,epoch);
    for (unsigned i=0;i<16;i++) p[16+i]=sid[i];
    for (unsigned i=0;i<32;i++) p[32+i]=c->spec_sha256[i];
    put32(p+64,iz_crc32(p,64));
}

int iz_control_stage(iz_control_guard *g,iz_config *out,const uint8_t *p,size_t n,uint16_t block,uint16_t queue) {
    if (!g) return IZ_CONFIG_INVALID;
    g->armed=0;
    if (g->epoch==UINT32_MAX) return IZ_CONFIG_EPOCH;
    int rc=iz_config_decode(out,p,n,block,queue);
    if (rc) return rc;
    g->epoch++;g->armed=1;
    return IZ_CONFIG_OK;
}
int iz_control_start(iz_control_guard *g) {
    if (!g || !g->armed) return IZ_CONFIG_INVALID;
    g->armed=0;
    return IZ_CONFIG_OK;
}
void iz_control_stop(iz_control_guard *g) { if (g) g->armed=0; }

size_t iz_rx_put(iz_rx_ring *r,const uint8_t *p,size_t n) {
    if (!r || (!p && n) || atomic_load_explicit(&r->overflow,memory_order_acquire)) return 0;
    uint32_t w=atomic_load_explicit(&r->written,memory_order_relaxed);
    uint32_t used=w-atomic_load_explicit(&r->read,memory_order_acquire);
    if (used>IZ_RX_CAPACITY || n>IZ_RX_CAPACITY-used) {
        atomic_store_explicit(&r->overflow,1,memory_order_release);return 0;
    }
    for (size_t i=0;i<n;i++) r->bytes[(w+i)&(IZ_RX_CAPACITY-1)]=p[i];
    atomic_store_explicit(&r->written,w+(uint32_t)n,memory_order_release);
    return n;
}
int iz_rx_get(iz_rx_ring *r,uint8_t *out) {
    if (!r || !out || atomic_load_explicit(&r->overflow,memory_order_acquire)) return -1;
    uint32_t read=atomic_load_explicit(&r->read,memory_order_relaxed);
    uint32_t used=atomic_load_explicit(&r->written,memory_order_acquire)-read;
    if (!used) return 1;
    if (used>IZ_RX_CAPACITY) { atomic_store_explicit(&r->overflow,1,memory_order_release);return -1; }
    *out=r->bytes[read&(IZ_RX_CAPACITY-1)];
    atomic_store_explicit(&r->read,read+1,memory_order_release);
    return 0;
}
