"""Explicit SOP pipeline for a complete lit Solaris scene, independent of the demo."""
import fnmatch
import hashlib
import json
import math
from pathlib import Path
import uuid
import numpy as np

PIPELINE_REVISION = "7.3.0"


def nodes(node):
    root=node if node.userData('spirula_arch') else node.creator()
    return {n.userData('spirula_arch_role'):n for n in root.children() if n.userData('spirula_arch_role')}



def unique_usd_geometry(node):
    """Keep one packed prim per USD path and world placement."""
    out=node.geometry();out.clear();out.merge(node.inputs()[0].geometry())
    if not out.findPrimAttrib('path'):return
    seen=set();duplicates=[]
    for prim in out.prims():
        names=prim.intrinsicNames()
        if 'packedfulltransform' not in names:continue
        transform=tuple(prim.intrinsicValue('packedfulltransform'));key=(prim.stringAttribValue('path'),transform)
        if key in seen:duplicates.append(prim)
        else:seen.add(key)
    if duplicates:out.deletePrims(duplicates,keep_points=False)

def state(node):return json.loads(node.userData('spirula_arch_state') or '{}')


def remember(node,**values):
    data=state(node);data.update(values);node.setUserData('spirula_arch_state',json.dumps(data));return data


def status(node,message):
    if node.parm('status'):node.parm('status').set(message)
    node.setComment(message)
    import hou
    node.setGenericFlag(hou.nodeFlag.DisplayComment,True)


def scene(node):
    import hou
    source=nodes(node)['source'];lop=hou.node(source.evalParm('lop_source'))
    if lop is None or lop.type().category()!=hou.lopNodeTypeCategory():raise ValueError('01 : choisir le LOP final contenant géométrie, matériaux et lumières.')
    stage=lop.stage()
    if stage is None:raise ValueError('La scène Solaris ne peut pas cuire : '+'; '.join(lop.errors()))
    return lop,stage


def bounds(node):
    import hou
    from pxr import Usd,UsdGeom
    lop,stage=scene(node);patterns=nodes(node)['source'].evalParm('targets').split()
    if not patterns:raise ValueError('01 : indiquer au moins un chemin USD du bâtiment à cadrer, sans le ciel ni un sol immense.')
    prims=[]
    for pattern in patterns:
        if any(c in pattern for c in '*?['):prims.extend(p for p in stage.Traverse() if fnmatch.fnmatchcase(str(p.GetPath()),pattern))
        else:
            prim=stage.GetPrimAtPath(pattern)
            if not prim:raise ValueError('Cible USD introuvable : '+pattern)
            prims.append(prim)
    if not prims:raise ValueError('Aucune primitive USD ne correspond à la cible.')
    cache=UsdGeom.BBoxCache(Usd.TimeCode(hou.frame()),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render],useExtentsHint=True);ranges=[]
    for prim in prims:
        box=cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if not box.IsEmpty():ranges.append((np.array(box.GetMin()),np.array(box.GetMax())))
    if not ranges:raise ValueError('Cible vide ou sans limites géométriques exploitables.')
    lo=np.min([r[0] for r in ranges],axis=0);hi=np.max([r[1] for r in ranges],axis=0)
    if not np.isfinite([lo,hi]).all() or np.linalg.norm(hi-lo)<=1e-9:raise ValueError('Limites de cible non finies ou de taille nulle.')
    return dict(lo=lo.tolist(),hi=hi.tolist(),up=str(UsdGeom.GetStageUpAxis(stage)),meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage),prims=sorted(set(str(p.GetPath()) for p in prims)))


def pose(position,target,up_axis=1):
    back=np.asarray(position,float)-np.asarray(target,float);back/=np.linalg.norm(back);up=np.eye(3)[up_axis]
    if abs(up@back)>.995:up=np.eye(3)[0 if up_axis!=0 else 2]
    right=np.cross(up,back);right/=np.linalg.norm(right);up=np.cross(back,right);m=np.eye(4);m[:3,:3]=np.stack([right,up,back],axis=1);m[:3,3]=position;return m


