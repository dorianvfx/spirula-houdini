"""Photoreal render datasets and resumable Spirula training jobs."""
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid
import re
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
JOBS={}


def atomic_json(path,data):
    path=Path(path);temp=path.with_name('.partial_'+path.name)
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
    for i in range(10):
        try:os.replace(temp,path);return
        except PermissionError:time.sleep(.03)
    os.replace(temp,path)


def look_at(position,target):
    p=np.array(position,float);back=p-np.array(target,float);back/=np.linalg.norm(back)
    up=np.array([0.,1.,0.])
    if abs(np.dot(back,up))>.995:up=np.array([0.,0.,1.])
    right=np.cross(up,back);right/=np.linalg.norm(right);up=np.cross(back,right)
    m=np.eye(4);m[:3,:3]=np.stack([right,up,back],axis=1);m[:3,3]=p
    return m


def entry(matrix,width,height,fov):
    return {'transform_matrix':np.asarray(matrix).tolist(),'fl_x':width/(2*math.tan(math.radians(fov)/2)),
            'fl_y':width/(2*math.tan(math.radians(fov)/2)),'cx':width/2,'cy':height/2,'w':width,'h':height}


def frame_numbers(spec):
    result=[]
    for token in spec.replace(',',' ').split():
        if ':' not in token:result.append(float(token));continue
        fields=[float(x) for x in token.split(':')]
        if len(fields) not in (2,3):raise ValueError('Plage caméra : début:fin:pas, par exemple 1:120:4.')
        first,last=fields[:2];step=fields[2] if len(fields)==3 else 1
        if step==0 or (last-first)*step<0:raise ValueError('Le pas de la plage caméra est invalide.')
        count=int(math.floor((last-first)/step))+1
        if count>10000:raise ValueError('Au maximum 10 000 poses par plage caméra.')
        result.extend(first+i*step for i in range(count))
    return result


def camera_plan(node):
    import hou
    if node.userData('spirula_arch_request'):
        return json.loads(node.userData('spirula_arch_request'))['views']
    from spirula_object import sop
    width=node.evalParm('width');height=node.evalParm('height');fov=node.evalParm('fov');mode=node.evalParm('capture_mode')
    result=[]
    if mode==0:
        source=hou.node(node.evalParm('source'))
        if source is None:raise ValueError('Choisir le mesh/SOP de référence pour le tour d’objet.')
        from spirula_transform import bounding_box
        source=sop(source);bb=bounding_box(source.geometry(),source.creator().worldTransform())
        center=np.array(bb.center());radius=node.evalParm('radius')
        if radius<=0:radius=float(np.linalg.norm(bb.sizevec()))*.6/max(.1,math.sin(math.radians(fov)/2))
        elevations=[float(x) for x in node.evalParm('elevations').split()]
        for elevation in elevations:
            a=math.radians(elevation)
            for i in range(node.evalParm('views')):
                t=2*math.pi*i/node.evalParm('views');pos=center+radius*np.array([math.cos(a)*math.sin(t),math.sin(a),math.cos(a)*math.cos(t)])
                result.append(entry(look_at(pos,center),width,height,fov))
    elif mode==1:
        paths=node.evalParm('cameras').split();usd_stage=None
        if node.evalParm('backend')>=2:
            from pxr import UsdGeom,Usd
            source_lop=hou.node(node.evalParm('lop_source'))
            if source_lop is None:raise ValueError('Choisir un LOP final pour lire les caméras USD.')
            usd_stage=source_lop.stage()
            if usd_stage is None:raise ValueError('Le stage Solaris ne peut pas cuire.')
            if not paths:paths=[str(p.GetPath()) for p in usd_stage.Traverse() if p.IsA(UsdGeom.Camera)]
        if usd_stage is not None and any('*' in p for p in paths):
            import fnmatch
            patterns=paths;paths=[str(p.GetPath()) for p in usd_stage.Traverse() if p.IsA(UsdGeom.Camera) and any(fnmatch.fnmatchcase(str(p.GetPath()),pattern) for pattern in patterns)]
        cameras=hou.node('/').glob(node.evalParm('cameras')) if usd_stage is None and '*' in node.evalParm('cameras') else [hou.node(x) for x in paths]
        frames=frame_numbers(node.evalParm('camera_frames')) or [hou.frame()]
        oldframe=hou.frame()
        try:
            for frame in frames:
                hou.setFrame(frame)
                for index,cam in enumerate(cameras):
                    if (cam is None or not cam.parm('focal')) and usd_stage is not None:
                        usd_camera=UsdGeom.Camera(usd_stage.GetPrimAtPath(paths[index]))
                        if not usd_camera:raise ValueError('Caméra USD introuvable : '+paths[index])
                        if usd_camera.GetProjectionAttr().Get(frame)!='perspective':raise ValueError('Caméra USD en perspective requise : '+paths[index])
                        if any(abs(a.Get(frame) or 0)>1e-8 for a in (usd_camera.GetHorizontalApertureOffsetAttr(),usd_camera.GetVerticalApertureOffsetAttr())):raise ValueError('Les décentrements de caméra USD ne sont pas pris en charge : '+paths[index])
                        pose=UsdGeom.XformCache(Usd.TimeCode(frame)).GetLocalToWorldTransform(usd_camera.GetPrim());mat=np.array(pose).T
                        e=entry(mat,width,height,fov);e['fl_x']=e['fl_y']=width*usd_camera.GetFocalLengthAttr().Get(frame)/usd_camera.GetHorizontalApertureAttr().Get(frame);result.append(e);continue
                    if cam is None or not cam.parm('focal'):raise ValueError('Une caméra OBJ est introuvable.')
                    if cam.parm('projection') and cam.parm('projection').evalAsString()!='perspective':raise ValueError('Les caméras d’apprentissage doivent être en perspective : '+cam.path())
                    if any(cam.parm(p) and abs(cam.evalParm(p))>1e-8 for p in ('winx','winy')):raise ValueError('Pour la capture, utiliser une caméra centrée (Window Offset = 0) : '+cam.path())
                    mat=np.array(cam.worldTransform().asTuple()).reshape(4,4).T
                    e=entry(mat,width,height,fov);e['fl_x']=e['fl_y']=width*cam.evalParm('focal')/cam.evalParm('aperture');result.append(e)
        finally:hou.setFrame(oldframe)
    else:
        if mode==3:
            from spirula_insert import exterior_plan
            result=exterior_plan(node)
            for i,e in enumerate(result):e['file_path']='images/%05d.png'%i
            return result
        path=hou.node(node.evalParm('path_sop'))
        if path is None:raise ValueError('Choisir une courbe/SOP décrivant le parcours intérieur.')
        path=sop(path);p=np.array(path.geometry().pointFloatAttribValues('P')).reshape(-1,3);matrix=np.array(path.creator().worldTransform().asTuple()).reshape(4,4)
        p=p@matrix[:3,:3]+matrix[3,:3]
        lengths=np.linalg.norm(np.diff(p,axis=0),axis=1);arc=np.r_[0,np.cumsum(lengths)]
        if len(p)<2 or arc[-1]<=0:raise ValueError('Le parcours doit contenir au moins deux points distincts.')
        distances=np.linspace(0,arc[-1],node.evalParm('path_positions'))
        positions=np.stack([np.interp(distances,arc,p[:,i]) for i in range(3)],axis=1);positions[:,1]+=node.evalParm('eye_height')
        for pos in positions:
            for pitch in [float(x) for x in node.evalParm('elevations').split()]:
                pitch=math.radians(pitch)
                for i in range(node.evalParm('views')):
                    yaw=2*math.pi*i/node.evalParm('views');direction=np.array([math.cos(pitch)*math.sin(yaw),math.sin(pitch),math.cos(pitch)*math.cos(yaw)])
                    result.append(entry(look_at(pos,pos+direction),width,height,fov))
    if not result:raise ValueError('Aucune caméra à capturer.')
    for i,e in enumerate(result):e['file_path']='images/%05d.png'%i
    return result


