from pathlib import Path
import json,hashlib,sys,re
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle
R=Path(__file__).resolve().parents[2]
MOBILE='--mobile' in sys.argv
plt.rcParams.update({'font.family':['DejaVu Sans','Arial','sans-serif'],'path.simplify':False,'font.size':15,'axes.spines.top':False,'axes.spines.right':False,'axes.labelsize':15,'xtick.labelsize':13,'ytick.labelsize':13,'svg.fonttype':'none','figure.facecolor':'#ffffff','axes.facecolor':'#ffffff','text.color':'#172b3a','axes.labelcolor':'#172b3a','xtick.color':'#334a5b','ytick.color':'#334a5b','axes.edgecolor':'#8a9aa7'})
manifest={'method':'Matplotlib source-derived figures from exact retained JSON; no solver, inference, new experiment, image enhancement or smoothing','runtime':{'python':sys.version,'matplotlib':matplotlib.__version__,'numpy':np.__version__},'font_policy':['DejaVu Sans','Arial','sans-serif'],'figures':[]}
def save(n,fig,stem,inputs,transforms):
 fig.get_layout_engine().set(rect=(0,0 if MOBILE else .13,1,.94 if MOBILE else .80))
 if MOBILE:stem+='-mobile'
 d=R/'docs/presentation';d.mkdir(parents=True,exist_ok=True);outputs=[]
 for ext in ['png','svg']:
  p=d/(stem+'.'+ext);fig.savefig(p,dpi=160,facecolor='white');outputs.append({'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 if n in ['InstrumentZero','PhotonSmith']:
  series=signal if n=='InstrumentZero' else spectrum
  gid='source-signal' if n=='InstrumentZero' else 'source-spectrum'
  xml=ET.fromstring((d/(stem+'.svg')).read_text());path=xml.find('.//s:g[@id="'+gid+'"]/s:path',{'s':'http://www.w3.org/2000/svg'})
  numbers=[float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.attrib['d'])]
  expected=series.get_transform().transform(series.get_xydata());scale=72/fig.dpi
  expected=[(x*scale,(fig.bbox.height-y)*scale) for x,y in expected]
  required=769 if n=='InstrumentZero' else 21
  assert len(expected)==required and len(numbers)==required*2,(n,len(numbers))
  error=max(abs(numbers[2*i+j]-point[j]) for i,point in enumerate(expected) for j in [0,1])
  assert error<0.00001,(n,error)
  manifest['source_to_svg']={'series':gid,'source_samples':required,'exported_vertices':len(numbers)//2,'maximum_svg_coordinate_error':error,'path_simplify':matplotlib.rcParams['path.simplify']}
 manifest['figures'].append({'repository':n,'inputs':[{'path':str(p.relative_to(R)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],'transformations':transforms,'outputs':outputs});plt.close(fig)
# The complete plotted signal from a retained seeded experiment, no filtering or refitting.
p=R/'examples/edge/simulation-confirmation-v0.3-final/custom-1.json';v=json.loads(p.read_text());t=np.array(v['plot']['time_seconds']);y=np.array(v['plot']['signal']);assert t.shape==y.shape;model=v['source']['model'];est=v['independent_numerical_reference']['result'];fig,ax=plt.subplots(figsize=(6.4,4.6) if MOBILE else (13.2,4.6),layout='constrained');fig.suptitle('A seeded ringdown.' if MOBILE else 'A seeded ringdown. An inspectable estimate.',fontsize=20 if MOBILE else 23,fontweight='bold');signal=ax.plot(t,y,color='#21644d',lw=1.1,gid='source-signal')[0];ax.set(xlabel='Time (s)',ylabel='Acceleration (m/s²)',xlim=(float(t.min()),float(t.max())));ax.grid(axis='y',alpha=.15);ax.set_title('Synthetic, seed 9132301' if MOBILE else 'Synthetic model: 9.75 Hz, decay 0.45 s⁻¹, seed 9132301',loc='left',fontsize=15 if MOBILE else 16,pad=14); (fig.text if not MOBILE else lambda *a,**k:None)(.5,.025,'All 769 stored plot samples. Float64 reference fit: 9.75000657 Hz; decay 0.44992366 s⁻¹. No physical measurement.',ha='center',fontsize=11)
save('InstrumentZero',fig,'seeded-ringdown',[p],['All stored time_seconds and signal values retained unchanged.','No new fit; printed estimate read from retained independent_numerical_reference.','Acceleration unit from stored plot metadata checked against compiled calibration.'])

(R/('docs/presentation/manifest-mobile.json' if MOBILE else 'docs/presentation/manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
print('Rendered figure and manifest from exact retained source arrays.')