def plan_box(box,width,height,fov,views,elevations,margin=1.15,mode=0,detail=.01,max_views=2000,minimum_height=1.6):
    """Plan in source world units. Enclose all bounding-box corners in orbit mode."""
    from spirula_render import entry
    lo=np.array(box['lo'],float);hi=np.array(box['hi'],float);center=(lo+hi)*.5;size=hi-lo;up=1 if box['up']=='Y' else 2;horizontal=[i for i in range(3) if i!=up]
    if width<32 or height<32 or not 10<=fov<150 or not 1<=margin<=3:raise ValueError('Résolution, champ ou marge de cadrage invalide.')
    if not np.isfinite([lo,hi]).all() or np.any(size<0) or np.linalg.norm(size)<=1e-9:raise ValueError('Limites de cible invalides.')
    result=[];half=math.radians(fov)*.5
    if mode==0:
        if views<3 or not elevations or not np.isfinite(elevations).all() or any(abs(a)>=89 for a in elevations):raise ValueError('Prévoir au moins 3 directions et des angles verticaux entre -89 et 89 degrés.')
        if views*len(elevations)>max_views:raise ValueError('La capture dépasse la limite de vues. Réduire directions ou niveaux.')
        vertical=math.atan(math.tan(half)*height/width);distance=np.linalg.norm(size)*.5/max(math.sin(min(half,vertical)),1e-8)*margin
        for elevation in elevations:
            a=math.radians(elevation);y=max(center[up]+distance*math.sin(a),lo[up]+minimum_height)
            vertical_delta=y-center[up];radius=max(distance*abs(math.cos(a)),math.sqrt(max(0,distance**2-vertical_delta**2)))
            for i in range(views):
                az=2*math.pi*i/views-math.radians(20);p=center.copy();p[up]=y;p[horizontal[0]]+=radius*math.sin(az);p[horizontal[1]]-=radius*math.cos(az)
                result.append(entry(pose(p,center,up),width,height,fov))
    else:
        if detail<=0:raise ValueError('La précision façade doit être positive.')
        spans=np.array([width*detail,height*detail]);distance=spans[0]/(2*math.tan(half));layouts=[];count=0
        for axis,sign in [(horizontal[0],-1),(horizontal[0],1),(horizontal[1],-1),(horizontal[1],1),(up,1)]:
            other=[i for i in range(3) if i!=axis]
            if up in other:other=[i for i in other if i!=up]+[up]
            dims=np.maximum(1,np.ceil(size[other]/(spans*.7)).astype(int));count+=int(np.prod(dims));layouts.append((axis,sign,other,dims))
        if count>max_views:raise ValueError('%s vues de façade prévues, limite %s. Augmenter les unités/pixel ou découper la cible.'%(count,max_views))
        for axis,sign,other,dims in layouts:
            for i in range(dims[0]):
                for j in range(dims[1]):
                    target=center.copy();target[axis]=lo[axis] if sign<0 else hi[axis];target[other]=lo[other]+size[other]*(np.array([i,j])+.5)/dims;p=target.copy();p[axis]+=sign*distance
                    result.append(entry(pose(p,target,up),width,height,fov))
    for i,view in enumerate(result):view['file_path']='images/%05d.png'%i
    return result