def start(node,train=True,resume=False,preview=False):
    import hou
    import PyOpenColorIO as ocio
    color_config=ocio.GetCurrentConfig();display=(node.evalParm('display') if node.parm('display') else '') or color_config.getDefaultDisplay()
    key=node.sessionId()
    if key in JOBS:raise RuntimeError('Un job est déjà actif pour ce nœud.')
    if resume:
        config=Path(node.evalParm('jobfile'));data=json.loads(config.read_text(encoding='utf8'))
        if train and not data.get('exchange') and data.get('training_method')!='surface_bake':
            import spirula_train_profiles as profiles
            if not profiles.compatible(data,profiles.selected(node)) or not profiles.engine_matches(data,node):raise ValueError('Version ou projection modifiée : lancer une nouvelle génération depuis le node d’apprentissage pour conserver un checkpoint cohérent.')
        data['train']=bool(train);atomic_json(config,data)
    else:
        views=camera_plan(node)
        describe_plan(node,views)
        scan_mode=bool(node.parm('scan_lighting') and node.evalParm('scan_lighting'))
        origin=np.zeros(3);clip=[.001,100000.]
        if scan_mode:
            if node.evalParm('capture_mode')!=0 and node.evalParm('backend')>=2:raise ValueError('Pour éclairer depuis le scan, utiliser la source mesh OBJ/SOP et le renderer Karma du mode insertion.')
            from spirula_object import sop
            from spirula_transform import bounding_box
            source=sop(hou.node(node.evalParm('source')));bounds=bounding_box(source.geometry(),source.creator().worldTransform());origin=np.array(bounds.center())
            diagonal=float(np.linalg.norm(bounds.sizevec()))
            if diagonal<=1e-10:raise ValueError('La géométrie source est vide ou de taille nulle.')
            distances=[np.linalg.norm(np.array(v['transform_matrix'])[:3,3]-origin) for v in views]
            clip=[max(min(diagonal*1e-5,min(distances)*1e-3),1e-7),max(distances)+diagonal*4]
            if node.evalParm('capture_mode')==3:
                standoff=node.evalParm('target_detail')*node.evalParm('width')/(2*math.tan(math.radians(node.evalParm('fov'))/2))
                clip[0]=max(1e-7,min(clip[0],standoff*1e-3))
        if preview:
            if node.evalParm('capture_mode')==0:
                elevations=[float(x) for x in node.evalParm('elevations').split()];index=min(range(len(elevations)),key=lambda i:abs(elevations[i]))*node.evalParm('views');views=views[index:index+1]
            else:views=views[:1]
            train=False
        if train and len(views)<3:raise ValueError('Prévoir au moins trois vues pour entraîner un splat.')
        folder=Path(node.evalParm('workspace'))/('capture_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True,exist_ok=True)
        config=folder/'job.json';snapshot=folder/'scene_snapshot.hip';original=hou.hipFile.name();hip=hou.getenv('HIP')
        try:hou.hipFile.save(str(snapshot),save_to_recent_files=False)
        finally:hou.hipFile.setName(original);hou.putenv('HIP',hip)
        data={'schema':1,'started':time.time(),'folder':str(folder.resolve()),'snapshot':str(snapshot.resolve()),'original_hip':hip,'original_scene_name':original,'frame':hou.frame(),
              'views':views,'source':node.evalParm('source'),'objects':node.evalParm('objects'),'isolate':bool(node.evalParm('isolate')),
              'backend':node.evalParm('backend'),'lop_source':node.evalParm('lop_source'),'render_settings':node.evalParm('render_settings'),
              'studio_lights':bool(node.evalParm('studio_lights')),'width':node.evalParm('width'),'height':node.evalParm('height'),
              'samples':node.evalParm('samples'),'exposure':node.evalParm('exposure'),'hdr':bool(node.evalParm('hdr')),
              'iterations':node.evalParm('iterations'),'cap':node.evalParm('cap'),'executable':__import__('spirula_train_profiles').engine_path(node),
              'primitive':__import__('spirula_train_profiles').selected(node),'train':bool(train),'training_seed':node.evalParm('seed'),'device':node.evalParm('device'),
              'ocio':hou.getenv('OCIO'),'working_space':node.evalParm('working_space') or color_config.getRoleColorSpace(ocio.ROLE_SCENE_LINEAR),
              'display':display,'view':node.evalParm('view') or next((v for v in color_config.getViews(display) if v.startswith('ACES 2.0 - SDR')),color_config.getDefaultView(display))}
        data.update(preview=bool(preview),scan_lighting=scan_mode,scan_source=node.evalParm('scan_source') if scan_mode else '',training_origin=origin.tolist(),clip_range=clip,
                    output_transform=list((hou.hmath.buildTranslate(tuple(origin))*node.creator().worldTransform().inverted()).asTuple()))
        architecture=node.userData('spirula_arch_request')
        if architecture:
            request=json.loads(architecture);node.destroyUserData('spirula_arch_request');origin=np.array(request['origin']);diagonal=float(np.linalg.norm(np.array(request['box']['hi'])-request['box']['lo']));distances=[np.linalg.norm(np.array(v['transform_matrix'])[:3,3]-origin) for v in views]
            data.update(architecture={k:request[k] for k in ('stage','kind','signature')},training_origin=origin.tolist(),rebase_usd=True,clip_range=[max(diagonal*1e-6,1e-8),max(distances)+diagonal*10],output_transform=list((hou.hmath.buildTranslate(tuple(origin))*node.creator().worldTransform().inverted()).asTuple()))
        workflow=node.userData('spirula_workflow_request')
        if workflow:
            data['workflow']=json.loads(workflow);node.destroyUserData('spirula_workflow_request')
        chain=node.userData('spirula_chain_request')
        if chain:data['chain']=json.loads(chain);node.destroyUserData('spirula_chain_request')
        atomic_json(config,data);node.parm('jobfile').set(str(config))
    folder=Path(data['folder']);cancel=folder/'cancel.request'
    if cancel.exists():cancel.unlink()
    queued_message='Démarrage de l’export optimisé…' if data.get('exchange') else 'Démarrage du raffinement local…' if data.get('refinement_worker') else 'Démarrage des images de détail…' if data.get('refinement') else 'Démarrage du worker de rendu…'
    atomic_json(folder/'status.json',{'phase':'queued','message':queued_message,'started':time.time(),'updated':time.time()})
    logpath=folder/'worker.log';log=logpath.open('ab',buffering=0)
    command=[hou.expandString('$HFS/bin/hython.exe'),str(ROOT/'scripts/render_worker.py'),str(config.resolve())]
    try:process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception:log.close();raise
    JOBS[key]={'node':node,'process':process,'log':log,'folder':folder}
    if data.get('workflow'):
        import spirula_workflow
        spirula_workflow.job_started(node,config,data)
    if data.get('chain'):
        import spirula_chain
        spirula_chain.started(node,config,data)
    if data.get('architecture'):
        import spirula_arch
        spirula_arch.started(node,config,data)
    node.parm('status').set('Job en arrière-plan : %s vues · %s'%(len(data['views']),folder))
    if hou.isUIAvailable() and not getattr(poll,'installed',False):hou.ui.addEventLoopCallback(poll);poll.installed=True
    return config


def poll():
    import hou
    if time.monotonic()-getattr(poll,'last',0)<.5:return
    poll.last=time.monotonic()
    for key,job in list(JOBS.items()):
        try:
            n=job['node'];path=job['folder']/'status.json'
            try:state=json.loads(path.read_text(encoding='utf8'))
            except (OSError,ValueError):state={}
            n.parm('status').set(state.get('message','Démarrage du worker…'))
            from spirula_monitor import update_node
            state.setdefault('worker_pid',job['process'].pid);state['active']=job['process'].poll() is None
            if 'started' not in state:
                if 'started' not in job:job['started']=(job['folder']/'job.json').stat().st_mtime
                state['started']=job['started']
            shown=state
            if state.get('phase')=='done' and state['active']:shown=dict(state,phase='finishing',message='Résultat écrit ; fermeture du worker avant le retour dans Houdini…')
            update_node(n,shown)
            code=job['process'].poll()
            if code is None:continue
            if code and state.get('phase') not in ('failed','cancelled'):
                state={'phase':'failed','message':'Le worker a quitté (code %s). Voir %s'%(code,job['folder']/'worker.log')};n.parm('status').set(state['message'])
            data=json.loads((job['folder']/'job.json').read_text(encoding='utf8'))
            if state.get('result'):
                import spirula_monitor as monitor
                importing=dict(state,phase='importing',message='Chargement et vérification du splat dans Houdini…');monitor.OVERRIDES[key]=importing;update_node(n,importing);n.parm('status').set(importing['message'])
                try:
                    if n.parm('result_transform'):n.parm('result_transform').set(json.dumps(data.get('output_transform',[])))
                    n.parm('splatfile').set(state['result']);n.node('read_splat').parm('reload').pressButton();n.cook(force=True)
                    geometry=n.geometry()
                    if geometry is None or geometry.intrinsicValue('pointcount')==0:raise RuntimeError('Splat non chargé : '+'; '.join(n.errors()))
                    if not data.get('chain') and not data.get('architecture') and not data.get('refinement'):n.setDisplayFlag(True);n.setRenderFlag(True)
                    n.creator().setDisplayFlag(True)
                    if data.get('scan_lighting') and not data.get('chain'):
                        source=hou.node(data['source']);scan=hou.node(data['scan_source'])
                        if source is not None and source.creator()!=n.creator() and (scan is None or source.creator()!=scan.creator()):source.creator().setDisplayFlag(False)
                    state['message']='Terminé : %s gaussiennes chargées dans Houdini.'%geometry.intrinsicValue('pointcount')
                except Exception as exc:state.update(phase='failed',message='Entraînement conservé, import Houdini en échec : '+str(exc))
                monitor.OVERRIDES[key]=state;n.parm('status').set(state['message']);update_node(n,state)
            job['log'].close();del JOBS[key]
            if data.get('refinement') and state.get('phase')=='done':
                try:
                    import spirula_refine
                    spirula_refine.completed(n,state,data)
                except Exception as exc:
                    import spirula_monitor as monitor
                    failed=dict(state,phase='failed',message='Candidat conservé ; raccordement du raffinement en échec : '+str(exc),active=False);monitor.OVERRIDES[key]=failed;update_node(n,failed)
            if data.get('architecture') and state.get('phase')=='done':
                try:
                    import spirula_arch
                    spirula_arch.completed(n,state,data)
                except Exception as exc:
                    import spirula_monitor as monitor
                    failed=dict(state,phase='failed',message='Résultat conservé ; étape architecture en échec : '+str(exc),active=False);monitor.OVERRIDES[key]=failed;update_node(n,failed)
            if data.get('chain') and state.get('phase')=='done':
                try:
                    import spirula_chain
                    spirula_chain.completed(n,state,data)
                except Exception as exc:
                    import spirula_monitor as monitor
                    failed=dict(state,phase='failed',message='Étape conservée, suite en échec : '+str(exc),active=False);monitor.OVERRIDES[key]=failed;update_node(n,failed)
            if data.get('workflow') and state.get('phase')=='done':
                try:
                    import spirula_workflow
                    spirula_workflow.completed(n,state,data)
                except Exception as exc:
                    import spirula_monitor as monitor
                    failed=dict(state,phase='failed',message='Résultat conservé ; suite du pipeline en échec : '+str(exc),active=False)
                    monitor.OVERRIDES[key]=failed;n.parm('status').set(failed['message']);update_node(n,failed)
            # The live monitor already displays the completed preview.
        except hou.ObjectWasDeleted:
            job['log'].close();del JOBS[key]
    if not JOBS and getattr(poll,'installed',False):hou.ui.removeEventLoopCallback(poll);poll.installed=False


def stop(node):
    import spirula_monitor as monitor
    if node.sessionId() in monitor.PENDING:
        pending=monitor.PENDING.pop(node.sessionId());state={'phase':'cancelled','message':'Préparation annulée.','started':pending['started'],'finished':time.time()};monitor.OVERRIDES[node.sessionId()]=state;node.parm('status').set(state['message']);monitor.update_node(node,state);return
    config=Path(node.evalParm('jobfile'));data=json.loads(config.read_text(encoding='utf8'));(Path(data['folder'])/'cancel.request').touch();node.parm('status').set('Arrêt de la conversion demandé.' if data.get('exchange') else 'Arrêt demandé ; source et images de détail conservées.' if data.get('refinement') else 'Arrêt demandé après l’image en cours ; reprise possible.')


def callback(node,action='start'):
    import hou
    try:
        if action=='stop':return stop(node)
        if action=='cameras':return preview_cameras(node)
        if action=='folder':
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            job=node.evalParm('jobfile');path=Path(job).parent if job else Path(node.evalParm('workspace'))
            if not path.exists():raise ValueError('Aucun dossier de calcul disponible pour le moment.')
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        return start(node,train=action not in ('render','preview'),resume=action=='resume',preview=action=='preview')
    except Exception as exc:
        node.parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def preset(node,quality):
    import hou
    preview=quality=='preview';production=quality=='production';interior=node.evalParm('capture_mode')==2
    values={'width':512 if preview else 2048 if production else 1536,'height':512 if preview else 2048 if production else 1536,
            'samples':2 if preview else 24 if production else 12,'iterations':2000 if preview else 40000 if production else 30000,
            'cap':300000 if preview else 4000000}
    if node.evalParm('capture_mode')!=1:
        values.update(views=(6 if preview else 8) if interior else (12 if preview else 36),
                      elevations='-60 0 60' if interior else '-25 10 45',fov=80 if interior else 65,
                      path_positions=6 if preview else 24 if production else 12)
    with hou.undos.group('Spirula : qualité '+quality):
        for name,value in values.items():node.parm(name).set(value)
    node.parm('status').set('Préréglage appliqué. Tester une image puis vérifier le parcours et l’éclairage avant le calcul complet.')
    try:describe_plan(node,camera_plan(node))
    except ValueError:pass


def describe_plan(node,views):
    text='%s vues · %s × %s · %s itérations · plafond %s gaussiennes. Couverture à contrôler ; le nombre de vues seul ne garantit pas la qualité.'%(len(views),node.evalParm('width'),node.evalParm('height'),node.evalParm('iterations'),node.evalParm('cap'))
    if node.parm('capture_summary'):node.parm('capture_summary').set(text)
    return text


def preview_cameras(node):
    """Persistent world-space wire frusta, excluded from rendering."""
    import hou
    views=camera_plan(node);describe_plan(node,views)
    name='SPIRULA_CAMERAS_'+str(node.sessionId());obj=hou.node('/obj/'+name) or hou.node('/obj').createNode('geo',name)
    guide=obj.node('COVERAGE') or obj.createNode('python','COVERAGE')
    guide.parm('python').set('''import hou, json, numpy as np
geo=hou.pwd().geometry();geo.addAttrib(hou.attribType.Point,'Cd',(0.1,0.75,1.0));geo.addAttrib(hou.attribType.Global,'gl_wireframe',1)
views=json.loads(%r)
for view in views:
 m=np.array(view['transform_matrix']);d=.18
 x=d*view['w']/(2*view['fl_x']);y=d*view['h']/(2*view['fl_y'])
 p=np.array([[0,0,0],[-x,-y,-d],[x,-y,-d],[x,y,-d],[-x,y,-d]])@m[:3,:3].T+m[:3,3]
 points=geo.createPoints(p.tolist())
 for a,b in [(0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1)]:
  line=geo.createPolygon(is_closed=False);line.addVertex(points[a]);line.addVertex(points[b])
'''%json.dumps(views))
    guide.setDisplayFlag(True);obj.setDisplayFlag(True)
    empty=obj.node('NO_RENDER') or obj.createNode('null','NO_RENDER');empty.setRenderFlag(True)
    if obj.parm('vm_rendervisibility'):obj.parm('vm_rendervisibility').set('')
    if obj.parm('vm_renderable'):obj.parm('vm_renderable').set(0)
    obj.setUserData('spirula_capture_controller',node.path());guide.cook(force=True)
    node.parm('status').set('Repères caméra créés dans /obj. Vérifier les angles morts, le sol, le plafond et les passages derrière les objets.')
    return obj


def create(source=None):
    import hou
    from spirula_object import sop
    source=source or (hou.selectedNodes()[0] if hou.selectedNodes() else None)
    if isinstance(source,hou.LopNode):
        obj=hou.node('/obj').createNode('geo','ARCHITECTURAL_SPLAT_CAPTURE');n=obj.createNode('spirula::render_splat::1.0','RENDER_TO_SPLAT');n.parm('backend').set(2);n.parm('lop_source').set(source.path());n.parm('capture_mode').set(1);n.setCurrent(True,clear_all_selected=True);return n
    source=sop(source)
    if source.type().name()=='spirula::object_splat::1.0' and source.inputs():source=source.inputs()[0]
    if source.type().name()=='spirula::render_splat::1.0' and source.evalParm('source'):
        original=hou.node(source.evalParm('source'))
        if original is not None:source=sop(original)
    n=source.parent().createNode('spirula::render_splat::1.0','RENDER_TO_SPLAT');n.parm('source').set(source.path());n.parm('seed').set(source.path());n.setPosition(source.position()+hou.Vector2(2,-2));n.setCurrent(True,clear_all_selected=True);return n


def exr_to_png(source,target,exposure=0,color=None,allow_incomplete=False):
    import OpenImageIO as oiio
    from PIL import Image
    image=oiio.ImageInput.open(str(source))
    if image is None:raise RuntimeError('EXR illisible : '+str(source))
    spec=image.spec();channels=list(spec.channelnames);names=[n.lower() for n in channels]
    prefix=next((p for p in ['', 'c.', 'ci.', 'beauty.', 'combined.'] if all(p+c in names for c in ['r','g','b'])),None)
    if prefix is None:raise RuntimeError('Le fichier EXR ne contient pas de passe beauty RGB identifiable : '+str(channels))
    indices=[names.index(prefix+c) for c in ['r','g','b']];alpha_index=names.index(prefix+'a') if prefix+'a' in names else None
    begin=min(indices+[alpha_index] if alpha_index is not None else indices);end=max(indices+[alpha_index] if alpha_index is not None else indices)+1
    pixels=np.asarray(image.read_image(begin,end,oiio.FLOAT));image.close()
    rgb=pixels[:,:,[i-begin for i in indices]]
    alpha=np.clip(pixels[:,:,alpha_index-begin],0,1) if alpha_index is not None else np.ones(rgb.shape[:2])
    if allow_incomplete:
        invalid=~np.isfinite(rgb).all(axis=2)|~np.isfinite(alpha);rgb=np.nan_to_num(rgb,nan=0.,posinf=0.,neginf=0.);alpha=np.where(invalid,0,alpha)
    elif not np.isfinite(rgb).all() or not np.isfinite(alpha).all():raise RuntimeError('NaN/Inf dans la passe beauty '+str(source))
    rgb=np.where(alpha[:,:,None]>1e-6,rgb/np.maximum(alpha[:,:,None],1e-6),0)*2**exposure
    if color:
        import PyOpenColorIO as ocio
        cfg=ocio.Config.CreateFromFile(color['ocio']) if color.get('ocio') else ocio.GetCurrentConfig()
        transform=ocio.DisplayViewTransform(src=color['working_space'],display=color['display'],view=color['view'])
        rgb=np.ascontiguousarray(rgb,dtype=np.float32);cfg.getProcessor(transform).getDefaultCPUProcessor().applyRGB(rgb)
    else:
        rgb=np.where(rgb<=.0031308,rgb*12.92,1.055*np.maximum(rgb,0)**(1/2.4)-.055)
    rgba=np.dstack([np.clip(rgb,0,1),alpha]);Image.fromarray(np.uint8(np.round(rgba*255)),'RGBA').save(target)


def _set(node,name,value):
    parm=node.parm(name)
    if parm is not None:parm.set(value,follow_parm_reference=False)


def run_worker(config_file):
    """One writer per capture; Windows releases this lock even after a crash."""
    import msvcrt
    config_file=Path(config_file)
    with (config_file.parent/'.worker.lock').open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('Ce job est déjà utilisé par un worker. Attendre sa fin avant de le reprendre.')
        try:return _run_worker(config_file)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


def _run_worker(config_file):
    import hou
    from PIL import Image
    data=json.loads(Path(config_file).read_text(encoding='utf8'));folder=Path(data['folder']);statuspath=folder/'status.json'
    worker_started=time.time()
    def status(phase,message,**extra):
        state=dict(phase=phase,message=message,started=worker_started,worker_pid=os.getpid(),updated=time.time(),**extra)
        if phase in ('done','failed','cancelled'):state['finished']=time.time()
        atomic_json(statuspath,state)
    try:
        if data.get('exchange'):
            from spirula_exchange import worker
            return worker(data,status)
        status('loading','Chargement du snapshot de la scène…');hou.hipFile.load(data['snapshot'],suppress_save_prompt=True,ignore_load_warnings=True)
        if data.get('original_scene_name'):hou.hipFile.setName(data['original_scene_name'])
        hou.putenv('HIP',data['original_hip']);hou.setFrame(data['frame'])
        if data.get('refinement_worker'):
            from spirula_refine import worker
            return worker(data,folder,status)
        images=folder/'images';renders=folder/'renders';images.mkdir(exist_ok=True);renders.mkdir(exist_ok=True)
        backend=data['backend'];source=hou.node(data['source']) if data['source'] else None;objects=data['objects'];render_lop=None
        scan_base=None
        if data.get('require_cached_renders'):pass
        elif data.get('scan_lighting'):
            from spirula_insert import prepare_stage
            status('lighting','Préparation du champ lumineux du scan et des matériaux de l’objet…');scan_base=prepare_stage(data,folder)
        elif backend<2:
            camera=hou.node('/obj').createNode('cam','SPIRULA_CAPTURE_CAMERA');camera.parm('resx').set(data['width']);camera.parm('resy').set(data['height']);camera.parm('aspect').set(1)
            camera.parm('near').set(data.get('clip_range',[.001,100000])[0]);camera.parm('far').set(data.get('clip_range',[.001,100000])[1])
            if data['isolate']:
                if source is None:raise ValueError('Choisir un mesh/SOP à isoler.')
                from spirula_object import sop
                source=sop(source)
                if source.geometry().findPointAttrib('GS_Alpha') and backend==0:raise ValueError('Mantra ne rend pas les splats natifs. Choisir un mesh source ou un stage Solaris/Karma XPU.')
                proxy=hou.node('/obj').createNode('geo','SPIRULA_CAPTURE_PROXY');proxy.setWorldTransform(source.creator().worldTransform())
                if source.creator().parm('shop_materialpath'):proxy.parm('shop_materialpath').set(source.creator().evalParm('shop_materialpath'))
                merge=proxy.createNode('object_merge');merge.parm('objpath1').set(source.path());merge.parm('xformtype').set(0);objects=proxy.path()
            if data['studio_lights']:
                positions=np.array([v['transform_matrix'] for v in data['views']])[:,:3,3];center=positions.mean(axis=0);radius=max(.5,float(np.linalg.norm(positions-center,axis=1).mean()))
                for i,offset in enumerate([[1,1.4,1],[-1,.6,.4],[0,1,-1]]):
                    light=hou.node('/obj').createNode('hlight::2.0','SPIRULA_STUDIO_LIGHT');light.parm('light_type').set('grid');light.parmTuple('areasize').set((radius*.6,radius*.6));light.parm('light_intensity').set([2.,.8,1.5][i]);light.parm('light_exposure').set(2)
                    pose=look_at(center+np.array(offset)*radius,center);light.setWorldTransform(hou.Matrix4(tuple(pose.T.ravel())))
            rop=hou.node(data['render_settings']) if data['render_settings'] else hou.node('/out').createNode('ifd' if backend==0 else 'karma','SPIRULA_CAPTURE_RENDER')
            if rop is None:raise ValueError('ROP de rendu introuvable : '+data['render_settings'])
            _set(rop,'camera',camera.path());_set(rop,'soho_foreground',1);_set(rop,'soho_autoheadlight',0);_set(rop,'allowmotionblur',0);_set(rop,'enabledof',0);_set(rop,'vm_dof',0);_set(rop,'enablemblur',0)
            _set(rop,'override_camerares',1);_set(rop,'res_fraction','specific')
            for name,value in [('resolutionx',data['width']),('resolutiony',data['height']),('res_overridex',data['width']),('res_overridey',data['height'])]:_set(rop,name,value)
            if backend==0:
                _set(rop,'vm_renderengine','pbrraytrace');_set(rop,'vobject',objects);_set(rop,'vm_samplesx',data['samples']);_set(rop,'vm_samplesy',data['samples']);_set(rop,'vm_diffuselimit',3);_set(rop,'vm_reflectlimit',4);_set(rop,'vm_refractlimit',4)
            else:
                _set(rop,'engine','cpu');_set(rop,'candobjects',objects);_set(rop,'samplesfromstage',0);_set(rop,'samplesperpixel',data['samples']**2);_set(rop,'pathtracedsamples',data['samples']**2);_set(rop,'enablemplaymonitor',0)
        else:
            source_lop=hou.node(data['lop_source'])
            if source_lop is None:raise ValueError('Choisir le LOP final contenant la scène, les matériaux et les lumières.')
            if data['render_settings']:
                render_lop=source_lop
            else:
                render_lop=hou.node('/stage').createNode('karmarendersettings','SPIRULA_CAPTURE_SETTINGS');render_lop.setInput(0,source_lop)
                for name,value in [('res_mode','manual'),('resolutionx',data['width']),('resolutiony',data['height']),('camera','/SpirulaCapture/camera'),('engine','xpu' if backend==3 else 'cpu'),('samplesperpixel',data['samples']**2),('pathtracedsamples',data['samples']**2)]:
                    _set(render_lop,name,value)
                    if name=='res_mode':render_lop.parm(name).pressButton()
        frames=[];maximum_signal=0
        for i,view in enumerate(data['views']):
            if (folder/'cancel.request').exists():status('cancelled','Arrêté après %s images ; reprise disponible.'%len(frames));return
            exr=renders/('%05d.exr'%i);png=images/('%05d.png'%i)
            valid=False
            if png.exists():
                try:
                    with Image.open(png) as im:
                        valid=im.size==(data['width'],data['height']);im.verify()
                    valid=valid and exr.exists() and exr.stat().st_size>100
                except (OSError,ValueError):pass
            if not valid:
                if data.get('require_cached_renders'):raise RuntimeError('Dataset incomplet ou corrompu : revenir au nœud 07. Le nœud 08 ne recalcule pas les rendus.')
                status('rendering','Rendu photoréaliste %s / %s'%(i+1,len(data['views'])),rendered=i,total=len(data['views']))
                if scan_base:
                    from spirula_insert import render_view
                    render_view(data,scan_base,view,exr)
                elif backend<2:
                    camera.setWorldTransform(hou.Matrix4(tuple(np.array(view['transform_matrix']).T.ravel())));camera.parm('aperture').set(36);camera.parm('focal').set(36*view['fl_x']/data['width'])
                    _set(rop,'vm_picture' if backend==0 else 'picture',str(exr));rop.render()
                else:
                    from pxr import Usd,UsdGeom,Gf
                    source_stage=render_lop.stage()
                    if source_stage is None:raise RuntimeError('Le stage Solaris ne peut pas cuire : '+'; '.join(render_lop.errors()))
                    stage=Usd.Stage.Open(source_stage.Flatten())
                    matrix=np.array(view['transform_matrix'])
                    if data.get('rebase_usd'):
                        from spirula_arch import rebase_stage
                        rebase_stage(stage,data['training_origin'],data['frame']);matrix[:3,3]-=np.array(data['training_origin'])
                    cam=UsdGeom.Camera.Define(stage,'/SpirulaCapture/camera');cam.GetHorizontalApertureAttr().Set(36.);cam.GetVerticalApertureAttr().Set(36.*data['height']/data['width']);cam.GetFocalLengthAttr().Set(36.*view['fl_x']/data['width']);cam.GetClippingRangeAttr().Set(Gf.Vec2f(*data.get('clip_range',[.001,100000])));cam.MakeMatrixXform().Set(Gf.Matrix4d(*matrix.T.ravel().tolist()))
                    usd=folder/'capture.usdc';stage.GetRootLayer().Export(str(usd))
                    command=[hou.expandString('$HFS/bin/husk.exe'),str(usd),'--camera','/SpirulaCapture/camera','--res',str(data['width']),str(data['height']),'-o',str(exr),'--frame',str(data['frame']),'--disable-motionblur']
                    if data.get('architecture') or data.get('refinement'):command+=['--headlight','none','-n','1']
                    if data['render_settings']:command+=['--settings',data['render_settings'],'-R','BRAY_HdKarmaXPU' if backend==3 else 'BRAY_HdKarma']
                    subprocess.run(command,check=True)
                if not exr.is_file():raise RuntimeError('Le renderer n’a pas écrit '+str(exr))
                exr_to_png(exr,png,data['exposure'],data if data.get('working_space') else None)
                with Image.open(png) as im:
                    if im.size!=(view['w'],view['h']):raise RuntimeError('La résolution rendue ne correspond pas aux intrinsèques caméra : %s / %s'%(im.size,(view['w'],view['h'])))
            frame=dict(view)
            if data.get('training_origin'):
                matrix=np.array(view['transform_matrix']);matrix[:3,3]-=np.array(data['training_origin']);frame['transform_matrix']=matrix.tolist()
            with Image.open(png) as im:
                maximum_signal=max(maximum_signal,int(np.asarray(im.convert('RGB')).max()))
            if data['hdr']:frame['file_path']='renders/%05d.exr'%i
            frames.append(frame)
            atomic_json(folder/'transforms.json',{'camera_model':'OPENCV','frames':frames,'w':data['width'],'h':data['height'],'fl_x':view['fl_x'],'fl_y':view['fl_y'],'cx':view['cx'],'cy':view['cy']})
        if maximum_signal==0:raise RuntimeError('Toutes les images sont noires. Vérifier lumières, visibilité, cadrage et exposition avant l’apprentissage.')
        if not data['train']:status('done','Dataset prêt : %s images et caméras exactes.'%len(frames));return
        if (folder/'cancel.request').exists():status('cancelled','Rendus conservés ; entraînement non démarré.');return
        if data.get('training_method')=='surface_bake':
            from spirula_surface_bake import run_worker
            try:result=run_worker(data,folder,status)
            except InterruptedError:status('cancelled','Cuisson arrêtée ; rendus conservés.');return
            status('done','Radiance transférée sur les surfaces ; splat prêt.',result=str(result),rendered=len(frames),total=len(frames));return
        status('training','Entraînement Spirula sur %s rendus…'%len(frames),rendered=len(frames),total=len(frames))
        run=folder/'training'/'run';command=[data['executable'],'train','synthetic','--data',str(folder),'--data-format','nerfstudio','--output-dir-prefix',str(run.parent),'--output-dir-name',run.name,'--num-iterations',str(data['iterations']),'--cap-max',str(data['cap']),'--sh-degree','3','--disable-viewer','1','--keep-viewer-alive','0','--save-full-checkpoint','1','--orientation-method','none','--center-method','none','--auto-scale-poses','0','--scene-center','none','--device',data['device']]
        command+=__import__('spirula_train_profiles').arguments(data)
        completed=[p for p in run.glob('step-*.ckpt/splat.ply') if int(p.parent.name.split('-')[-1].split('.')[0])>=data['iterations']]
        if completed:
            result=max(completed,key=lambda p:p.stat().st_mtime_ns);status('done','Job déjà terminé ; rendus et splat conservés.',result=str(result),rendered=len(frames),total=len(frames));return
        if list(run.glob('step-*.ckpt/state.tar')):command+=['--resume',str(run)]
        if data['hdr']:
            space=data.get('working_space','').lower();gamut='ACEScg' if 'acescg' in space else 'Rec.709'
            if 'aces' in space and 'acescg' not in space:raise ValueError('Pour HDR, utiliser ACEScg ou Linear Rec.709 comme espace de rendu.')
            # Normalize output primaries for Houdini and the shared scene exporter.
            command+=['--image-color-is-linear','1','--splat-color-is-linear','1','--image-color-gamut',gamut,'--splat-color-gamut','Rec.709']
        if data['training_seed'] and hou.node(data['training_seed']):
            from spirula_object import sop
            seed=sop(hou.node(data['training_seed']));seed_geometry=seed.geometry()
            if seed_geometry.intrinsicValue('primitivecount'):
                scatter=hou.sopNodeTypeCategory().nodeVerb('scatter::2.0');scatter.setParms({'forcetotal':1,'npts':100000,'relaxpoints':0,'seed':42.})
                points=hou.Geometry();scatter.execute(points,[seed_geometry]);seed_geometry=points
            p=np.frombuffer(seed_geometry.pointFloatAttribValuesAsString('P'),dtype=np.float32).reshape(-1,3).astype(np.float64);m=np.array(seed.creator().worldTransform().asTuple()).reshape(4,4);p=p@m[:3,:3]+m[3,:3]
            p-=np.array(data.get('training_origin',[0.,0.,0.]))
            if len(p)>100000:p=p[np.random.default_rng(42).choice(len(p),100000,replace=False)]
            seedfile=folder/'seed.ply'
            rows=np.zeros(len(p),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
            for i,c in enumerate('xyz'):rows[c]=p[:,i]
            for c in ('red','green','blue'):rows[c]=128
            seedfile.write_bytes(('ply\nformat binary_little_endian 1.0\nelement vertex %s\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n'%len(p)).encode()+rows.tobytes());command+=['--seed-pointcloud',str(seedfile)]
        env=os.environ.copy();env['SS_NO_AUTO_FETCH']='1';log=(folder/'training.log').open('ab',buffering=0)
        try:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while process.poll() is None:
                if (folder/'cancel.request').exists():process.terminate();process.wait();status('cancelled','Entraînement arrêté ; dernier checkpoint conservé.');return
                with (folder/'training.log').open('rb') as reader:
                    reader.seek(max(0,(folder/'training.log').stat().st_size-8192));tail=reader.read().decode('utf8',errors='replace')
                steps=re.findall(r'(?:step|étape)\s+(\d+)\s*/\s*(\d+)',tail,re.IGNORECASE)
                if steps:status('training','Entraînement Spirula : %s / %s'%steps[-1],step=int(steps[-1][0]),steps=int(steps[-1][1]),rendered=len(frames),total=len(frames))
                time.sleep(1)
            if process.returncode:raise RuntimeError('Spirula a échoué (code %s). Voir training.log.'%process.returncode)
        finally:log.close()
        outputs=list(run.glob('step-*.ckpt/splat.ply'))
        if not outputs:raise RuntimeError('Entraînement terminé sans splat.ply.')
        result=max(outputs,key=lambda p:p.stat().st_mtime_ns);status('done','Splat appris depuis les rendus, prêt à importer.',result=str(result),rendered=len(frames),total=len(frames))
    except Exception as exc:
        import traceback
        status('failed',str(exc),traceback=traceback.format_exc());raise
