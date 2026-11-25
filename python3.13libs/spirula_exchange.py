"""Pinned local PlayCanvas conversions, using the existing Houdini job monitor."""
import json,os,shutil,subprocess,time,uuid
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def tool_paths():
    node=ROOT/'runtime/node/node.exe';cli=ROOT/'runtime/splat-tools/node_modules/@playcanvas/splat-transform/bin/cli.mjs'
    if not node.is_file() or not cli.is_file():raise ValueError('Outils PlayCanvas absents du package Spirula.')
    return str(node),str(cli)

def zero_harmonics(path):
    try:
        with Path(path).open('rb') as stream:
            names=[];count=0
            for _ in range(512):
                line=stream.readline().decode('ascii').strip()
                if line.startswith('element vertex '):count=int(line.split()[2])
                elif line.startswith('property '):
                    parts=line.split()
                    if len(parts)!=3 or parts[1]!='float':return False
                    names.append(parts[2])
                elif line=='end_header':break
            else:return False
            offset=stream.tell()
        indices=[i for i,n in enumerate(names) if n.startswith('f_rest_')]
        if not indices:return True
        rows=np.memmap(path,dtype='<f4',mode='r',offset=offset,shape=(count,len(names)))
        return all(not np.any(rows[start:start+32768,indices]) for start in range(0,count,32768))
    except (OSError,ValueError,UnicodeError):return False

def convert(source,target,device='auto',status=None,cancel=None,log_path=None,axis_preset='preserve',up_axis='Y',meters_per_unit=1.):
    source=Path(source).resolve();target=Path(target).resolve();node,cli=tool_paths()
    if not source.is_file():raise ValueError('PLY source absent : '+str(source))
    if source==target:raise ValueError('La conversion doit écrire un autre fichier que la source.')
    if target.suffix.lower() not in ('.sog','.spz','.ply'):raise ValueError('Format de sortie attendu : .sog, .spz ou .ply.')
    if cancel and Path(cancel).exists():raise InterruptedError('Conversion arrêtée.')
    target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.partial_'+uuid.uuid4().hex[:8]+'_'+target.name);log_path=Path(log_path or target.with_suffix('.conversion.log'));zero=zero_harmonics(source) if source.suffix.lower()=='.ply' else False
    choices=['cpu'] if device=='cpu' else [device,'cpu'] if device in ('d3d12','vulkan') else ['d3d12' if os.name=='nt' else 'vulkan','cpu'];attempts=[];begin=time.monotonic()
    try:
        for backend in choices:
            args=[node,cli,'-w',str(source)]
            if axis_preset=='playcanvas':
                if up_axis.upper() not in ('Y','Z') or not np.isfinite(meters_per_unit) or meters_per_unit<=0:raise ValueError('Axe vertical ou unités de scène invalides.')
                args+=['-r','0,0,180']
                if up_axis.upper()=='Z':args+=['-r','-90,0,0']
                if meters_per_unit!=1:args+=['-s',str(meters_per_unit)]
            elif axis_preset!='preserve':raise ValueError('Convention d’axes inconnue : '+axis_preset)
            if zero:args+=['-H','0']
            args+=['-g','cpu'] if backend=='cpu' else ['-g','0','--gpu-backend',backend]
            args.append(str(temp));message='Conversion PlayCanvas : '+('CPU' if backend=='cpu' else 'WebGPU '+backend)
            if status:status('exporting',message)
            with log_path.open('a',encoding='utf-8') as log:
                log.write('\n'+message+'\n');log.flush();process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                while process.poll() is None:
                    if cancel and Path(cancel).exists():process.terminate();process.wait();raise InterruptedError('Conversion arrêtée.')
                    time.sleep(.2)
            attempts.append({'backend_option':backend,'exit_code':process.returncode})
            if process.returncode==0 and temp.is_file():break
        else:raise RuntimeError('Conversion PlayCanvas en échec ; voir '+str(log_path))
        temp.replace(target);report={'tool':'@playcanvas/splat-transform','version':'3.10.3','source':str(source),'target':str(target),'input_bytes':source.stat().st_size,'output_bytes':target.stat().st_size,'seconds':time.monotonic()-begin,'zero_sh_bands_removed':zero,'attempts':attempts,'fallback_used':len(attempts)>1,'axis_preset':axis_preset,'source_up_axis':up_axis,'meters_per_unit':meters_per_unit};target.with_suffix(target.suffix+'.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
    finally:
        if temp.exists():temp.unlink()

def start(node,source,target):
    import spirula_render as render,spirula_monitor as monitor
    if node.sessionId() in render.JOBS:raise ValueError('Une conversion est déjà active pour ce node.')
    tool_paths();source=Path(source).resolve();target=Path(target).resolve()
    if target.suffix.lower() not in ('.sog','.spz'):raise ValueError('Choisir un fichier .sog ou .spz pour cet export.')
    if source==target:raise ValueError('Le PLY original doit rester distinct de l’export optimisé.')
    folder=target.parent/'.spirula_jobs'/('export_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True);snapshot=folder/'master.ply'
    try:os.link(source,snapshot)
    except OSError:shutil.copy2(source,snapshot)
    device=node.parm('web_device').evalAsString() if node.parm('web_device') else 'auto';axis=node.parm('web_axes').evalAsString() if node.parm('web_axes') else 'playcanvas';up='Y';units=1.
    if node.userData('spirula_arch_role'):
        import spirula_arch
        box=spirula_arch.bounds(node);up=box['up'];units=box['meters_per_unit']
    data={'schema':1,'exchange':True,'folder':str(folder),'started':time.time(),'views':[],'source':str(snapshot),'original_source':str(source),'target':str(target),'device':device,'axis_preset':axis,'up_axis':up,'meters_per_unit':units,'train':False};path=folder/'job.json';render.atomic_json(path,data);node.parm('jobfile').set(str(path));node.setUserData('spirula_exchange_ui','1');monitor.OVERRIDES.pop(node.sessionId(),None);result=render.start(node,train=False,resume=True);node.parm('status').set('Conversion en arrière-plan…');return result

def launch(node,export_master,target):
    import spirula_monitor as monitor
    node.setUserData('spirula_exchange_ui','1')
    return monitor.launch(node,lambda:start(node,export_master(),target),'Préparation de l’export optimisé…')

def worker(data,status):
    try:
        report=convert(data['source'],data['target'],data.get('device','auto'),status,Path(data['folder'])/'cancel.request',Path(data['folder'])/'render.log',data.get('axis_preset','preserve'),data.get('up_axis','Y'),data.get('meters_per_unit',1.))
    except InterruptedError:status('cancelled','Conversion arrêtée ; sortie précédente conservée.');return
    status('done','Export prêt : %.1f Mo (PLY source %.1f Mo)'%(report['output_bytes']/1e6,report['input_bytes']/1e6),output=data['target'],report=report)
