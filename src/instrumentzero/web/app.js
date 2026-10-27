'use strict';

const acquisition = globalThis.InstrumentZeroAcquisition;
const $ = (id) => document.getElementById(id);
const state = {domain:'stiffness',demoAudio:false,spec:null,plan:null,result:null,rows:[],samples:null,sampleRate:null,busy:false,cameraGate:acquisition.createCaptureGate(),micGate:acquisition.createCaptureGate(),importGate:acquisition.createCaptureGate(),cameraStream:null,cameraFrame:null,marker:null,markerSamples:[],capturedRows:[],micStream:null,audioContext:null,processor:null,audioSource:null,recording:false,recordChunks:[],recordTimer:null};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const finite = (n) => typeof n === 'number' && Number.isFinite(n);
const fmt = (n,d=4) => finite(n) ? (Math.abs(n)>0 && (Math.abs(n)<0.001 || Math.abs(n)>=1e6) ? n.toExponential(2) : Number(n.toPrecision(d)).toLocaleString('en-US',{maximumFractionDigits:8})) : '—';
const number = (id) => {const n=Number($(id).value);if(!Number.isFinite(n))throw new Error(`Enter a valid value for ${$(id).closest('label')?.textContent.trim() || id}.`);return n;};
function notify(message,type='info'){const el=$('message');el.textContent=message;el.className=`message ${type}`;el.hidden=false;}
function clearMessage(){$('message').hidden=true;}
function setBusy(busy,label){state.busy=busy;for(const id of ['compile-button','demo-button','example-choice','analyze-csv','apply-calibration'])$(id).disabled=busy;$('export-button').disabled=busy||!state.result;if(busy)notify(label||'Computing locally…','busy');}
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok){let error;try{error=await response.json();}catch{error={error:`The local engine returned HTTP ${response.status}.`};}throw new Error(typeof error.error==='string'?error.error:JSON.stringify(error.error||error));}return response;}
async function apiJSON(path,body){return (await api(path,body)).json();}
function currentSpec(kind,name,preserveSource=false){const sourceMetadata=preserveSource&&state.spec?{source_limitations:[...(state.spec.source_limitations||[])],source_attribution:(state.spec.source_attribution||[]).map(item=>({...item})),reference:state.spec.reference?{...state.spec.reference}:null,calibration_basis:state.spec.calibration_basis||'User-declared values; independent certificates not verified by this engine'}:{};return {...sourceMetadata,domain:state.domain,question:$('question').value.trim(),equipment:$('equipment').value.split(',').map(s=>s.trim()).filter(Boolean),target_relative_uncertainty:number('accuracy')/100,budget_seconds:number('budget'),max_force_n:number('max-force'),min_frequency_hz:number('min-frequency'),max_frequency_hz:number('max-frequency'),source_kind:preserveSource&&state.spec?state.spec.source_kind:kind||state.spec?.source_kind||'imported',source_name:preserveSource&&state.spec?state.spec.source_name:name||$('source-name').value.trim()||'User measurement',calibration:{meters_per_pixel:number('meters-per-pixel'),scale_relative_sd:number('scale-uncertainty')/100,force_relative_sd:number('force-uncertainty')/100,pixel_noise_sd:number('pixel-noise'),sample_clock_relative_sd:number('clock-uncertainty')/100}};}
function populateSpec(spec){if(!spec)return;$('question').value=spec.question||$('question').value;$('equipment').value=(spec.equipment||[]).join(', ');if(finite(spec.target_relative_uncertainty))$('accuracy').value=spec.target_relative_uncertainty*100;if(finite(spec.budget_seconds))$('budget').value=spec.budget_seconds;if(finite(spec.max_force_n))$('max-force').value=spec.max_force_n;if(finite(spec.min_frequency_hz))$('min-frequency').value=spec.min_frequency_hz;if(finite(spec.max_frequency_hz))$('max-frequency').value=spec.max_frequency_hz;$('source-name').value=spec.source_name||'User measurement';const c=spec.calibration||{};for(const [key,id,multiplier]of [['meters_per_pixel','meters-per-pixel',1],['scale_relative_sd','scale-uncertainty',100],['force_relative_sd','force-uncertainty',100],['pixel_noise_sd','pixel-noise',1],['sample_clock_relative_sd','clock-uncertainty',100]])if(finite(c[key]))$(id).value=c[key]*multiplier;}
function showView(view){document.querySelectorAll('.view-panel').forEach(el=>el.hidden=el.id!==`${view}-view`);document.querySelectorAll('[data-view]').forEach(el=>{el.classList.toggle('active',el.dataset.view===view);if(el.dataset.view===view)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});}
function showCapture(capture){document.querySelectorAll('.capture-panel').forEach(el=>el.hidden=el.id!==`${capture}-capture`);document.querySelectorAll('[data-capture]').forEach(el=>el.classList.toggle('active',el.dataset.capture===capture));}
function sourceLabel(kind){return ({synthetic:'SYNTHETIC / CONTROLLED',recorded:'RECORDED / REAL SIGNAL',imported:'IMPORTED / USER DATA',live:'LIVE / LOCAL CAPTURE'}[kind]||'SOURCE UNSPECIFIED');}
function originDescription(result){const kind=result.source_kind;return kind==='synthetic'?'Controlled example data. These are simulated observations, not a physical experiment.':kind==='recorded'?'An authentic recorded signal, replayed for analysis. This is not live acquisition.':kind==='live'?'Captured locally after deliberate sensor activation. Physical calibration still requires inspection.':'User-supplied measurements. Inspect calibration and provenance before using the estimate.';}