def camera_plan(node):
    ns=nodes(node);cam=ns['cameras'];render=ns['renders'];box=bounds(node)
    views=plan_box(box,render.evalParm('width'),render.evalParm('height'),cam.evalParm('fov'),cam.evalParm('views'),[float(v) for v in cam.evalParm('elevations').split()],margin=cam.evalParm('margin'),mode=cam.evalParm('mode'),detail=cam.evalParm('detail')/box['meters_per_unit'],max_views=cam.evalParm('max_views'),minimum_height=cam.evalParm('min_height')/box['meters_per_unit'])
    if cam.evalParm('extra_cameras').strip():
        import hou
        from pxr import UsdGeom,Usd
        _,stage=scene(node)
        for path in cam.evalParm('extra_cameras').split():
            obj=hou.node(path)
            if obj is not None and obj.parm('focal'):
                if obj.parm('projection').evalAsString()!='perspective':raise ValueError('Caméra en perspective requise : '+path)
                if any(obj.parm(n) and abs(obj.evalParm(n))>1e-8 for n in ('winx','winy')):raise ValueError('Caméra décentrée non prise en charge : '+path)
                matrix=np.array(obj.worldTransform().asTuple()).reshape(4,4).T;fov=math.degrees(2*math.atan(obj.evalParm('aperture')/(2*obj.evalParm('focal'))))
            else:
                camera=UsdGeom.Camera(stage.GetPrimAtPath(path))
                if not camera or camera.GetProjectionAttr().Get()!='perspective':raise ValueError('Caméra OBJ ou USD perspective introuvable : '+path)
                if any(abs(a.Get() or 0)>1e-8 for a in (camera.GetHorizontalApertureOffsetAttr(),camera.GetVerticalApertureOffsetAttr())):raise ValueError('Caméra décentrée non prise en charge : '+path)
                matrix=np.array(UsdGeom.XformCache(Usd.TimeCode(hou.frame())).GetLocalToWorldTransform(camera.GetPrim())).T;fov=math.degrees(2*math.atan(camera.GetHorizontalApertureAttr().Get()/(2*camera.GetFocalLengthAttr().Get())))
            from spirula_render import entry
            view=entry(matrix,render.evalParm('width'),render.evalParm('height'),fov);view['file_path']='images/%05d.png'%len(views);views.append(view)
    if len(views)>cam.evalParm('max_views'):raise ValueError('Les caméras supplémentaires dépassent la limite de vues.')
    return views


def signature(node):
    import hou
    from pxr import Sdf,Usd
    from spirula_quality import file_signature
    ns=nodes(node);_,stage=scene(node);layer=stage.Flatten();snapshot=Usd.Stage.Open(layer);snapshot.RemovePrim('/HoudiniLayerInfo');layer.documentation='';digest=hashlib.sha256(layer.ExportToString().encode())
    for prim in stage.Traverse():
        for attr in prim.GetAttributes():
            if attr.GetTypeName()==Sdf.ValueTypeNames.Asset:
                asset=attr.Get(hou.frame())
                if asset and asset.path:digest.update(file_signature(asset.resolvedPath or asset.path).encode())
    digest.update(json.dumps(camera_plan(node),sort_keys=True).encode());digest.update(str([ns['renders'].evalParm(p) for p in ('width','height','samples','exposure','hdr')]).encode());digest.update(str(hou.frame()).encode())
    if ns['source'].parm('settings_path'):digest.update(ns['source'].evalParm('settings_path').encode())
    return digest.hexdigest()


def geometry(node,role):
    import hou
    stage=node.parent();ns=nodes(stage);out=node.geometry();out.clear()
    if role in ('cameras','preview','renders'):
        if stage.inputs() and stage.inputs()[0]:out.merge(stage.inputs()[0].geometry())
        if role=='cameras' and stage.evalParm('guides'):
            guide=hou.Geometry();guide.addAttrib(hou.attribType.Point,'Cd',(.1,.7,1.));scale=np.linalg.norm(np.array(bounds(stage)['hi'])-bounds(stage)['lo'])*.025
            for view in camera_plan(stage):
                m=np.array(view['transform_matrix']);x=scale*view['w']/(2*view['fl_x']);y=scale*view['h']/(2*view['fl_y']);p=np.array([[0,0,0],[-x,-y,-scale],[x,-y,-scale],[x,y,-scale],[-x,y,-scale]])@m[:3,:3].T+m[:3,3];points=guide.createPoints(p.tolist())
                for a,b in ((0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1)):
                    poly=guide.createPolygon(is_closed=False);poly.addVertex(points[a]);poly.addVertex(points[b])
            out.merge(guide)
    elif role=='train':
        saved=state(stage)
        if not saved.get('model'):return
        if saved.get('signature')!=signature(stage):raise hou.NodeError('Scène ou caméras modifiées : recalculer les rendus puis le splat.')
        out.merge(stage.node('CAPTURE').geometry())


