#include "iz_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t wire[3+IZ_CONFIG_MAX_BYTES+1], changed[IZ_RX_CAPACITY+IZ_CONFIG_MAX_BYTES+1];
static void crc(uint8_t *p,size_t n) {
    uint32_t c=iz_crc32(p,n-4);
    for (unsigned b=0;b<4;b++) p[n-4+b]=(uint8_t)(c>>(b*8));
}
int main(int argc,char **argv) {
    assert(argc==4);
    iz_control_guard guard={0};
    iz_config config={0};
    uint8_t sid[16]={1},ack[IZ_ACK_BYTES];
    for (unsigned mode=0;mode<3;mode++) {
        FILE *f=fopen(argv[mode+1],"rb"); assert(f);
        size_t count=fread(wire,1,sizeof(wire),f); assert(!ferror(f)); fclose(f);
        assert(count>3 && count<=IZ_CONFIG_MAX_BYTES+3 && wire[0]=='C');
        const uint8_t *p=wire+3;size_t n=count-3;
        assert(iz_control_stage(&guard,&config,p,n,64,4)==0);
        assert(config.mode==mode && guard.epoch==mode+1 && guard.armed);
        iz_config_ack(ack,&config,0,guard.epoch,sid);
        assert(iz_crc32(ack,64)==((uint32_t)ack[64]|(uint32_t)ack[65]<<8|(uint32_t)ack[66]<<16|(uint32_t)ack[67]<<24));
        assert(iz_control_start(&guard)==0 && !guard.armed);
        assert(iz_control_start(&guard)==1);
        iz_config before=config;
        for (size_t length=0;length<=IZ_CONFIG_MAX_BYTES+1;length++) {
            if (length==n) continue;
            assert(iz_config_decode(&config,p,length<n?length:n-1,64,4)!=0);
            assert(!memcmp(&config,&before,sizeof(config)));
        }
        for (size_t i=0;i<n-4;i++) {
            memcpy(changed,p,n);changed[i]^=0x80;
            assert(iz_config_decode(&config,changed,n,64,4)!=0);
            assert(!memcmp(&config,&before,sizeof(config)));
            crc(changed,n);
            (void)iz_config_decode(&config,changed,n,64,4); /* CRC-valid bounds mutation sweep. */
            config=before;
        }
        for (size_t nbad=0;nbad<IZ_CONFIG_MAX_BYTES+1;nbad++) {
            memset(changed,0xa5,sizeof(changed));
            assert(iz_control_stage(&guard,&config,changed,nbad,64,4)!=0);
            assert(!guard.armed && !memcmp(&config,&before,sizeof(config)));
        }
    }
    iz_rx_ring ring={0};uint8_t value;
    for (unsigned burst=0;burst<2000;burst++) {
        uint8_t expected[32];
        for (unsigned i=0;i<32;i++) expected[i]=(uint8_t)(burst+i);
        assert(iz_rx_put(&ring,expected,32)==32);
        for (unsigned i=0;i<32;i++) { assert(!iz_rx_get(&ring,&value)); assert(value==expected[i]); }
        assert(iz_rx_get(&ring,&value)==1);
    }
    atomic_store(&ring.read,UINT32_MAX-2);atomic_store(&ring.written,UINT32_MAX-2);
    assert(iz_rx_put(&ring,wire,5)==5);
    for (unsigned i=0;i<5;i++) { assert(!iz_rx_get(&ring,&value)); assert(value==wire[i]); }
    assert(iz_rx_put(&ring,changed,IZ_RX_CAPACITY)==IZ_RX_CAPACITY);
    assert(!iz_rx_put(&ring,wire,1) && iz_rx_get(&ring,&value)==-1);
    guard.epoch=UINT32_MAX;guard.armed=1;
    assert(iz_control_stage(&guard,&config,wire+3,1,64,4)==IZ_CONFIG_EPOCH && !guard.armed);
    assert(iz_config_decode(NULL,wire,1,64,4)!=0);
    assert(iz_config_decode(&config,NULL,1,64,4)!=0);
    return 0;
}
