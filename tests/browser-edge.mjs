/** UI epoch/invalidation checks against production edge.js; generated DOM/network only. */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../src/instrumentzero/web/edge.js',import.meta.url),'utf8');
const defaultSpec=()=>({source:{rate_hz:400},dsp:{decimation:4},resources:{raw_validation:false,link_bytes_per_second:4000}});
const response=value=>({ok:true,json:async()=>value});
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function bundle(){return {artifact_url:'/api/edge/artifact?id=fixture',compiled:{spec_sha256:'a'.repeat(64)},plot:{signal:[0,1,0],time_seconds:[0,1,2],unit:'m/s^2'},comparisons:['raw_host','calibrated_edge','filtered_edge'].map((mode,i)=>({mode,selected:i===2,result:{frequency_hz:17.25,frequency_resolution_clock_envelope_hz:.13,damping_ratio:.006,reasons:[],damping_rejection_reasons:[],status:'accepted_model_fit'},metrics:{wire_bytes_including_headers:i===2?100:300,processing_wall_seconds:.01},frequency_disagreement_hz:1e-8,resource_model:{legal_under_declared_model:true,reasons:[]}}))};}
function harness(runFetch=async()=>response(bundle()),initialFetch=async()=>response(defaultSpec())){
 const elements=new Map(),requests=[];
 function item(id){if(elements.has(id))return elements.get(id);const listeners=new Map();const e={value:'',checked:false,disabled:false,hidden:false,style:{},listeners,children:[],textContent:'',addEventListener(type,cb){listeners.set(type,cb);},removeAttribute(key){delete this[key];},setAttribute(key,v){this[key]=v;},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;}};elements.set(id,e);return e;}
 for(const [id,value]of Object.entries({scenario:'mount_a',duration:'8',decimation:'4',bandwidth:'4000'}))item(id).value=value;
 const context={AbortController,document:{getElementById:item,createElement:()=>item(Symbol()),createElementNS:()=>item(Symbol())},fetch:async(url,options)=>{if(url==='/api/edge/spec')return initialFetch();requests.push({url,payload:JSON.parse(options.body)});return runFetch();}};
 vm.createContext(context);vm.runInContext(source,context,{filename:'edge.js'});
 return {item,requests,dispatch(id,type='click'){const handler=item(id).listeners.get(type);assert.equal(typeof handler,'function');return handler({preventDefault(){}});}};
}
test('editing JSON then changing scenario cannot run an unapplied old specification',async()=>{
 const h=harness();await flush();h.item('spec-json').value=JSON.stringify({...defaultSpec(),schema:'changed'});h.dispatch('spec-json','input');h.item('scenario').value='mount_b';h.dispatch('scenario','change');assert.equal(h.item('run').disabled,true);await h.dispatch('experiment-form','submit');assert.equal(h.requests.length,0);
 h.dispatch('apply-spec');assert.equal(h.item('run').disabled,false);await h.dispatch('experiment-form','submit');assert.equal(h.requests[0].payload.spec.schema,'changed');
});
test('basic controls preserve unapplied specification text',async()=>{
 const h=harness();await flush();h.item('spec-json').value='unsaved exact text';h.dispatch('spec-json','input');h.item('decimation').value='2';h.dispatch('decimation','change');assert.equal(h.item('spec-json').value,'unsaved exact text');assert.equal(h.item('run').disabled,true);
});
test('new epoch clears result and export; late old response cannot repopulate either',async()=>{
 let resolve;const deferred=new Promise(r=>{resolve=r;});const h=harness(()=>deferred);await flush();const pending=h.dispatch('experiment-form','submit');h.item('scenario').value='silence';h.dispatch('scenario','change');resolve(response(bundle()));await pending;assert.equal(h.item('result').hidden,true);assert.equal(h.item('comparison').hidden,true);assert.equal(h.item('export').href,undefined);assert.equal(h.item('run').disabled,false);
});
test('loaded export belongs to loaded configuration and clears on edits',async()=>{
 const h=harness();await flush();await h.dispatch('experiment-form','submit');assert.equal(h.item('export').href,'/api/edge/artifact?id=fixture');assert.equal(h.item('frequency').textContent,'17.2500');h.item('raw-validation').checked=true;h.dispatch('raw-validation','change');assert.equal(h.item('export').href,undefined);assert.equal(h.item('result').hidden,true);
});
test('server rejection keeps export unavailable and allows recovery',async()=>{
 const h=harness(async()=>({ok:false,json:async()=>({error:'Samples clip the declared input range.'})}));await flush();await h.dispatch('experiment-form','submit');assert.match(h.item('status').textContent,/clip/);assert.equal(h.item('export').href,undefined);assert.equal(h.item('run').disabled,false);
});

test('a delayed initial specification cannot replace locally applied JSON',async()=>{
 let resolve;const initial=new Promise(r=>{resolve=r;});const h=harness(undefined,()=>initial);
 const edited={...defaultSpec(),schema:'owned-local-edit'};h.item('spec-json').value=JSON.stringify(edited);h.dispatch('spec-json','input');h.dispatch('apply-spec');
 resolve(response(defaultSpec()));await flush();assert.match(h.item('spec-json').value,/owned-local-edit/);await h.dispatch('experiment-form','submit');assert.equal(h.requests[0].payload.spec.schema,'owned-local-edit');
});
test('a delayed initial specification cannot erase unapplied JSON or enable Run',async()=>{
 let resolve;const initial=new Promise(r=>{resolve=r;});const h=harness(undefined,()=>initial);h.item('spec-json').value='unapplied text';h.dispatch('spec-json','input');resolve(response(defaultSpec()));await flush();assert.equal(h.item('spec-json').value,'unapplied text');assert.equal(h.item('run').disabled,true);
});