def configure(node,kind):
    ns=nodes(node);source=ns['source'];cap=ns['train' if kind=='train' else 'renders'].node('CAPTURE');r=ns['renders'];cam=ns['cameras']
    settings=dict(source=source.node('SEED_NATIVE').path(),seed=source.node('SEED_NATIVE').path(),scan_lighting=0,backend=3,lop_source=source.evalParm('lop_source'),studio_lights=0,isolate=0,width=r.evalParm('width'),height=r.evalParm('height'),samples=r.evalParm('samples'),exposure=r.evalParm('exposure'),hdr=r.evalParm('hdr'),views=cam.evalParm('views'),elevations=cam.evalParm('elevations'),fov=cam.evalParm('fov'),iterations=ns['train'].evalParm('iterations'),cap=ns['train'].evalParm('cap'),working_space='Linear Rec.709 (sRGB)')
    settings['render_settings']=source.evalParm('settings_path') if source.parm('settings_path') else ''
    if settings['render_settings']:
        from pxr import UsdRender
        if not UsdRender.Settings(scene(node)[1].GetPrimAtPath(settings['render_settings'])):raise ValueError('Render Settings USD introuvables : '+settings['render_settings'])
    for key,value in settings.items():cap.parm(key).set(value)
    # Use the current OCIO role rather than assuming a colour-space display name.
    cap.parm('working_space').set('');cap.setUserData('spirula_arch_active_stage',node.path());__import__('spirula_train_profiles').apply_to_capture(ns['train'],cap);return cap