function setupDiagram(){const mechanical=state.domain==='stiffness';$('setup-diagram').innerHTML=mechanical?`<svg viewBox="0 0 300 145" role="img" aria-label="Fixed camera observes a fiducial on a spring under a known downward load"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse"><path d="M0 6L6 0" stroke="#bac2af" stroke-width=".7"/></pattern></defs><rect x="36" y="18" width="130" height="12" fill="url(#hatch)"/><path d="M36 30H166M99 30v8l-9 6 18 8-18 8 18 8-18 8 18 8-9 6v12" stroke="#404d3c" fill="none" stroke-width="1.5"/><path d="M73 103h52v19H73z" fill="#e9eddf" stroke="#7c8972"/><circle cx="99" cy="112" r="3" fill="#375cbd"/><path d="M99 125v13m-4-5 4 5 4-5" stroke="#e75630" fill="none" stroke-width="1.8"/><text x="111" y="139" fill="#a75a38" font-family="monospace" font-size="8">F (known)</text><path d="M60 45v70M56 45h8M56 115h8M60 60h5M60 75h5M60 90h5" stroke="#839177" fill="none"/><text x="29" y="129" fill="#75826c" font-family="monospace" font-size="6">SCALE</text><path d="M216 91h26v27h-26l-8-6v-15z" fill="#f0f1e9" stroke="#7d8975"/><circle cx="230" cy="104" r="7" fill="none" stroke="#7d8975"/><path d="M208 99 104 109M208 112 104 115" stroke="#c2cbb8" stroke-dasharray="3 3"/><text x="207" y="132" fill="#75826c" font-family="monospace" font-size="6">FIXED CAMERA</text><text x="115" y="93" fill="#375cbd" font-family="monospace" font-size="7">y (observed)</text></svg>`:`<svg viewBox="0 0 300 145" role="img" aria-label="A vibrating tuning fork is recorded by a microphone with a calibrated sample clock"><path d="M72 32v39c0 28 38 28 38 0V32M91 93v33" fill="none" stroke="#58664f" stroke-width="5" stroke-linecap="round"/><path d="M130 50q12 20 0 40M144 41q20 30 0 59M157 31q30 40 0 79" fill="none" stroke="#c0cbb4" stroke-width="1.1"/><rect x="194" y="44" width="19" height="42" rx="10" fill="#e9eddf" stroke="#68795e"/><path d="M187 71v5c0 23 34 23 34 0v-5M204 96v15m-13 0h26" fill="none" stroke="#68795e"/><circle cx="204" cy="58" r="2" fill="#375cbd"/><path d="M196 67h15M196 72h15" stroke="#a8b59a"/><text x="49" y="140" fill="#75826c" font-family="monospace" font-size="7">RESONATOR</text><text x="183" y="130" fill="#375cbd" font-family="monospace" font-size="7">MICROPHONE</text><path d="M35 48q-8 16 0 31M123 48q8 16 0 31" stroke="#e75630" fill="none" stroke-width="1.5"/></svg>`;$('setup-description').textContent=mechanical?'Apply known low-risk loads. Track a dark fiducial from a fixed camera. Calibrate pixels against a known length in the same plane.':'Record a ringing resonator or steady tone. Confirm the peak is the intended mode. Sample-clock uncertainty sets a shared precision floor.';}
function resetResult(){state.demoAudio=false;state.result=null;state.plan=null;state.rows=[];state.samples=null;state.sampleRate=null;state.spec=null;$('quantity-value').textContent='—';$('quantity-unit').textContent=state.domain==='stiffness'?'N/m':'Hz';$('quantity-label').textContent=state.domain==='stiffness'?'ESTIMATED STIFFNESS':'ESTIMATED RESONANCE';$('quantity-label').closest('.metric-card').classList.remove('result-unreliable');$('quantity-interval').textContent='Calibrate and analyze to begin';$('uncertainty-detail').textContent='Model-conditional interval';$('uncertainty-value').textContent='—';$('source-badge').textContent='NO DATA YET';$('source-badge').className='source-badge empty';$('source-description').textContent='Import recorded data or deliberately enable a local sensor.';$('sample-count').textContent='0 observations';$('main-chart').innerHTML='<div class="chart-empty"><span>＋</span><p>The signal belongs here.</p><small>Load an example or import your measurements.</small></div>';$('residual-chart').innerHTML='';$('main-chart').setAttribute('aria-label','No measurement plot yet');$('residual-chart').setAttribute('aria-label','No residuals yet');$('model-status').textContent='MODEL NOT YET FITTED';$('model-status').className='';$('fit-detail').textContent='Calibration precedes conclusion.';$('next-title').textContent='Let the evidence choose what comes next.';$('next-reason').textContent='After inference, compare feasible actions by expected uncertainty reduction and acquisition cost.';$('next-settings').innerHTML='';$('run-label').textContent='Ready for a measurement';$('export-button').disabled=true;$('warnings-panel').hidden=true;$('convergence-panel').hidden=true;$('protocol-content').innerHTML='<p class="empty-copy">No protocol compiled yet.</p>';$('evidence-content').innerHTML='<p class="empty-copy">Analyze data to inspect provenance and model checks.</p>';}
function changeDomain(domain){if(domain===state.domain)return;if(state.busy){notify('Wait for the current analysis to finish before changing the measurement family.');$('family-select').value=state.domain;return;}stopCamera();stopMic();state.importGate.cancel();state.domain=domain;state.capturedRows=[];state.marker=null;$('camera-count').textContent='0 captured loads · at least 4 required';$('camera-analyze').disabled=true;resetResult();clearMessage();document.querySelectorAll('[data-domain]').forEach(el=>el.classList.toggle('active',el.dataset.domain===domain));$('family-select').value=domain;const acoustic=domain==='acoustic';$('question').value=acoustic?'What is the resonance frequency of this sound?':'How stiff is this spring?';$('equipment').value=acoustic?'Microphone, sample clock':'Camera, known loads, ruler';$('family-number').textContent=acoustic?'02':'01';$('family-label').textContent=acoustic?'ACOUSTICS / RESONANCE':'MECHANICS / STIFFNESS';$('plot-title').textContent=acoustic?'Frequency & power':'Force & deflection';$('observation-legend').hidden=acoustic;$('line-legend-label').textContent=acoustic?'Measured spectrum':'Fitted model';$('setup-input-label').textContent=acoustic?'Resonator':'Known input';$('setup-output-label').textContent=acoustic?'Recorded signal':'Observed output';$('model-equation').textContent=acoustic?'y(t) = A sin(2πft + φ)':'x = b + F/k';$('sensor-tab').textContent=acoustic?'Microphone':'Camera';$('example-choice-label').hidden=acoustic;$('import-title').textContent=acoustic?'Recorded acoustic signal':'Calibrated force–deflection data';$('import-description').textContent=acoustic?'Choose a WAV or browser-supported audio file. The first 20 seconds are analyzed locally at 16 kHz. Retain your original recording for provenance.':'CSV with force_n and position_px, or force_n, displacement_m and sigma_m. Every row is preserved in the export.';$('data-file').accept=acoustic?'audio/*,.wav,.ogg,.mp3':'.csv,text/csv';$('csv-editor').hidden=acoustic;$('camera-tools').hidden=acoustic;$('microphone-tools').hidden=!acoustic;document.querySelectorAll('.mechanical-setting').forEach(el=>el.hidden=acoustic);document.querySelectorAll('.acoustic-setting').forEach(el=>el.hidden=!acoustic);$('residual-label').textContent=acoustic?'SIGNAL / THINNED TIME-DOMAIN PREVIEW':'RESIDUALS / OBSERVED − FITTED';$('residual-unit').textContent=acoustic?'relative amplitude':'m';$('csv-text').value='';showView('workspace');showCapture('import');setupDiagram();}

