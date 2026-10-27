/** No hardware acceptance claim: these are synthetic software fixtures and mocked async device APIs.
 * Run: node --test tests/browser-acquisition.mjs
 * Optional historical regression check: INSTRUMENTZERO_TEST_APP_REF=<commit> node --test ...
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const acq = require('../src/instrumentzero/web/acquisition.js');
const web = new URL('../src/instrumentzero/web/', import.meta.url);
const appSource = process.env.INSTRUMENTZERO_TEST_APP_REF
  ? execFileSync('git', ['show', `${process.env.INSTRUMENTZERO_TEST_APP_REF}:src/instrumentzero/web/app.js`], {encoding:'utf8'})
  : readFileSync(new URL('app.js', web), 'utf8');

function deferred() { let resolve, reject; const promise = new Promise((yes, no) => {resolve=yes;reject=no;}); return {promise,resolve,reject}; }
async function flush() { for (let i=0;i<12;i++) await Promise.resolve(); }
function stream() { const track={stops:0,stop(){this.stops++;}}; return {track,getTracks:()=>[track]}; }
function frame(width=160,height=120,background=220) {
  const data=new Uint8ClampedArray(width*height*4);
  for(let i=0;i<data.length;i+=4){data[i]=data[i+1]=data[i+2]=background;data[i+3]=255;}
  return {width,height,data};
}
function rectangle(image,x,y,width,height,gray=15,alpha=255) {
  for(let yy=y;yy<y+height;yy++)for(let xx=x;xx<x+width;xx++){
    const i=(yy*image.width+xx)*4;image.data[i]=image.data[i+1]=image.data[i+2]=gray;image.data[i+3]=alpha;
  }
  return image;
}
function crop(image,roi) {
  const rgba=new Uint8ClampedArray(roi.width*roi.height*4);
  for(let y=0;y<roi.height;y++)for(let x=0;x<roi.width;x++){
    const xx=Math.floor(roi.x+x),yy=Math.floor(roi.y+y);
    if(xx>=0&&xx<image.width&&yy>=0&&yy<image.height)rgba.set(image.data.subarray((yy*image.width+xx)*4,(yy*image.width+xx)*4+4),(y*roi.width+x)*4);
  }
  return rgba;
}
function locate(image,previous){const roi=acq.markerROI(image.width,image.height,previous);return roi?acq.locateDarkMarker(crop(image,roi),roi):{found:false};}

test('synthetic marker translation preserves known pixel displacement across frames',()=>{
  let marker={x:80,y:45};const positions=[];
  for(const y of [45,50,55,60,65]){
    const image=rectangle(frame(),77,y-3,7,7),found=locate(image,marker);
    assert.equal(found.found,true);assert.ok(Math.abs(found.y-y)<1e-9);assert.ok(Math.abs(found.x-80)<1e-9);
    positions.push(found.y);marker=found;
  }
  assert.equal(positions.at(-1)-positions[0],20);
});
test('synthetic brightness changes preserve a visible marker centroid without mixing separate background objects',()=>{
  for(const [background,markerGray]of [[255,0],[180,20],[100,50]]){
    const image=rectangle(rectangle(frame(160,120,background),77,57,7,7,markerGray),97,45,5,25,0);
    const found=locate(image,{x:80,y:60});assert.equal(found.found,true);
    assert.ok(Math.abs(found.x-80)<1e-9);assert.ok(Math.abs(found.y-60)<1e-9);
  }
});
test('lost, overlarge, transparent, fast-moving and edge-clipped markers fail explicitly',()=>{
  assert.equal(locate(frame(),{x:80,y:60}).found,false);
  assert.equal(locate(frame(160,120,0),{x:80,y:60}).found,false);
  assert.equal(locate(rectangle(frame(),77,57,7,7,0,0),{x:80,y:60}).found,false);
  assert.equal(locate(rectangle(frame(),96,57,7,7),{x:80,y:60}).found,false);
  for(const marker of [{x:2,y:60},{x:150,y:60},{x:80,y:10},{x:80,y:115}])assert.equal(acq.markerROI(160,120,marker),null);
  assert.throws(()=>acq.locateDarkMarker(new Uint8ClampedArray(4),{x:0,y:0,width:50,height:50}),/complete/);
});
test('settled capture rejects insufficient, moving and nonfinite positions',()=>{
  assert.equal(acq.settledPosition(Array(10).fill(125),.5).mean,125);
  assert.throws(()=>acq.settledPosition(Array(9).fill(125),.5),/10 valid/);
  assert.throws(()=>acq.settledPosition([0,20,0,20,0,20,0,20,0,20],.5),/not settled/);
  assert.throws(()=>acq.settledPosition([...Array(9).fill(1),NaN],.5),/valid/);
});
test('audio preparation preserves mono samples and explicit equal-weight stereo downmix',async()=>{
  const tone=Float32Array.from({length:16000},(_,i)=>.4*Math.sin(2*Math.PI*440*i/16000));
  const prepared=acq.prepareAudioInput([tone],16000);
  assert.deepEqual(prepared.samples,tone);assert.notEqual(prepared.samples,tone);
  const decoded={sampleRate:16000,numberOfChannels:1,getChannelData:()=>tone};
  const direct=await acq.prepareDecodedAudio(decoded,{},()=>{throw new Error('Same-rate data must not be resampled');});
  assert.deepEqual(direct.samples,tone);assert.equal(direct.sampleRate,16000);
  const mixed=acq.prepareAudioInput([new Float32Array([.5,-.5,.25]),new Float32Array([.25,.5,-.25])],16000);
  assert.deepEqual(Array.from(mixed.samples),[.375,0,0]);assert.equal(mixed.channelCount,2);
});
test('audio rate and duration contract is explicit, finite and never pads a recording beyond available samples',()=>{
  const long=new Float32Array(21*8000);long.fill(.125);
  const result=acq.prepareAudioInput([long],8000);
  assert.equal(result.samples.length,20*8000);assert.equal(result.outputLength,20*16000);
  assert.equal(result.duration,20);assert.equal(result.originalDuration,21);assert.equal(result.truncated,true);
  for(const rate of [0,7999,Infinity,192001])assert.throws(()=>acq.prepareAudioInput([long],rate),/rates/);
  assert.throws(()=>acq.prepareAudioInput([long],8000,{maxDuration:21}),/duration/);
  assert.throws(()=>acq.prepareAudioInput([[],[]],8000),/nonempty/);
  assert.throws(()=>acq.prepareAudioInput([[1,2],[1]],8000),/equal/);
  assert.throws(()=>acq.prepareAudioInput([[NaN]],16000),/nonfinite/);
  assert.throws(()=>acq.prepareAudioInput([[1e100]],16000),/float32/);
});
test('browser resampling adapter requests the declared mono rate/count and validates returned data',async()=>{
  const left=new Float32Array([.5,.25,-.5,-.25]),right=new Float32Array([.25,.5,-.25,-.5]);
  let received,bufferInput;
  const decoded={numberOfChannels:2,sampleRate:48000,getChannelData:i=>[left,right][i]};
  const make=(channels,length,rate)=>{
    received={channels,length,rate};
    return {destination:{},createBuffer:(c,n,r)=>{assert.deepEqual([c,n,r],[1,4,48000]);return {copyToChannel:(data,index)=>{assert.equal(index,0);bufferInput=Array.from(data);}};},
      createBufferSource:()=>({connect(){},start(){}}),startRendering:async()=>({getChannelData:()=>new Float32Array(length).fill(.125)})};
  };
  const result=await acq.prepareDecodedAudio(decoded,{},make);
  assert.deepEqual(received,{channels:1,length:1,rate:16000});assert.deepEqual(bufferInput,[.375,.375,-.375,-.375]);
  assert.equal(result.sampleRate,16000);assert.deepEqual(Array.from(result.samples),[.125]);
  // This checks the adapter contract with a fake WebAudio renderer, not the browser's DSP quality.
  const bad=(c,n,r)=>({...make(c,n,r),startRendering:async()=>({getChannelData:()=>new Float32Array(n+1)})});
  await assert.rejects(acq.prepareDecodedAudio(decoded,{},bad),/sample count/);
});

function harness({media=async()=>stream(),play=async()=>{},resume=[],close=[],decode=async()=>null,render}={}){
  const elements=new Map(),frames=[],contexts=[],mediaRequests=[],analysisCalls=[],timers=new Map();
  let nextTimer=0;
  let image=frame();
  function element(id){
    if(elements.has(id))return elements.get(id);
    const classes=new Set(),context={clearRect(){},strokeRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},
      drawImage(_video,x,y,width,height){this.roi={x,y,width,height};},getImageData(){return {data:crop(image,this.roi)};}};
    const el={id,value:'',disabled:false,hidden:false,textContent:'',innerHTML:'',width:160,height:120,videoWidth:160,videoHeight:120,readyState:3,
      style:{},parentElement:{style:{}},srcObject:null,className:'',listeners:new Map(),classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(){}},
      addEventListener(type,handler){this.listeners.set(type,handler);},setAttribute(){},removeAttribute(){},getContext:()=>context,
      getBoundingClientRect:()=>({width:160,height:120,left:0,top:0}),closest(){return this;},play};
    elements.set(id,el);return el;
  }
  class AudioContext {
    constructor(){this.index=contexts.length;this.sampleRate=48000;this.destination={};this.sources=[];this.closed=false;contexts.push(this);}
    resume(){return resume[this.index]?.promise||Promise.resolve();}
    close(){this.closed=true;return close[this.index]?.promise||Promise.resolve();}
    decodeAudioData(data){return decode(data);}
    createMediaStreamSource(value){this.sources.push(value);return {connect(){},disconnect(){}};}
    createScriptProcessor(){return {connect(){},disconnect(){},onaudioprocess:null};}
  }
  class OfflineAudioContext {
    constructor(_channels,length,rate){this.length=length;this.sampleRate=rate;this.destination={};}
    createBuffer(){return {copyToChannel(){}};}
    createBufferSource(){return {connect(){},start(){}};}
    async startRendering(){return render?render(this):{getChannelData:()=>new Float32Array(this.length)};}
  }
  class AudioBuffer {
    constructor({length,sampleRate}){this.sampleRate=sampleRate;this.length=length;this.numberOfChannels=1;this.data=new Float32Array(length);}
    copyToChannel(values){this.data.set(values);}
    getChannelData(){return this.data;}
  }
  const sandbox={console,Float32Array,Uint8ClampedArray,InstrumentZeroAcquisition:acq,
    document:{getElementById:element,querySelectorAll:()=>[]},window:{AudioContext,addEventListener(){}},OfflineAudioContext,AudioBuffer,
    navigator:{mediaDevices:{getUserMedia:options=>{mediaRequests.push(options);return media(options);}}},
    requestAnimationFrame:callback=>{frames.push(callback);return frames.length;},cancelAnimationFrame(){},
    setTimeout(callback,delay){const id=++nextTimer;timers.set(id,{callback,delay});return id;},clearTimeout(id){timers.delete(id);},analysisCalls};
  vm.createContext(sandbox);
  // Suppress only the unrelated automatic example fetch; every tested acquisition entrypoint is unchanged.
  vm.runInContext(appSource.replace(/^demo\(true\);$/m,''),sandbox,{filename:'Lab app.js'});
  const run=code=>vm.runInContext(code,sandbox);
  run('analyzeAudio = async (...args) => analysisCalls.push(args)');
  return {run,elements,element,contexts,frames,mediaRequests,analysisCalls,timers,
    inject(name,value){sandbox[name]=value;},setImage(value){image=value;}};
}

test('actual Lab camera entrypoint disposes a permission response received after Stop',async()=>{
  const permission=deferred(),device=stream(),h=harness({media:()=>permission.promise});
  const starting=h.run('startCamera()');h.run('stopCamera()');permission.resolve(device);await starting;
  assert.ok(device.track.stops>0);assert.equal(h.run('state.cameraStream'),null);assert.equal(h.frames.length,0);
  assert.equal(h.element('camera-stop').disabled,true);
});
test('actual Lab camera cannot restart tracking when a canceled video.play promise resolves',async()=>{
  const playing=deferred(),device=stream(),h=harness({media:async()=>device,play:()=>playing.promise});
  const starting=h.run('startCamera()');await flush();h.run('stopCamera()');playing.resolve();await starting;
  assert.equal(h.frames.length,0);assert.equal(h.element('camera-stop').disabled,true);
  assert.equal(h.element('camera-video').srcObject,null);assert.ok(device.track.stops>0);
});
test('actual Lab camera ignores an older denied request after a newer start succeeds',async()=>{
  const permission=deferred(),device=stream();let requests=0;
  const h=harness({media:()=>++requests===1?permission.promise:Promise.resolve(device)});
  const old=h.run('startCamera()');await h.run('startCamera()');permission.reject(new Error('Synthetic stale denial'));await old;
  assert.equal(h.run('state.cameraStream'),device);assert.equal(device.track.stops,0);
  assert.equal(h.element('camera-stop').disabled,false);
});
test('actual Lab tracker rejects out-of-frame crops and requires reselection after marker loss',()=>{
  const h=harness();h.run('state.cameraStream = {getTracks:()=>[]}');h.run('state.marker={x:2,y:60};trackCamera(100)');
  assert.equal(h.run('state.marker'),null);assert.equal(h.run('state.markerSamples.length'),0);
  h.run('state.marker={x:80,y:60};trackCamera(200)');assert.equal(h.run('state.marker'),null);
  h.setImage(rectangle(frame(),77,57,7,7));h.run('trackCamera(300)');
  assert.equal(h.run('state.marker'),null);assert.equal(h.run('state.markerSamples.length'),0);
});
test('actual Lab tracker and settled capture retain known synthetic positions in exported-row coordinates',()=>{
  const h=harness();h.run('state.cameraStream={getTracks:()=>[]};state.marker={x:80,y:60}');
  h.element('max-force').value='2';h.element('pixel-noise').value='.5';h.element('capture-force').value='0';
  h.setImage(rectangle(frame(),77,57,7,7));
  let time=100;for(let i=0;i<30;i++){h.run(`trackCamera(${time})`);time+=100;}
  h.run('capturePosition()');
  for(const y of [65,70,75,80]){h.setImage(rectangle(frame(),77,y-3,7,7));h.run(`trackCamera(${time})`);time+=100;}
  for(let i=0;i<30;i++){h.run(`trackCamera(${time})`);time+=100;}
  h.element('capture-force').value='.5';h.run('capturePosition()');
  assert.equal(h.run('state.capturedRows.length'),2);
  assert.equal(h.run('state.capturedRows[0].position_px'),60);assert.equal(h.run('state.capturedRows[1].position_px'),80);
  assert.equal(h.run('state.capturedRows[1].force_n'),.5);
  assert.match(h.element('csv-text').value,/force_n,position_px\n0,60\n0.5,80/);
});
test('actual Lab microphone cannot attach an old stream to a newer resumed audio context',async()=>{
  const firstResume=deferred(),first=stream(),second=stream();let requests=0;
  const h=harness({media:async()=>++requests===1?first:second,resume:[firstResume]});h.run("state.domain='acoustic'");
  const old=h.run('startMic()');await flush();assert.equal(h.contexts.length,1);
  await h.run('stopMic()');await h.run('startMic()');assert.equal(h.contexts.length,2);
  firstResume.resolve();await old;
  assert.equal(h.run('state.micStream'),second);assert.equal(second.track.stops,0);
  assert.equal(h.contexts[1].sources.length,1);assert.ok(first.track.stops>0);
});
test('actual Lab microphone honors Stop while an earlier AudioContext close is pending',async()=>{
  const closing=deferred(),h=harness({close:[closing]});h.run("state.domain='acoustic';state.audioContext=new window.AudioContext()");
  const starting=h.run('startMic()');await flush();await h.run('stopMic()');closing.resolve();await starting;
  assert.equal(h.mediaRequests.length,0);assert.equal(h.element('mic-record').disabled,true);
});
test('actual Lab audio import is canceled by a domain round trip while decoding',async()=>{
  const decoding=deferred(),h=harness({decode:()=>decoding.promise});h.run("state.domain='acoustic'");
  const importing=h.run("importAudio({size:100,name:'synthetic-fixture.wav',arrayBuffer:async()=>new ArrayBuffer(4)})");await flush();
  h.run("changeDomain('stiffness');changeDomain('acoustic')");
  decoding.resolve({numberOfChannels:1,sampleRate:16000,duration:1,getChannelData:()=>new Float32Array(16000)});await importing;
  assert.equal(h.analysisCalls.length,0);assert.equal(h.run('state.samples'),null);
});
test('actual Lab file import hands the shared mono preparation to analysis without changing same-rate samples',async()=>{
  const left=Float32Array.from({length:16000},(_,i)=>.4*Math.sin(2*Math.PI*440*i/16000));
  const right=Float32Array.from(left,value=>value*.5);
  const h=harness({decode:async()=>({numberOfChannels:2,sampleRate:16000,getChannelData:i=>[left,right][i]})});
  h.run("state.domain='acoustic'");
  await h.run("importAudio({size:100,name:'explicitly-synthetic-stereo.wav',arrayBuffer:async()=>new ArrayBuffer(4)})");
  assert.equal(h.analysisCalls.length,1);
  const [samples,rate]=h.analysisCalls[0];assert.equal(rate,16000);assert.equal(samples.length,16000);
  assert.deepEqual(samples,Float32Array.from(left,(value,i)=>(value+right[i])/2));
});
test('actual Lab capture preparation trims delayed audio callbacks to the selected capture duration',async()=>{
  const h=harness();h.run("state.domain='acoustic'");await h.run('startMic()');h.run('state.audioContext.sampleRate=16000');
  h.element('capture-duration').value='1';h.run('recordMic()');
  const tone=Float32Array.from({length:32000},(_,i)=>.3*Math.sin(2*Math.PI*440*i/16000));
  h.inject('syntheticTone',tone);h.inject('syntheticOutput',new Float32Array(32000));
  h.run('state.processor.onaudioprocess({inputBuffer:{getChannelData:()=>syntheticTone},outputBuffer:{getChannelData:()=>syntheticOutput}})');
  const timer=[...h.timers.values()][0];assert.equal(timer.delay,1000);await timer.callback();
  assert.equal(h.analysisCalls.length,1);assert.equal(h.analysisCalls[0][0].length,16000);
  assert.deepEqual(h.analysisCalls[0][0],tone.subarray(0,16000));
});
test('actual Lab Stop cancels a captured signal still waiting for browser resampling',async()=>{
  const rendering=deferred(),h=harness({render:()=>rendering.promise});h.run("state.domain='acoustic'");await h.run('startMic()');
  h.element('capture-duration').value='1';h.run('recordMic()');
  h.inject('syntheticTone',new Float32Array(48000).fill(.125));
  h.run('state.recordChunks=[syntheticTone]');const processing=[...h.timers.values()][0].callback();await flush();
  await h.run('stopMic()');rendering.resolve({getChannelData:()=>new Float32Array(16000)});await processing;
  assert.equal(h.analysisCalls.length,0);assert.equal(h.element('mic-record').disabled,true);
  assert.equal(h.element('mic-status').textContent,'Microphone is off.');
});