def request(node,kind):
    import hou,spirula_render as render
    ns=nodes(node);sig=signature(node);source=ns['source'];cap=configure(node,kind)
    if not np.allclose(np.array(node.creator().worldTransform().asTuple()).reshape(4,4),np.eye(4)):raise ValueError('Garder le Geo de pilotage à sa transformation identité ; placer le bâtiment dans la scène Solaris.')
    if kind=='train':
        primitive=__import__('spirula_train_profiles').selected(ns['train'])
        dataset=state(ns['renders'])
        if dataset.get('signature')!=sig:raise ValueError('04 : rendre le dataset actuel avant l’apprentissage.')
        method='surface_bake' if ns['train'].parm('method') and ns['train'].evalParm('method')==1 else 'spirula'
        if method=='surface_bake' and ns['renders'].evalParm('hdr'):raise ValueError('Le mode surface exporte actuellement un PLY sRGB : désactiver le HDR avancé.')
        old=state(ns['train']);job=Path(dataset['job']);data=json.loads(job.read_text(encoding='utf8'))
        if old.get('pipeline_revision')==PIPELINE_REVISION and old.get('training_method','spirula')==method and old.get('source_render_job')==str(job) and old.get('signature')==sig and old.get('job') and Path(old['job']).is_file() and json.loads(Path(old['job']).read_text(encoding='utf8'))['cap']==ns['train'].evalParm('cap') and __import__('spirula_train_profiles').compatible(json.loads(Path(old['job']).read_text(encoding='utf8')),primitive) and __import__('spirula_train_profiles').engine_matches(json.loads(Path(old['job']).read_text(encoding='utf8')),ns['train']):
            path=Path(old['job']);data=json.loads(path.read_text(encoding='utf8'))
        else:
            import os,shutil
            folder=Path(source.evalParm('workspace'))/'03_apprentissage'/('train_'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
            for directory,extension in [('images','png'),('renders','exr')]:
                (folder/directory).mkdir()
                for i in range(len(data['views'])):
                    original=job.parent/directory/('%05d.%s'%(i,extension));target=folder/directory/original.name
                    if not original.is_file():raise ValueError('Dataset incomplet : revenir en 04.')
                    try:os.link(original,target)
                    except OSError:shutil.copy2(original,target)
            data.update(folder=str(folder),require_cached_renders=True,source_render_job=str(job));path=folder/'job.json'
        data.update(executable=__import__('spirula_train_profiles').engine_path(ns['train']),primitive=primitive,pipeline_revision=PIPELINE_REVISION,training_method=method,iterations=ns['train'].evalParm('iterations'),cap=ns['train'].evalParm('cap'),train=True,architecture=dict(stage=node.path(),kind=kind,signature=sig));render.atomic_json(path,data);cap.parm('jobfile').set(str(path));remember(ns['train'],pipeline_revision=PIPELINE_REVISION,training_method=method,model=None,source_render_job=str(job),job=str(path),signature=sig);return render.start(cap,train=True,resume=True)
    if kind=='renders' and state(ns['preview']).get('approved')!=sig:raise ValueError('03 : calculer puis valider l’aperçu de la scène actuelle.')
    box=bounds(node);origin=((np.array(box['lo'])+box['hi'])*.5).tolist();views=camera_plan(node)
    if kind=='preview':views=views[:1]
    cap.parm('workspace').set(str(Path(source.evalParm('workspace'))/('01_apercus' if kind=='preview' else '02_rendus')))
    cap.setUserData('spirula_arch_request',json.dumps(dict(stage=node.path(),kind=kind,signature=sig,views=views,origin=origin,box=box)))
    return render.start(cap,train=False,preview=kind=='preview')


def started(capture,path,data):
    import hou
    request=data['architecture'];stage=hou.node(request['stage']);remember(stage,job=str(path))
    if request['kind']=='renders':remember(stage,signature=None)
    status(stage,'Calcul lancé. Ouvrir le suivi pour voir le rendu et la progression.')


def completed(capture,result,data):
    import hou
    request=data['architecture'];stage=hou.node(request['stage']);ns=nodes(capture.parent())
    if stage is None:stage=ns[request['kind']]
    if result.get('phase')!='done':return
    remember(stage,job=str(Path(data['folder'])/'job.json'),signature=request['signature'])
    if request['kind']=='preview':status(stage,'Aperçu terminé. Vérifier l’image puis valider avant 04.')
    elif request['kind']=='renders':status(stage,'Images et poses prêtes. Continuer en 05 pour apprendre le splat.')
    else:
        remember(stage,model=result['result'],source_render_job=data['source_render_job']);ns['result'].cook(force=True);ns['result'].setDisplayFlag(True);ns['result'].setRenderFlag(True);status(stage,'Splat chargé. Contrôler en 06 puis exporter en 07.')


def action(node,command):
    import hou,spirula_render as render,spirula_monitor as monitor
    try:
        ns=nodes(node)
        if command in ('preview','renders','train'):
            if any(ns[k].node('CAPTURE').sessionId() in render.JOBS or ns[k].node('CAPTURE').sessionId() in monitor.PENDING for k in ('renders','train')):raise ValueError('Un calcul est déjà actif pour cette scène.')
            cap=ns['train' if command=='train' else 'renders'].node('CAPTURE');cap.setUserData('spirula_arch_active_stage',node.path());return monitor.launch(cap,lambda:request(node,command),'Préparation de la scène Karma…')
        if command=='monitor':return monitor.show(ns['train' if node.userData('spirula_arch_role')=='train' else 'renders'].node('CAPTURE'))
        if command=='stop':return render.stop(ns['train' if node.userData('spirula_arch_role')=='train' else 'renders'].node('CAPTURE'))
        if command=='approve':
            sig=signature(node)
            if state(ns['preview']).get('signature')!=sig:raise ValueError('Recalculer l’aperçu actuel avant validation.')
            remember(ns['preview'],approved=sig);status(ns['preview'],'Aperçu validé. Lancer les rendus en 04.');return
        if command=='cameras':
            views=camera_plan(node);ns['cameras'].parm('guides').set(1);ns['cameras'].setDisplayFlag(True);status(ns['cameras'],'%s caméras. Les dimensions viennent de la cible USD.'%len(views));return views
        if command=='check':
            box=bounds(node);views=camera_plan(node);report=dict(target=box,views=len(views),megapixels=round(sum(v['w']*v['h'] for v in views)/1e6,2),lop=ns['source'].evalParm('lop_source'),quality_measured=False)
            if state(ns['train']).get('model'):
                geo=ns['result'].geometry();report['splat_points']=len(geo.points())
                if not report['splat_points']:raise ValueError('Le modèle appris est vide.')
                for name in ('P','GS_Alpha','scale','orient'):
                    if geo.findPointAttrib(name) and not np.isfinite(np.frombuffer(geo.pointFloatAttribValuesAsString(name),dtype=np.float32)).all():raise ValueError('Valeurs non finies dans le résultat : '+name)
            folder=Path(ns['source'].evalParm('workspace'));folder.mkdir(parents=True,exist_ok=True);(folder/'diagnostic_scene.json').write_text(json.dumps(report,indent=2),encoding='utf8');status(node,'%s vues · %s Mpixels · unités USD : %s m'%(len(views),report['megapixels'],box['meters_per_unit']));return report
        if command=='export_sog':
            if node.sessionId() in render.JOBS:raise ValueError('Une conversion est déjà active pour ce node.')
            from spirula_exchange import launch
            return launch(node,lambda:action(node,'export'),node.evalParm('webfile'))
        if command=='export_monitor':
            node.setUserData('spirula_exchange_ui','1');return monitor.show(node)
        if command=='export_stop':return render.stop(node)
        if command=='export':
            if node.sessionId() in render.JOBS or any(ns[k].node('CAPTURE').sessionId() in render.JOBS for k in ('renders','train')):raise ValueError('Terminer le calcul avant export.')
            if not state(ns['train']).get('model') or state(ns['train']).get('signature')!=signature(node):raise ValueError('Terminer l’apprentissage actuel avant export.')
            from spirula_ply import write_geometry
            from spirula_transform import transformed
            upstream=ns['export'].inputs()[0]
            if upstream.userData('spirula_refine_role'):
                import spirula_refine
                spirula_refine.ensure_exportable(upstream)
            geo=upstream.geometry();path=Path(ns['export'].evalParm('exportfile'));path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name('.partial_'+path.name)
            try:
                with hou.InterruptableOperation('Exporter le splat architectural',open_interrupt_dialog=True):write_geometry(transformed(geo,node.creator().worldTransform()),temp,linearized=not bool(ns['renders'].evalParm('hdr')));temp.replace(path)
            finally:
                if temp.exists():temp.unlink()
            remember(ns['export'],export=str(path));status(ns['export'],'%s gaussiennes exportées : %s'%(len(geo.points()),path));return str(path)
        if command=='next':
            order=['source','cameras','preview','renders','train','result','export'];role=node.userData('spirula_arch_role')
            if role=='export':return
            target=ns[order[order.index(role)+1]]
            if role=='result':target=next((n for n in node.outputs() if n.userData('spirula_refine_role')=='refine_zone'),target)
            target.setCurrent(True,clear_all_selected=True)
            if role in ('train','result'):target.setDisplayFlag(True)
            if hou.isUIAvailable():
                viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                if viewer:viewer.setPwd(node.creator());viewer.enterViewState()
            return target
    except Exception as exc:
        status(node,str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def rebase_stage(stage,origin,frame):
    """Offset highest transformable prims and reset-stack subtrees in a snapshot."""
    from pxr import UsdGeom,Usd,Gf
    translated=[];offset=Gf.Matrix4d().SetTranslate(Gf.Vec3d(*(-np.asarray(origin,dtype=float))))
    for prim in stage.Traverse():
        xform=UsdGeom.Xformable(prim)
        if not xform:continue
        path=str(prim.GetPath());covered=any(path.startswith(p+'/') for p in translated)
        if covered and not xform.GetResetXformStack():continue
        matrix=xform.GetLocalTransformation(Usd.TimeCode(frame));reset=xform.GetResetXformStack();xform.MakeMatrixXform().Set(matrix*offset);xform.SetResetXformStack(reset);translated.append(path)


def create(lop=None):
    import hou
    if lop is None:lop=next((n for n in hou.selectedNodes() if n.type().category()==hou.lopNodeTypeCategory()),None)
    root=hou.node('/obj').createNode('geo','SPIRULA_ARCHITECTURE');root.setUserData('spirula_arch','1')
    roles=[('source','01_SCENE_KARMA'),('cameras','02_CAMERAS_EXTERIEUR'),('preview','03_APERCU_KARMA'),('renders','04_RENDUS_KARMA'),('train','05_APPRENTISSAGE_SPIRULA'),('result','06_SPLAT_HOUDINI'),('export','07_EXPORT_SPLAT')];created={}
    for i,(role,name) in enumerate(roles):
        node=root.createNode('spirula::arch_'+role+'::1.0',name);node.setUserData('spirula_arch_role',role);node.setPosition(hou.Vector2(0,-i*2.5));node.setColor(hou.Color((.28,.47,.66) if i<2 else (.65,.46,.22) if i<4 else (.35,.60,.38)));created[role]=node
        if i:node.setInput(0,created[roles[i-1][0]])
    source=created['source'];source.parm('lop_source').set(lop.path() if lop else '');source.parm('workspace').set('$HIP/Projets/'+root.name());created['export'].parm('exportfile').setExpression('__import__("spirula_arch").nodes(hou.pwd())["source"].evalParm("workspace") + "/04_exports/scene_complete.ply"',language=hou.exprLanguage.Python)
    # Optional detail stages are already in the logical chain; no random Geo nodes.
    if hou.nodeType(hou.sopNodeTypeCategory(),'spirula::refine_zone::1.0') and lop is not None:
        try:
            import spirula_refine
            spirula_refine.create(created['result'])
        except ValueError:pass  # A fresh empty target can be configured before insertion.
    source.setDisplayFlag(True);source.setRenderFlag(True);source.setCurrent(True,clear_all_selected=True)
    note=root.createStickyNote('PARCOURS');note.setText('SCÈNE KARMA → CAMÉRAS → APERÇU VALIDÉ → RENDUS → SPIRULA → CONTRÔLE → EXPORT\n01 référence le LOP final et les chemins USD à cadrer. Le ciel et le sol ne doivent pas gonfler la cible.\nLa scène originale garde ses matériaux et lumières. 04 rend seulement ; 05 apprend seulement.');note.setPosition(hou.Vector2(-5,3));note.setSize(hou.Vector2(16,2.2))
    if hou.isUIAvailable():
        for kind in (hou.paneTabType.NetworkEditor,hou.paneTabType.SceneViewer):
            pane=hou.ui.paneTabOfType(kind)
            if pane:pane.setPwd(root)
        network=hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if network:network.setVisibleBounds(hou.BoundingRect(-6,min([-18]+[n.position().y()-4 for n in root.children()]),12,6))
    return root


def focus(root):
    import hou
    if not hou.isUIAvailable():return
    for kind in (hou.paneTabType.NetworkEditor,hou.paneTabType.SceneViewer):
        pane=hou.ui.paneTabOfType(kind)
        if pane:pane.setPwd(root)
    network=hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if network:
        detail=[n for n in root.children() if n.userData('spirula_refine_role')]
        if root.userData('spirula_focus_detail') and detail:network.setVisibleBounds(hou.BoundingRect(-4,min(n.position().y() for n in detail)-4,14,max(n.position().y() for n in detail)+2))
        else:network.setVisibleBounds(hou.BoundingRect(-6,min([-18]+[n.position().y()-4 for n in root.children()]),12,6))
    viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer:
        try:
            camera=hou.node(root.userData('spirula_preview_camera') or '')
            if camera:viewer.curViewport().setCamera(camera)
            else:
                box=bounds(root);viewer.curViewport().frameBoundingBox(hou.BoundingBox(*(box['lo']+box['hi'])))
        except Exception:pass