function lineChart(container,xs,ys,{predicted=null,xLabel='',yLabel='',log=false,small=false,points=true}={}){const valid=xs.map((x,i)=>[Number(x),Number(ys[i]),predicted?Number(predicted[i]):null]).filter(p=>finite(p[0])&&finite(p[1]));if(!valid.length){$(container).innerHTML='<div class="chart-empty"><small>No plottable values returned.</small></div>';return;}const transform=y=>log?10*Math.log10(Math.max(y,1e-24)):y;let xMin=Math.min(...valid.map(p=>p[0])),xMax=Math.max(...valid.map(p=>p[0]));let allY=valid.map(p=>transform(p[1]));if(predicted)allY.push(...valid.filter(p=>finite(p[2])).map(p=>transform(p[2])));let yMin=Math.min(...allY),yMax=Math.max(...allY);if(xMin===xMax){xMin-=.5;xMax+=.5;}if(yMin===yMax){yMin-=Math.max(.001,Math.abs(yMin)*.1);yMax+=Math.max(.001,Math.abs(yMax)*.1);}const yPad=(yMax-yMin)*.1;yMin-=yPad;yMax+=yPad;const W=700,H=small?90:300,L=small?57:64,R=20,T=small?10:20,B=small?18:44;const px=x=>L+(x-xMin)/(xMax-xMin)*(W-L-R),py=y=>T+(yMax-transform(y))/(yMax-yMin)*(H-T-B);let svg=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">`;const ticks=small?2:4;for(let i=0;i<=ticks;i++){const yy=T+i*(H-T-B)/ticks,val=yMax-i*(yMax-yMin)/ticks;svg+=`<path class="chart-grid" d="M${L} ${yy}H${W-R}"/><text class="chart-axis" x="${L-9}" y="${yy+3}" text-anchor="end">${esc(fmt(val,3))}</text>`;}if(!small){for(let i=0;i<=4;i++){const xx=L+i*(W-L-R)/4;svg+=`<path class="chart-grid" d="M${xx} ${T}V${H-B}"/><text class="chart-axis" x="${xx}" y="${H-B+19}" text-anchor="middle">${esc(fmt(xMin+i*(xMax-xMin)/4,3))}</text>`;}svg+=`<text class="chart-axis-label" x="${(L+W-R)/2}" y="${H-5}" text-anchor="middle">${esc(xLabel)}</text><text class="chart-axis-label" transform="translate(13 ${(T+H-B)/2}) rotate(-90)" text-anchor="middle">${esc(yLabel)}${log?' (dB)':''}</text>`;}if(yMin<=0&&yMax>=0&&!log)svg+=`<path class="zero-line" d="M${L} ${py(0)}H${W-R}"/>`;const sorted=[...valid].sort((a,b)=>a[0]-b[0]);if(predicted){svg+=`<path class="fit-path" d="${sorted.filter(p=>finite(p[2])).map((p,i)=>`${i?'L':'M'}${px(p[0]).toFixed(2)} ${py(p[2]).toFixed(2)}`).join(' ')}"/>`;}if(points){svg+=valid.map(p=>`<circle class="${small?'residual-point':'data-point'}" cx="${px(p[0]).toFixed(2)}" cy="${py(p[1]).toFixed(2)}" r="${small?3:4.3}"><title>${esc(`${xLabel}: ${fmt(p[0])}; ${yLabel}: ${fmt(p[1])}`)}</title></circle>`).join('');}else{svg+=`<path class="${small?'wave-path':'spectrum-path'}" d="${sorted.map((p,i)=>`${i?'L':'M'}${px(p[0]).toFixed(2)} ${py(p[1]).toFixed(2)}`).join(' ')}"/>`;}svg+='</svg>';$(container).innerHTML=svg;$(container).setAttribute('aria-label',`${yLabel} versus ${xLabel}, ${valid.length} plotted values`);}

function resultWarnings(result){return [...new Set([...(result.warnings||[]),...(state.spec?.source_kind==='synthetic'?['Synthetic observations demonstrate the workflow; they do not validate performance on physical equipment.']:[])])];}
function renderConvergence(history){const rows=(history||[]).filter(p=>finite(p.samples)&&finite(p.relative_uncertainty));$('convergence-panel').hidden=rows.length<2;if(rows.length<2)return;const W=640,H=130,L=48,R=18,T=18,B=33,xMin=Math.min(...rows.map(p=>p.samples)),xMax=Math.max(...rows.map(p=>p.samples)),values=rows.map(p=>p.relative_uncertainty*100),yMax=Math.max(...values)*1.15||1,px=x=>L+(x-xMin)/(xMax-xMin||1)*(W-L-R),py=y=>T+(1-y/yMax)*(H-T-B);let svg=`<svg viewBox="0 0 ${W} ${H}" role="presentation">`;for(let i=0;i<=2;i++){const y=yMax*i/2;svg+=`<path class="chart-grid" d="M${L} ${py(y)}H${W-R}"/><text class="convergence-label" x="${L-9}" y="${py(y)+3}" text-anchor="end">${esc(fmt(y,2))}%</text>`;}svg+=`<path class="fit-path" d="${rows.map((p,i)=>`${i?'L':'M'}${px(p.samples)} ${py(p.relative_uncertainty*100)}`).join(' ')}"/>`;for(const p of rows)svg+=`<circle class="data-point" cx="${px(p.samples)}" cy="${py(p.relative_uncertainty*100)}" r="4"><title>${p.samples} observations: ${esc(fmt(p.relative_uncertainty*100))}% relative uncertainty</title></circle><text class="convergence-label" x="${px(p.samples)}" y="${H-B+17}" text-anchor="middle">${p.samples}</text>`;svg+=`<text class="convergence-label" x="${W-R}" y="${H-2}" text-anchor="end">Accumulated observations →</text></svg>`;$('convergence-chart').innerHTML=svg;}
function renderResult(result){state.result=result;const q=result.quantity||{};$('quantity-label').textContent=(q.name|| (state.domain==='stiffness'?'Estimated stiffness':'Estimated resonance')).toUpperCase()+(result.status==='unreliable'?' / UNRELIABLE':'');$('quantity-label').closest('.metric-card').classList.toggle('result-unreliable',result.status==='unreliable');$('quantity-value').textContent=fmt(q.value,5);$('quantity-unit').textContent=q.unit||'';const interval=q.interval_95||[];$('quantity-interval').textContent=interval.length===2?`${q.interval_label?'Envelope':'95% interval'}: ${fmt(interval[0])} – ${fmt(interval[1])} ${q.unit||''}`:'Uncertainty interval unavailable';$('uncertainty-value').textContent=finite(q.relative_uncertainty)?fmt(q.relative_uncertainty*100,3):'—';const target=state.spec?.target_relative_uncertainty;$('uncertainty-detail').textContent=q.interval_label|| (finite(target)?`Target: ${fmt(target*100,3)}% · 95% interval`:'95% interval · model conditional');$('source-badge').textContent=sourceLabel(result.source_kind||state.spec?.source_kind);$('source-badge').className=`source-badge ${(result.source_kind||state.spec?.source_kind)==='synthetic'?'synthetic':''}`;$('source-description').textContent=originDescription({...result,source_kind:result.source_kind||state.spec?.source_kind});$('run-label').textContent=result.source_name||state.spec?.source_name||'Measurement analyzed';$('export-button').disabled=false;const fit=result.fit||{};if(state.domain==='acoustic'&&result.spectrum){lineChart('main-chart',result.spectrum.frequency_hz||[],result.spectrum.power||[],{xLabel:'Frequency (Hz)',yLabel:'Spectral power',log:true,points:false});const wave=result.waveform||{};lineChart('residual-chart',wave.time_s||fit.x||[],wave.amplitude||fit.observed||[],{xLabel:'Time (s)',yLabel:'Amplitude',small:true,points:false});$('sample-count').textContent=`${fmt(result.provenance?.samples||result.provenance?.sample_count||result.sample_count||fit.x?.length||0,5)} samples`;}else{lineChart('main-chart',fit.x||[],fit.observed||[],{predicted:fit.predicted||null,xLabel:fit.x_label||'Force (N)',yLabel:fit.y_label||'Deflection (m)'});lineChart('residual-chart',fit.x||[],fit.residuals||[],{xLabel:fit.x_label||'Force (N)',yLabel:'Residual (m)',small:true});$('sample-count').textContent=`${(fit.x||[]).length} observations`;}$('model-status').textContent=result.status==='reliable'?'MODEL CHECKS PASSED':'INSPECT MODEL LIMITATIONS';$('model-status').className=result.status==='reliable'?'':'unreliable';$('fit-detail').textContent=result.status==='reliable'?'Conditional on the stated assumptions.':'A fitted number is not a verified conclusion.';const next=result.next_experiment||{};$('next-title').textContent=next.title||'Inspect the experimental model.';$('next-reason').textContent=next.reason||'Additional measurement design was not returned.';const settings=next.settings||{};$('next-settings').innerHTML=Object.entries(settings).slice(0,4).map(([key,value])=>`<div class="next-setting"><small>${esc(key.replaceAll('_',' '))}</small>${esc(typeof value==='number'?fmt(value):typeof value==='object'?JSON.stringify(value):value)}</div>`).join('');const warnings=resultWarnings(result);$('warnings-panel').hidden=!warnings.length;$('warnings-list').innerHTML=warnings.map(w=>`<li>${esc(w)}</li>`).join('');renderEvidence(result);renderConvergence(result.uncertainty_history);}
function renderPlan(plan){state.plan=plan;const steps=plan.steps||[];let html=`<div class="evidence-section"><h3>${esc(plan.title||'Measurement protocol')}</h3><p>${plan.identifiable?'The supported model is structurally identifiable when the required measurements and calibration are available.':'Identifiability requires additional information. Inspect the requirements before acquisition.'}</p></div>`;html+=steps.map((s,i)=>`<article class="protocol-step"><span class="step-number">${String(i+1).padStart(2,'0')}</span><div><h3>${esc(typeof s==='string'?s:s.title)}</h3><p>${esc(typeof s==='string'?'':s.detail||s.description||'')}</p></div></article>`).join('');for(const [label,items]of [['Required calibration',plan.required_calibration],['Explicit assumptions',plan.assumptions],['Limitations',plan.warnings]])if(items&&Object.keys(items).length){html+=`<section class="evidence-section"><h3>${label}</h3><ul>${(Array.isArray(items)?items:Object.entries(items).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`)).map(s=>`<li>${esc(typeof s==='object'?JSON.stringify(s):s)}</li>`).join('')}</ul></section>`;}$('protocol-content').innerHTML=html;}
function tableRows(object){return Object.entries(object||{}).map(([k,v])=>`<tr><th>${esc(k.replaceAll('_',' '))}</th><td>${esc(typeof v==='number'?fmt(v,7):typeof v==='object'?JSON.stringify(v):v)}</td></tr>`).join('');}
function renderEvidence(result){let html=`<section class="evidence-section"><h3>Evidence origin</h3><p>${esc(originDescription(result))}</p><table class="evidence-table">${tableRows({source_kind:result.source_kind,source_name:result.source_name,status:result.status,calibration_basis:state.spec?.calibration_basis,...result.provenance})}</table></section><section class="evidence-section"><h3>Calibration & uncertainty</h3><table class="evidence-table">${tableRows(result.calibration||state.spec?.calibration)}</table><p>The reported interval is conditional on the specified forward model, noise assumptions and calibration. A nominal reference is not a calibration certificate.</p></section>`;if(result.reference)html+=`<section class="evidence-section"><h3>External reference comparison</h3><table class="evidence-table">${tableRows(result.reference)}</table><p>Inspect the reference kind and source. Agreement alone does not establish traceability or validate an unrecorded follow-up action.</p></section>`;if(result.model_comparison?.length)html+=`<section class="evidence-section"><h3>Competing models</h3>${result.model_comparison.map(model=>`<table class="evidence-table">${tableRows(typeof model==='object'?model:{model})}</table>`).join('')}</section>`;html+=`<section class="evidence-section"><h3>Assumptions & limits</h3><ul>${[...(result.assumptions||[]),...resultWarnings(result)].map(s=>`<li>${esc(s)}</li>`).join('')}</ul></section><section class="evidence-section"><h3>Machine-readable result</h3><pre class="evidence-json">${esc(JSON.stringify(result,null,2))}</pre></section>`;$('evidence-content').innerHTML=html;}

async function compile(){if(state.busy)return;setBusy(true,'Compiling the measurement specification…');try{const spec=currentSpec(undefined,undefined,Boolean(state.result));const plan=await apiJSON('/api/compile',spec);if(!state.result)state.spec=spec;renderPlan(plan);clearMessage();notify('Protocol compiled. Inspect calibration before acquisition. Existing results retain their original specification until you reanalyze.');showView('protocol');}catch(error){notify(error.message,'error');}finally{setBusy(false);}}
async function demo(initial=false){if(state.busy)return;state.importGate.cancel();stopCamera();stopMic();setBusy(true,'Loading the example and running the scientific engine…');try{const recordedStiffness=state.domain==='stiffness'&&$('example-choice').value==='recorded';const bundle=await apiJSON(`/api/demo/${state.domain}${recordedStiffness?'/recorded':''}`);state.spec=bundle.spec;state.demoAudio=state.domain==='acoustic';state.rows=bundle.rows||[];state.samples=bundle.samples?new Float32Array(bundle.samples):null;state.sampleRate=bundle.sample_rate_hz||null;populateSpec(bundle.spec);if(bundle.plan)renderPlan(bundle.plan);if(!bundle.result)throw new Error('The engine returned no result for this example.');renderResult(bundle.result);if(state.rows.length)$('csv-text').value=rowsToCSV(state.rows);showView('workspace');clearMessage();if(!initial)notify(state.domain==='stiffness'?(recordedStiffness?'Recorded nickel force-sensor example loaded. The linear stiffness estimate is unreliable; inspect the residuals, source limitations and model warnings.':'Synthetic force–deflection example loaded. The observations are simulated.'):'Authentic recorded-audio example loaded. The reference frequency is nominal, not a traceable calibration.');}catch(error){notify(error.message,'error');}finally{setBusy(false);}}
function parseCSV(text){const records=[];let row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(c===','||c==='\n'||c==='\r')){row.push(cell.trim());cell='';if(c!==','){if(c==='\r'&&text[i+1]==='\n')i++;if(row.some(s=>s!==''))records.push(row);row=[];}}else cell+=c;}if(quoted)throw new Error('The CSV contains an unclosed quote.');row.push(cell.trim());if(row.some(s=>s!==''))records.push(row);if(records.length<2)throw new Error('Add a CSV header and measurement rows.');if(records.length>10001)throw new Error('Use at most 10,000 measurement rows per import.');const headers=records.shift().map(s=>s.replace(/^\uFEFF/,'').trim());if(new Set(headers).size!==headers.length)throw new Error('CSV column names must be unique.');if(!headers.includes('force_n'))throw new Error('CSV requires a force_n column.');if(!headers.includes('position_px')&&!headers.includes('displacement_m'))throw new Error('CSV requires position_px or displacement_m.');const fields=headers.filter(s=>['force_n','position_px','displacement_m','sigma_m','sigma_px'].includes(s));return records.map((values,i)=>{if(values.length!==headers.length)throw new Error(`CSV row ${i+2} has ${values.length} fields; expected ${headers.length}.`);const item={};for(const key of fields){const raw=values[headers.indexOf(key)],value=Number(raw);if(raw===''||!Number.isFinite(value))throw new Error(`CSV row ${i+2}, ${key}: enter a finite number.`);item[key]=value;}return item;});}
function rowsToCSV(rows){if(!rows.length)return '';const keys=Object.keys(rows[0]).filter(k=>['force_n','position_px','displacement_m','sigma_m','sigma_px'].includes(k));return [keys.join(','),...rows.map(r=>keys.map(k=>r[k]).join(','))].join('\n');}
function sameObservations(rows){return rows.length===state.rows.length&&rows.every((row,i)=>{const a=Object.keys(row).sort(),b=Object.keys(state.rows[i]).sort();return a.length===b.length&&a.every((key,j)=>key===b[j]&&row[key]===state.rows[i][key]);});}
async function analyzeRows(rows,kind='imported',name,preserveSource){if(state.busy)return;setBusy(true,'Fitting the physical model and propagating calibration uncertainty…');try{const preserve=preserveSource??(!name&&Boolean(state.result)&&sameObservations(rows));const spec=currentSpec(kind,name,preserve);const result=await apiJSON('/api/analyze',{spec,rows});state.spec=spec;state.demoAudio=false;state.rows=rows;state.samples=null;state.sampleRate=null;renderResult(result);const plan=await apiJSON('/api/compile',spec);renderPlan(plan);clearMessage();notify(`Analyzed ${rows.length} measurement rows. Inspect model checks and uncertainty before concluding.`);showView('workspace');}catch(error){notify(error.message,'error');}finally{setBusy(false);}}
async function analyzeAudio(samples,sampleRate,kind,name){if(state.busy)return;setBusy(true,'Estimating resonance and checking the signal…');try{const preserve=Boolean(state.result)&&samples===state.samples&&sampleRate===state.sampleRate;const spec=currentSpec(kind,name,preserve);const result=await apiJSON('/api/audio',{spec,samples:Array.from(samples),sample_rate_hz:sampleRate});state.spec=spec;state.demoAudio=false;state.samples=samples;state.sampleRate=sampleRate;state.rows=[];renderResult(result);renderPlan(await apiJSON('/api/compile',spec));clearMessage();notify('Audio analyzed. Inspect other peaks, recording duration, and sample-clock calibration.');showView('workspace');}catch(error){notify(error.message,'error');}finally{setBusy(false);}}
async function importAudio(file, ticket = state.importGate.begin()) {
  if (file.size > 40 * 1024 * 1024) throw new Error('Choose an audio file smaller than 40 MB.');
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) throw new Error('Audio decoding is unavailable in this browser.');
  const context = new AudioCtx();
  let decoded;
  try { decoded = await context.decodeAudioData(await file.arrayBuffer()); }
  finally { await context.close(); }
  if (!ticket.isCurrent() || state.domain !== 'acoustic') return;
  const prepared = await acquisition.prepareDecodedAudio(decoded);
  if (!ticket.isCurrent() || state.domain !== 'acoustic') return;
  await analyzeAudio(prepared.samples, prepared.sampleRate, 'recorded', file.name);
  if (prepared.truncated && ticket.isCurrent() && !$('message').classList.contains('error')) {
    notify('Analyzed the first 20 seconds, with equal-weight channel downmix and browser resampling to 16 kHz. Retain the full original recording for provenance.');
  }
}
async function ensureDemoAudio(){if(state.demoAudio&&!state.samples){const data=await apiJSON('/api/demo/acoustic/samples');state.samples=new Float32Array(data.samples);state.sampleRate=data.sample_rate_hz;}}
async function exportExperiment(){if(!state.result||state.busy)return;setBusy(true,'Packaging the procedure, data, calibration and analysis…');try{await ensureDemoAudio();const body={spec:state.spec};if(state.rows.length)body.rows=state.rows;if(state.samples){body.samples=Array.from(state.samples);body.sample_rate_hz=state.sampleRate;}const response=await api('/api/export',body),blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`instrumentzero-${state.domain}-${new Date().toISOString().slice(0,10)}.zip`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('Experiment package downloaded. Keep the original recording and any independent calibration records with it.');}catch(error){notify(error.message,'error');}finally{setBusy(false);}}

async function startCamera() {
  let ticket;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires a supported browser on localhost or HTTPS.');
    stopCamera();
    ticket = state.cameraGate.begin();
    $('camera-start').disabled = true; $('camera-stop').disabled = false;
    $('camera-status').textContent = 'Waiting for camera permission and playback. Stop cancels this request.';
    const stream = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}}, audio: false});
    if (!ticket.isCurrent() || state.domain !== 'stiffness') { acquisition.stopStream(stream); return; }
    state.cameraStream = stream;
    const video = $('camera-video'); video.srcObject = stream;
    await video.play();
    // Stop or a newer start may occur while the browser prepares video playback.
    if (!ticket.isCurrent() || state.cameraStream !== stream || state.domain !== 'stiffness') {
      acquisition.stopStream(stream); return;
    }
    video.parentElement.style.aspectRatio = `${video.videoWidth}/${video.videoHeight}`;
    $('camera-overlay').width = video.videoWidth; $('camera-overlay').height = video.videoHeight;
    state.marker = null; state.markerSamples = [];
    $('camera-status').textContent = 'Click a dark fiducial in the preview to select it.';
    $('camera-start').disabled = true; $('camera-stop').disabled = false;
    lastTrackingTime = 0; trackCamera(); clearMessage();
  } catch (error) {
    if (ticket && !ticket.isCurrent()) return;
    stopCamera(); notify(`Camera unavailable: ${error.message}. You can still import recorded positions.`, 'error');
  }
}
function stopCamera() {
  state.cameraGate.cancel();
  if (state.cameraFrame) cancelAnimationFrame(state.cameraFrame);
  state.cameraFrame = null;
  acquisition.stopStream(state.cameraStream); state.cameraStream = null;
  $('camera-video').srcObject = null;
  $('camera-overlay').getContext('2d').clearRect(0, 0, $('camera-overlay').width, $('camera-overlay').height);
  $('camera-status').textContent = 'Camera is off. No recording is sent.';
  $('camera-start').disabled = false; $('camera-stop').disabled = true; $('camera-capture').disabled = true;
  state.marker = null; state.markerSamples = [];
}
let lastTrackingTime = 0;
function trackCamera(time = 0) {
  if (!state.cameraStream) return;
  const video = $('camera-video'), overlay = $('camera-overlay'), ctx = overlay.getContext('2d');
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (state.marker && video.readyState >= 2) {
    const roi = acquisition.markerROI(video.videoWidth, video.videoHeight, state.marker);
    if (!roi) {
      state.marker = null; state.markerSamples = []; $('camera-capture').disabled = true;
      $('camera-status').textContent = 'Fiducial reached the image edge. Select an in-frame marker again.';
    } else {
      ctx.strokeStyle = '#e75630'; ctx.lineWidth = 2; ctx.strokeRect(roi.x, roi.y, roi.width, roi.height);
      ctx.beginPath(); ctx.moveTo(state.marker.x - 10, state.marker.y); ctx.lineTo(state.marker.x + 10, state.marker.y);
      ctx.moveTo(state.marker.x, state.marker.y - 10); ctx.lineTo(state.marker.x, state.marker.y + 10); ctx.stroke();
      if (time - lastTrackingTime > 65) {
        lastTrackingTime = time;
        const canvas = $('tracking-canvas'); canvas.width = roi.width; canvas.height = roi.height;
        const off = canvas.getContext('2d', {willReadFrequently: true});
        off.drawImage(video, roi.x, roi.y, roi.width, roi.height, 0, 0, roi.width, roi.height);
        const marker = acquisition.locateDarkMarker(off.getImageData(0, 0, roi.width, roi.height).data, roi);
        if (marker.found) {
          state.marker = {x: marker.x, y: marker.y};
          state.markerSamples.push(marker.y); state.markerSamples = state.markerSamples.slice(-30);
          $('pixel-position').textContent = fmt(marker.y, 5);
          $('camera-status').textContent = `Tracking selected dark marker · ${video.videoWidth} × ${video.videoHeight} px`;
          $('camera-capture').disabled = state.markerSamples.length < 10;
        } else {
          state.marker = null; state.markerSamples = []; $('camera-capture').disabled = true;
          $('camera-status').textContent = 'Marker lost. Click the fiducial again before capturing.';
        }
      }
    }
  }
  state.cameraFrame = requestAnimationFrame(trackCamera);
}
function chooseMarker(event) {
  if (!state.cameraStream) return;
  const rect = $('camera-overlay').getBoundingClientRect(), video = $('camera-video');
  const previewRatio = rect.width / rect.height, videoRatio = video.videoWidth / video.videoHeight;
  let width = rect.width, height = rect.height, left = rect.left, top = rect.top;
  if (previewRatio > videoRatio) { width = height * videoRatio; left += (rect.width - width) / 2; }
  else { height = width / videoRatio; top += (rect.height - height) / 2; }
  const marker = {x: (event.clientX - left) / width * video.videoWidth, y: (event.clientY - top) / height * video.videoHeight};
  if (!acquisition.markerROI(video.videoWidth, video.videoHeight, marker)) {
    notify('Choose a dark marker at least 25 pixels from the image edge.'); return;
  }
  state.marker = marker; state.markerSamples = []; $('camera-capture').disabled = true;
}
function capturePosition() {
  try {
    const force = number('capture-force');
    if (force < 0 || force > number('max-force')) throw new Error('Known force must be within your configured allowed range.');
    const position = acquisition.settledPosition(state.markerSamples, number('pixel-noise'));
    state.capturedRows.push({force_n: force, position_px: position.mean});
    $('camera-count').textContent = `${state.capturedRows.length} captured loads · latest ${fmt(force)} N / ${fmt(position.mean)} px`;
    $('camera-analyze').disabled = state.capturedRows.length < 4;
    $('csv-text').value = rowsToCSV(state.capturedRows);
    notify('Position captured. Apply the next known load and inspect tracking before capturing again.');
  } catch (error) { notify(error.message, 'error'); }
}
async function startMic() {
  let ticket;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone access requires a supported browser on localhost or HTTPS.');
    const closing = stopMic(); ticket = state.micGate.begin();
    $('mic-start').disabled = true; $('mic-stop').disabled = false; $('mic-record').disabled = true;
    $('mic-status').textContent = 'Waiting for microphone permission. Stop cancels this request.';
    await closing;
    if (!ticket.isCurrent() || state.domain !== 'acoustic') return;
    const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false}, video: false});
    if (!ticket.isCurrent() || state.domain !== 'acoustic') { acquisition.stopStream(stream); return; }
    state.micStream = stream;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const context = new AudioCtx(); state.audioContext = context;
    await context.resume();
    if (!ticket.isCurrent() || state.audioContext !== context || state.micStream !== stream || state.domain !== 'acoustic') {
      acquisition.stopStream(stream); return;
    }
    const source = context.createMediaStreamSource(stream), processor = context.createScriptProcessor(4096, 1, 1);
    state.audioSource = source; state.processor = processor;
    processor.onaudioprocess = event => {
      if (state.recording && ticket.isCurrent()) state.recordChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      event.outputBuffer.getChannelData(0).fill(0);
    };
    source.connect(processor); processor.connect(context.destination);
    $('mic-start').disabled = true; $('mic-stop').disabled = false; $('mic-record').disabled = false;
    $('mic-status').textContent = 'Microphone ready. Choose Capture to record.'; clearMessage();
  } catch (error) {
    if (ticket && !ticket.isCurrent()) return;
    await stopMic(); notify(`Microphone unavailable: ${error.message}. You can still import a recording.`, 'error');
  }
}
async function stopMic() {
  state.micGate.cancel();
  if (state.recordTimer) clearTimeout(state.recordTimer);
  state.recordTimer = null; state.recording = false; state.recordChunks = [];
  if (state.processor) { state.processor.disconnect(); state.processor.onaudioprocess = null; }
  if (state.audioSource) state.audioSource.disconnect();
  state.processor = null; state.audioSource = null;
  acquisition.stopStream(state.micStream); state.micStream = null;
  const context = state.audioContext; state.audioContext = null;
  // Reset before awaiting close, so an older close callback cannot disable a newer capture.
  $('mic-start').disabled = false; $('mic-stop').disabled = true; $('mic-record').disabled = true;
  $('mic-status').textContent = 'Microphone is off.';
  if (context) { try { await context.close(); } catch { /* Already closed. */ } }
}
function recordMic() {
  if (!state.micStream || state.recording || state.busy) return;
  const ticket = state.micGate.snapshot();
  let duration;
  try {
    duration = number('capture-duration');
    if (duration < 1 || duration > 20) throw new Error('Choose a capture duration from 1 to 20 seconds.');
  } catch (error) { notify(error.message, 'error'); return; }
  state.recordChunks = []; state.recording = true; $('mic-record').disabled = true;
  $('mic-status').textContent = `Recording for ${duration} seconds…`;
  state.recordTimer = setTimeout(async () => {
    state.recording = false; state.recordTimer = null;
    const chunks = state.recordChunks; state.recordChunks = [];
    const rate = state.audioContext?.sampleRate;
    if (!rate || !chunks.length) {
      if (ticket.isCurrent()) { $('mic-record').disabled = false; notify('No microphone samples were captured. Check the selected input and try again.', 'error'); }
      return;
    }
    try {
      const samples = acquisition.joinAudioChunks(chunks);
      const decoded = {numberOfChannels: 1, sampleRate: rate, getChannelData: () => samples};
      $('mic-status').textContent = 'Capture complete. Preparing local samples…';
      const prepared = await acquisition.prepareDecodedAudio(decoded, {maxDuration: duration});
      if (!ticket.isCurrent() || state.domain !== 'acoustic') return;
      await analyzeAudio(prepared.samples, prepared.sampleRate, 'recorded', `Local microphone capture ${new Date().toISOString()}`);
      if (ticket.isCurrent()) $('mic-status').textContent = 'Capture analyzed. Microphone remains enabled until Stop.';
    } catch (error) { if (ticket.isCurrent()) notify(error.message, 'error'); }
    finally { if (ticket.isCurrent()) $('mic-record').disabled = !state.micStream; }
  }, duration * 1000);
}

document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>showView(el.dataset.view)));
document.querySelectorAll('[data-domain]').forEach(el=>el.addEventListener('click',()=>changeDomain(el.dataset.domain)));
document.querySelectorAll('[data-capture]').forEach(el=>el.addEventListener('click',()=>showCapture(el.dataset.capture)));
$('family-select').addEventListener('change',event=>changeDomain(event.target.value));
$('spec-form').addEventListener('submit',event=>{event.preventDefault();compile();});
$('demo-button').addEventListener('click',()=>demo());$('example-choice').addEventListener('change',()=>demo());
$('export-button').addEventListener('click',exportExperiment);
$('analyze-csv').addEventListener('click',()=>{try{analyzeRows(parseCSV($('csv-text').value),'imported');}catch(error){notify(error.message,'error');}});
$('data-file').addEventListener('change', async event => {
  const file = event.target.files?.[0]; if (!file) return;
  const ticket = state.importGate.begin(), selectedDomain = state.domain;
  try {
    if (selectedDomain === 'acoustic') await importAudio(file, ticket);
    else {
      if (file.size > 2 * 1024 * 1024) throw new Error('Choose a CSV smaller than 2 MB.');
      const text = await file.text();
      if (!ticket.isCurrent() || state.domain !== selectedDomain) return;
      $('csv-text').value = text; $('source-name').value = file.name;
      await analyzeRows(parseCSV(text), 'imported', file.name, false);
    }
  } catch (error) { if (ticket.isCurrent()) notify(error.message, 'error'); }
  finally { if (ticket.isCurrent()) event.target.value = ''; }
});
$('apply-calibration').addEventListener('click',async()=>{if(!state.result){try{state.spec=currentSpec();notify('Calibration settings saved for the next analysis.');}catch(error){notify(error.message,'error');}return;}if(state.domain==='stiffness'&&state.rows.length)analyzeRows(state.rows,state.spec?.source_kind,state.spec?.source_name,true);else{try{await ensureDemoAudio();if(state.samples)await analyzeAudio(state.samples,state.sampleRate,state.spec?.source_kind,state.spec?.source_name);else notify('Import an audio recording to recompute with a different calibration.');}catch(error){notify(error.message,'error');}}});
$('camera-start').addEventListener('click',startCamera);$('camera-stop').addEventListener('click',stopCamera);$('camera-overlay').addEventListener('click',chooseMarker);$('camera-capture').addEventListener('click',capturePosition);$('camera-analyze').addEventListener('click',()=>analyzeRows([...state.capturedRows],'recorded','Local camera fiducial positions'));
$('mic-start').addEventListener('click',startMic);$('mic-stop').addEventListener('click',stopMic);$('mic-record').addEventListener('click',recordMic);
window.addEventListener('pagehide',()=>{stopCamera();stopMic();});
setupDiagram();
// The landing example is a labeled controlled simulation. Sensors always require a deliberate click.
demo(true);
