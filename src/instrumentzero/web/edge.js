/* The configuration epoch owns every visible result and export. */
(() => {
  const el=id=>document.getElementById(id), names={raw_host:'Raw → host',calibrated_edge:'Calibrate on edge',filtered_edge:'Filter on edge'};
  let spec=null,epoch=0,generation=0,loaded=null,pending=null,unapplied=false;
  const text=(id,v)=>{el(id).textContent=v;};
  function status(message,kind=''){text('status',message);el('status').className=`status ${kind}`;}
  function invalidate(message='Configuration changed. Run a new comparison.'){
    epoch++;generation++;loaded=null;if(pending)pending.abort();pending=null;el('run').disabled=!spec||unapplied;
    el('result').hidden=true;el('comparison').hidden=true;el('empty').hidden=false;el('comparison-empty').hidden=false;
    el('export').removeAttribute('href');text('epoch',`${epoch} / no result for this configuration`);status(message);
  }
  function updateSpec(){if(!spec)return;if(unapplied){invalidate('Apply the edited specification before changing basic controls.');return;}spec.dsp.decimation=Number(el('decimation').value);spec.resources.raw_validation=el('raw-validation').checked;spec.resources.link_bytes_per_second=Number(el('bandwidth').value);el('spec-json').value=JSON.stringify(spec,null,2);invalidate();}
  function waveform(plot){
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 800 180');svg.setAttribute('role','img');
    const title=document.createElementNS(ns,'title');title.textContent='Processed synthetic signal after FIR startup removal';svg.append(title);
    for(let i=0;i<7;i++){const line=document.createElementNS(ns,'line');for(const [k,v]of Object.entries({x1:0,x2:800,y1:i*30,y2:i*30,stroke:'#e2e4db'}))line.setAttribute(k,String(v));svg.append(line);}
    const y=plot.signal,extent=Math.max(...y.map(Math.abs),.001),path=document.createElementNS(ns,'path');
    path.setAttribute('d',y.map((v,i)=>`${i?'L':'M'}${(i*800/Math.max(1,y.length-1)).toFixed(2)},${(90-v*78/extent).toFixed(2)}`).join(' '));path.setAttribute('fill','none');path.setAttribute('stroke','#c84424');path.setAttribute('stroke-width','1.2');svg.append(path);el('waveform').replaceChildren(svg);
    text('plot-unit',`TIME / 0–${plot.time_seconds.at(-1).toFixed(2)} s · ${plot.unit}`);
  }
  function render(run){
    loaded=run;const chosen=run.comparisons.find(c=>c.selected),fit=chosen.result;
    el('result').hidden=false;el('comparison').hidden=false;el('empty').hidden=true;el('comparison-empty').hidden=true;
    text('frequency',fit.frequency_hz===null?'Rejected':fit.frequency_hz.toFixed(4));text('frequency-note',fit.frequency_hz===null?'No supported estimate':`Model fit · resolution envelope ±${fit.frequency_resolution_clock_envelope_hz.toFixed(3)} Hz`);
    text('damping',fit.damping_ratio===null?'Unavailable':fit.damping_ratio.toFixed(5));text('damping-note',fit.damping_ratio===null?'Decay/model criteria not met':'Single-mode decay model only');text('placement',names[chosen.mode]);text('epoch',`${epoch} / ${run.compiled.spec_sha256.slice(0,16)}`);
    const reasons=[...new Set([...(fit.reasons||[]),...(fit.damping_rejection_reasons||[])])];el('rejection').hidden=!reasons.length;
    const heading=document.createElement('strong');heading.textContent=fit.status==='rejected'?'Signal rejected':'Damping withheld';const reason=document.createElement('span');reason.textContent=reasons.join(' ');el('rejection').replaceChildren(heading,reason);waveform(run.plot);
    const max=Math.max(...run.comparisons.map(c=>c.metrics.wire_bytes_including_headers));el('transfer-bars').replaceChildren();el('comparison-rows').replaceChildren();
    run.comparisons.forEach(c=>{
      const bar=document.createElement('div');bar.className=`transfer-bar ${c.selected?'chosen':''}`;const label=document.createElement('span');label.textContent=names[c.mode];const track=document.createElement('div');track.className='bar-track';const fill=document.createElement('div');fill.className='bar-fill';fill.style.width=`${100*c.metrics.wire_bytes_including_headers/max}%`;track.append(fill);const bytes=document.createElement('code');bytes.textContent=`${c.metrics.wire_bytes_including_headers.toLocaleString()} B`;bar.append(label,track,bytes);el('transfer-bars').append(bar);
      const tr=document.createElement('tr');if(c.selected)tr.className='selected';[names[c.mode]+(c.selected?' ✓':''),c.metrics.wire_bytes_including_headers.toLocaleString(),(c.metrics.processing_wall_seconds*1000).toFixed(2),c.frequency_disagreement_hz===null?'—':c.frequency_disagreement_hz.toExponential(2),c.resource_model.legal_under_declared_model?'Within model':c.resource_model.reasons.join('; ')].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});el('comparison-rows').append(tr);
    });
    const raw=run.comparisons[0].metrics.wire_bytes_including_headers,saving=100*(1-chosen.metrics.wire_bytes_including_headers/raw);
    text('measurement-note',`${saving.toFixed(1)}% fewer transferred bytes for the selected placement. Headers and timestamps included. Host run includes initialization and analysis. Physical latency, MCU utilization and power are unmeasured. Δf uses a float64 numerical reference on the same input.`);
    el('export').href=run.artifact_url;if(run.lifecycle_demo){status('Simulated disconnect cleared the old session. Reconnected with a new session; physical unplug behavior remains unverified.');return;}status(fit.status==='rejected'?'Completed. Signal rejected; evidence remains exportable.':'Completed. Result and evidence belong to this configuration.');
  }
  el('experiment-form').addEventListener('submit',async event=>{
    event.preventDefault();if(!spec||unapplied)return;const current=++generation,controller=new AbortController();pending=controller;el('run').disabled=true;
    loaded=null;el('result').hidden=true;el('comparison').hidden=true;el('export').removeAttribute('href');status('Running C core, reference analysis and placement comparisons…','pending');
    const payload={spec:JSON.parse(JSON.stringify(spec)),scenario:el('scenario').value,seconds:Number(el('duration').value),seed:20261029};
    try{const response=await fetch('/api/edge/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});const run=await response.json();if(current!==generation)return;if(!response.ok)throw new Error(run.error||'Comparison could not run.');render(run);}
    catch(error){if(current!==generation||error.name==='AbortError')return;el('empty').hidden=false;el('comparison-empty').hidden=false;status(`${error.message} Adjust the specification or choose another signal, then run again.`,'error');}
    finally{if(current===generation){pending=null;el('run').disabled=false;}}
  });
  ['decimation','raw-validation','bandwidth'].forEach(id=>el(id).addEventListener('change',updateSpec));['scenario','duration'].forEach(id=>el(id).addEventListener('change',()=>invalidate()));
  el('spec-json').addEventListener('input',()=>{unapplied=true;invalidate('Specification text changed. Apply it before running.');el('run').disabled=true;});
  el('apply-spec').addEventListener('click',()=>{try{const candidate=JSON.parse(el('spec-json').value);if(!candidate.dsp||!candidate.resources||!candidate.source)throw new Error('Expected source, dsp and resources.');spec=candidate;unapplied=false;el('decimation').value=String(spec.dsp.decimation);el('raw-validation').checked=spec.resources.raw_validation;el('bandwidth').value=String(spec.resources.link_bytes_per_second);invalidate('Specification applied. Run to validate and compare.');}catch(error){el('run').disabled=true;status(`Specification not applied: ${error.message}`,'error');}});
  el('export').addEventListener('click',event=>{if(!loaded)event.preventDefault();});el('run').disabled=true;
  fetch('/api/edge/spec').then(r=>{if(!r.ok)throw new Error('Could not load specification.');return r.json();}).then(value=>{if(spec!==null||unapplied)return;spec=value;el('spec-json').value=JSON.stringify(spec,null,2);el('run').disabled=false;}).catch(error=>status(error.message,'error'));
})();
