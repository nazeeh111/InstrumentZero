from pathlib import Path
from fractions import Fraction
from math import lcm,ceil
from copy import deepcopy
import ctypes,json,struct,subprocess,tempfile,shutil,zlib
from instrumentzero.edge.control import configuration,decode_configuration
from instrumentzero.edge.spec import compile_graph,EdgeError
from instrumentzero.edge.planner import plan,measure_costs

class Config(ctypes.Structure):
    _fields_=[('request_id',ctypes.c_uint32),('rate_hz',ctypes.c_uint32),('flags',ctypes.c_uint16),('block_samples',ctypes.c_uint16),('queue_blocks',ctypes.c_uint16),('taps',ctypes.c_uint16),('decimation',ctypes.c_uint8),('mode',ctypes.c_uint8),('spec_sha256',ctypes.c_uint8*32),('scale',ctypes.c_float),('offset',ctypes.c_float),('coefficients',ctypes.c_float*255)]
root=Path.cwd();out=Path(tempfile.mkdtemp(prefix='iz-review-rc3-uart-'))
subprocess.run([shutil.which('clang'),'-std=c11','-O2','-shared','-fPIC',str(root/'src/instrumentzero/edge/control/iz_control.c'),'-o',str(out/'control.so')],check=True)
lib=ctypes.CDLL(str(out/'control.so'));lib.iz_config_decode.argtypes=[ctypes.POINTER(Config),ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint16,ctypes.c_uint16]
spec=json.loads((root/'examples/edge/adxl345-spec.json').read_text());spec['resources'].update(link_bytes_per_second=1e9,max_latency_ms=10000)
template,_=configuration(spec,'raw_host',request_id=1)
checks=0;admitted=0
for rate in (100,200,400):
    for b in range(1,65):
        for d in (1,2,4,8):
            if rate%d:continue
            for mode in (0,1,2):
                for raw in (0,1):
                    wire_d=d if mode==2 else 1
                    # Enumerate real send decisions over an exact repeating period.
                    period=lcm(b,wire_d);byte_count=0;send_ends=[]
                    for end in range(b,period+1,b):
                        count=end//wire_d-(end-b)//wire_d
                        if count:
                            byte_count+=88+count*8;send_ends.append(end)
                        if mode and raw:byte_count+=88+b*8
                    required=Fraction(byte_count*rate,period)
                    expected=required<=115200//10
                    packet_stride=max([send_ends[0]+period-send_ends[-1],*[y-x for x,y in zip(send_ends,send_ends[1:])]])
                    assert packet_stride==b*ceil(wire_d/b)
                    request=bytearray(template)
                    struct.pack_into('<H',request,9,raw);struct.pack_into('<I',request,15,rate);struct.pack_into('<H',request,19,b);request[25]=d;request[26]=mode
                    request[-4:]=struct.pack('<I',zlib.crc32(request[3:-4]))
                    c_result=lib.iz_config_decode(ctypes.byref(Config()),bytes(request[3:]),len(request)-3,b,4)==0
                    try:decode_configuration(bytes(request));py_result=True
                    except EdgeError:py_result=False
                    assert expected==c_result==py_result,(rate,b,d,mode,raw,str(required),expected,c_result,py_result)
                    checks+=1;admitted+=expected

# Exercise the public graph/controller path for the originally unsafe case.
s=deepcopy(spec);s['resources']['block_samples']=1
for mode,expected_bps,expected_valid in [('raw_host',38400,False),('filtered_edge',9600,True)]:
    compiled=compile_graph(s);model=plan(compiled,measure_costs(compiled));candidate=next(c for c in model['candidates'] if c['mode']==mode)
    assert candidate['estimated_transfer_bytes_per_second']==expected_bps
    assert candidate['legal_under_declared_model']==expected_valid
    try:configuration(s,mode,request_id=42);valid=True
    except EdgeError:valid=False
    assert valid==expected_valid
    assert model['effective_link_bytes_per_second']==11520
# Other adapter budgets stay virtual and uncapped.
s['source']['adapter']='simulated';model=plan(compile_graph(s),measure_costs(compile_graph(s)))
assert model['effective_link_bytes_per_second']==1e9 and model['candidates'][0]['legal_under_declared_model']
report={'binary_control_cases':checks,'admitted_cases':admitted,'reference':'exact rational bytes from enumerated repeating firmware send schedules','public_raw_38400_rejected':True,'public_filtered_9600_admitted':True,'simulated_budget_uncapped':True,'packet_wait_stride_exact_for_all_cases':True,'hardware_accessed':False}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));print('Evidence:',out)
