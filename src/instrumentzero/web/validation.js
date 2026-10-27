'use strict';
(() => {
  const element = id => document.getElementById(id);
  const escape = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (n,d=5) => Number.isFinite(n) ? Number(n.toPrecision(d)).toLocaleString('en-US',{maximumFractionDigits:7}) : 'unavailable';
  let replay=null, stageIndex=0, loaded=false, replayEpoch=0;
  async function json(url) { const response=await fetch(url); const body=await response.json(); if(!response.ok)throw new Error(body.error||`HTTP ${response.status}`); return body; }
  function message(text) { element('validation-message').textContent=text; element('validation-message').hidden=false; }
  function query() { return `?budget=${encodeURIComponent(element('replay-budget').value)}&policy=${encodeURIComponent(element('replay-policy').value)}&seed=0`; }
  function resetReplay() { replay=null;stageIndex=0;element('replay-stages').textContent='';element('replay-chart').textContent='Start the recorded replay for these settings.';element('replay-summary').textContent='';element('replay-stage-detail').textContent='';element('replay-next').disabled=true;element('replay-export').disabled=true; }
  async function download(url,name) { try { const response=await fetch(url); if(!response.ok){const error=await response.json();throw new Error(error.error||'Export failed');} const blob=await response.blob(),link=document.createElement('a'),object=URL.createObjectURL(blob);link.href=object;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(object),1000); }catch(error){message(error.message);} }
  function renderStage() {
    const stage=replay.stages[stageIndex];
    let current=replay.initial_result;
    for(let i=0;i<=stageIndex;i++)if(replay.stages[i].result)current=replay.stages[i].result;
    element('replay-stages').innerHTML=replay.stages.map((s,i)=>`<span class="${i===stageIndex?'current':i<stageIndex?'done':''}">${i+1} / ${escape(s.stage.replaceAll('_',' '))}</span>`).join('');
    lineChart('replay-chart',current.fit.x.map(x=>x*1000),current.fit.observed,{predicted:current.fit.predicted,xLabel:'Revealed actuator setting / mm',yLabel:'Recorded reference force / N'});
    let detail=`<h3>${escape(stage.stage.replaceAll('_',' '))}</h3>`;
    if(stage.selection) detail+=`<p>Selected source point ${stage.selection.point}: ${number(stage.selection.displacement_m*1000)} mm. Its recorded force is not revealed in this selection stage.</p><p>Gaussian design-proxy variance reduction: ${number(stage.selection.gaussian_stiffness_variance_reduction_proxy)} (N/m)². This finite proxy is not the variance of the broad Student-t inference distribution.</p>`;
    else if(stage.observation)detail+=`<p>Revealed the actual source response: ${number(stage.observation.reference_force_n)} N at ${number(stage.observation.displacement_m*1000)} mm. No response was generated.</p>`;
    else if(stage.stage==='held_out_reference_check')detail+=`<p>After all selections, check ${replay.reference_check.held_out_points} excluded unloading observations. Reference-force RMSE: ${number(replay.initial_reference_check.rmse_reference_force_n)} → ${number(replay.reference_check.rmse_reference_force_n)} N.</p>`;
    else detail+='<p>Infer from the three predeclared loading observations. Their residual scale has only one degree of freedom, so uncertainty remains broad.</p>';
    element('replay-stage-detail').innerHTML=detail;
    const q=current.quantity,interval=q.interval_95;
    element('replay-summary').innerHTML=`<span class="eyebrow">CONDITIONAL STIFFNESS</span><h2>${number(q.value)} <small>N/m</small></h2><p>Conditional interval: ${number(interval[0])}–${number(interval[1])} N/m.</p><p>${current.samples} observed records. Shared length/force uncertainty values are sensitivity assumptions, not source certificates.</p><p class="source-badge">PHYSICAL ACCURACY NOT CERTIFIED</p><p>The conventional endpoint policy ties information selection on this small pool. Another observation can worsen held-out error.</p><a href="https://doi.org/10.17632/syjkdyzmxj.1" target="_blank" rel="noreferrer">Source measurements ↗</a>`;
    element('replay-next').disabled=stageIndex>=replay.stages.length-1;
    element('replay-next').textContent=stageIndex>=replay.stages.length-1?'Replay complete':'Replay next stage →';
  }
  async function loadReplay() { const epoch=++replayEpoch;resetReplay();element('replay-load').disabled=true;element('replay-policy').disabled=true;element('replay-budget').disabled=true;try { const bundle=await json('/api/replay'+query());if(epoch!==replayEpoch)return;replay=bundle;stageIndex=0;renderStage();element('replay-export').disabled=false;element('validation-message').hidden=true; }catch(error){message(error.message);}finally{if(epoch===replayEpoch){element('replay-load').disabled=false;element('replay-policy').disabled=false;element('replay-budget').disabled=false;}} }
  function renderPTB(result) {
    const c=result.comparison,limit=Math.max(...c.difference_db.flat().map(Math.abs)),cell=9;
    element('ptb-metrics').innerHTML=`<div><span>Mean device difference</span><strong>${number(c.mean_difference_db,4)} dB</strong></div><div><span>Twice spatial SD, not mean uncertainty</span><strong>${number(c.twice_spatial_sd_db,4)} dB</strong></div><div><span>Source-matched positions</span><strong>${number(c.positions)}</strong></div>`;
    const rectangles=c.difference_db.map((row,y)=>row.map((value,x)=>{const strength=Math.min(1,Math.abs(value)/limit),hue=value>=0?15:220;return `<rect x="${x*cell}" y="${y*cell}" width="${cell}" height="${cell}" fill="hsl(${hue} 58% ${96-strength*52}%)"><title>Row ${y+1}, column ${x+1}: ${number(value)} dB</title></rect>`;}).join('')).join('');
    element('ptb-heatmap').innerHTML=`<svg viewBox="-6 -6 309 327" role="img" aria-label="33 by 33 recorded sound-level difference grid">${rectangles}<text x="0" y="316" font-family="monospace" font-size="8" fill="currentColor">BLUE: NEGATIVE / ORANGE: POSITIVE / ±${number(limit,3)} dB</text></svg>`;
    element('ptb-calibration').innerHTML=`<h3>What is calibrated?</h3><p>At 20 kHz, each source microphone pressure sensitivity has expanded uncertainty 0.6 dB with coverage factor k=2. That is a sensitivity calibration, not a total per-position error bound.</p><p>The result reproduces the source's reported 0.71 dB mean difference and 5.95 dB spatial dispersion. The 1,089 positions are not independent repeat trials.</p><a href="https://doi.org/10.7795/720.20211214" target="_blank" rel="noreferrer">PTB source and calibration ↗</a>`;
    element('ptb-limits').innerHTML='<p><strong>Evidence limits:</strong> Raw recordings are retained and inspected as ADC signals. Complete raw-WAV-to-Pa reconstruction, precise cell coordinates and sample-clock calibration remain unverified. Pressure calibration does not establish absolute frequency accuracy. No new physical acquisition occurred.</p>';
  }
  function renderSoftware(result) {
    let html='<p>Generated media and mocked permission/device APIs test the actual acquisition software. They do not calibrate a physical camera, microphone, or sample clock.</p>';
    if(result.acquisition)html+=`<p><strong>${number(result.acquisition.tests_passed)} acquisition checks passed.</strong> ${escape(result.acquisition.summary||'Shared production transforms and actual capture entrypoints are tested without hardware.')}</p>`;
    if(result.acoustic){html+='<table class="evidence-table"><thead><tr><th>Generated regime</th><th>Reliable</th><th>Envelope coverage</th></tr></thead><tbody>';for(const row of result.acoustic.summaries)html+=`<tr><th>${escape(row.regime.replaceAll('_',' '))} (${row.trials})</th><td>${number(row.reliable_fraction*100,3)}%</td><td>${row.envelope_coverage===null?'no scalar reference':number(row.envelope_coverage*100,3)+'%'}</td></tr>`;html+='</tbody></table><p>Coverage is empirical for these declared signal distributions. Fourfold unmodeled clock drift remains undetectable from the tone alone and sharply reduces coverage.</p>';}
    element('software-validation').innerHTML=html;
  }
  async function loadAll() { if(loaded)return;loaded=true;element('ptb-limits').textContent='Loading and checking the retained PTB sources…';await Promise.allSettled([loadReplay(),json('/api/validation/ptb').then(renderPTB).catch(error=>{element('ptb-limits').textContent='Calibrated reference unavailable: '+error.message+'. Restore the source fixtures and refresh this page.';message(error.message);}),json('/api/validation/software').then(renderSoftware).catch(error=>{element('software-validation').textContent='Acceptance evidence unavailable: '+error.message;message(error.message);})]); }
  document.querySelector('[data-view="validation"]').addEventListener('click',loadAll);
  element('replay-load').addEventListener('click',loadReplay);
  element('replay-policy').addEventListener('change',resetReplay);
  element('replay-budget').addEventListener('change',resetReplay);
  element('replay-next').addEventListener('click',()=>{if(replay&&stageIndex<replay.stages.length-1){stageIndex++;renderStage();}});
  element('replay-export').addEventListener('click',()=>{if(!replay){message('Start and inspect a recorded replay before exporting it.');return;}const shown=`?budget=${replay.measurement_budget}&policy=${encodeURIComponent(replay.policy)}&seed=${replay.provenance.random_seed}`;download('/api/replay/export'+shown,'instrumentzero-recorded-replay.zip');});
  element('ptb-export').addEventListener('click',()=>download('/api/validation/ptb/export','instrumentzero-calibrated-acoustic.zip'));
})();
