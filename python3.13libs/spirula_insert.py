"""Render meshes in the captured radiance field of native Gaussian splats."""
import json
from pathlib import Path
import numpy as np
_PREVIEWS={}


def setup(node, mesh, scan):
    import hou
    from spirula_object import sop
    mesh=sop(mesh);scan=sop(scan)
    if mesh.geometry().findPointAttrib('GS_Alpha'):raise ValueError('La source objet doit être un mesh, avant conversion en splat.')
    if not scan.geometry().findPointAttrib('GS_Alpha'):raise ValueError('Le décor doit être la sortie de Bake GSplats ou un splat natif.')
    node.parm('source').set(mesh.path());node.parm('seed').set(mesh.path());node.parm('scan_source').set(scan.path())
    node.parm('scan_lighting').set(1);node.parm('backend').set(1);node.parm('studio_lights').set(0);node.parm('isolate').set(1)
    from spirula_render import preset
    preset(node,'high');node.parm('status').set('Prêt : objet éclairé par le scan. Tester une image, puis lancer le splat.')
    return node


def create(mesh=None, scan=None):
    import hou
    from spirula_object import sop
    if mesh is None or scan is None:
        sources=[sop(n) for n in hou.selectedNodes()]
        scans=[n for n in sources if n.geometry().findPointAttrib('GS_Alpha')]
        meshes=[n for n in sources if not n.geometry().findPointAttrib('GS_Alpha')]
        if len(scans)!=1 or len(meshes)!=1:raise ValueError('Sélectionner exactement un objet mesh et un objet de splats natifs, puis relancer cet outil.')
        mesh,scan=meshes[0],scans[0]
    obj=hou.node('/obj').createNode('geo','SPIRULA_INSERT_AND_BAKE')
    node=obj.createNode('spirula::render_splat::1.0','OBJET_ECLAIRE_PAR_SCAN')
    try:setup(node,mesh,scan)
    except Exception:obj.destroy();raise
    node.setCurrent(True,clear_all_selected=True);return node


def create_simple(mesh=None,scan=None):
    import hou
    from spirula_object import sop
    from spirula_transform import bounding_box
    if mesh is None or scan is None:
        sources=[sop(n) for n in hou.selectedNodes()]
        meshes=[n for n in sources if not n.geometry().findPointAttrib('GS_Alpha')]
        scans=[n for n in sources if n.geometry().findPointAttrib('GS_Alpha')]
        if len(meshes)!=1 or len(scans)!=1:raise ValueError('Sélectionner un objet mesh et un décor splat, puis relancer Insérer objet éclairé par scan.')
        mesh,scan=meshes[0],scans[0]
    mesh=sop(mesh);scan=sop(scan)
    if mesh.geometry().findPointAttrib('GS_Alpha') or not scan.geometry().findPointAttrib('GS_Alpha'):raise ValueError('Il faut une source mesh et un décor de splats natifs.')
    obj=hou.node('/obj').createNode('geo','SPIRULA_INSERTION')
    obj.setWorldTransform(hou.hmath.buildTranslate(bounding_box(mesh.geometry(),mesh.creator().worldTransform()).center()))
    node=obj.createNode('spirula::insert_asset::1.0','INSERER_OBJET')
    node.parm('mesh').set(mesh.path());node.parm('scan').set(scan.path());node.setDisplayFlag(True);node.setRenderFlag(True);node.setCurrent(True,clear_all_selected=True)
    obj.moveToGoodPosition();return node


def simple_callback(node,action):
    import hou
    import spirula_render as render
    try:
        capture=node.node('CAPTURE');mesh=hou.node(node.evalParm('mesh'));scan=hou.node(node.evalParm('scan'))
        import spirula_monitor as monitor
        if action=='workflow':
            import spirula_workflow
            hou.ui.postEventCallback(lambda:spirula_workflow.open(node));return
        if action=='monitor':return monitor.show(capture)
        if action in ('preview','start','resume','export'):
            if capture.sessionId() in render.JOBS or capture.sessionId() in monitor.PENDING:raise RuntimeError('Un calcul est déjà actif ou en préparation. Ouvrir le suivi pour voir sa progression.')
            message={'preview':'Demande reçue : préparation de l’aperçu…','export':'Export du décor et de l’objet…'}.get(action,'Demande reçue : préparation du calcul…')
            return monitor.launch(capture,lambda:_simple_run(node,action),message)
        return _simple_run(node,action)
    except Exception as exc:
        node.node('CAPTURE').parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def _simple_run(node,action):
    import hou
    import spirula_render as render
    try:
        capture=node.node('CAPTURE');mesh=hou.node(node.evalParm('mesh'));scan=hou.node(node.evalParm('scan'))
        if action=='export':
            if capture.geometry().intrinsicValue('pointcount')==0:raise ValueError('Générer le splat de l’objet avant l’export.')
            import spirula_scene
            result=spirula_scene.assemble([scan,node]);result.parm('exportfile').set(node.evalParm('exportfile'));report=spirula_scene.export(result)
            import spirula_monitor as monitor,time
            message='%s gaussiennes exportées : %s'%(report['gaussians'],report['file']);capture.parm('status').set(message)
            monitor.OVERRIDES[capture.sessionId()]={'phase':'done','message':message,'started':time.time()-report['seconds'],'finished':time.time()};monitor.update_node(capture,monitor.OVERRIDES[capture.sessionId()]);return report
        if action=='image':return show_preview(capture)
        if action=='resume':return render.start(capture,train=True,resume=True)
        if action in ('stop','folder'):return render.callback(capture,action)
        if capture.sessionId() in render.JOBS:raise RuntimeError('Un calcul est déjà actif. Attendre sa fin ou utiliser Arrêter.')
        capture.parm('capture_mode').set(0)
        setup(capture,mesh,scan)
        render.preset(capture,['preview','high','production'][node.evalParm('quality')])
        if node.evalParm('detail')>0:
            capture.parm('capture_mode').set(3);capture.parm('target_detail').set(node.evalParm('detail'));capture.parm('max_views').set(node.evalParm('max_views'))
        capture.parm('exposure').set(node.evalParm('exposure'));capture.parm('workspace').set(node.evalParm('workspace'))
        if capture.userData('spirula_workflow_request'):
            capture.parm('workspace').set(str(Path(node.evalParm('workspace'))/('01_apercus' if action=='preview' else '02_generation')))
        if action=='preview':
            capture.parm('width').set(512);capture.parm('height').set(512);capture.parm('samples').set(8)
            return render.start(capture,train=False,preview=True)
        return render.start(capture,train=True)
    except Exception as exc:
        node.node('CAPTURE').parm('status').set(str(exc))
        raise


def show_preview(node):
    import hou
    if not hou.isUIAvailable():return
    from PySide6 import QtWidgets,QtGui,QtCore
    config=Path(node.evalParm('jobfile'))
    images=sorted((config.parent/'images').glob('*.png')) if config.is_file() else []
    if not images:raise ValueError('Aucun aperçu disponible. Cliquer Voir l’objet éclairé par le scan.')
    key=node.sessionId();dialog=_PREVIEWS.get(key)
    if dialog is not None:
        try:dialog.close()
        except RuntimeError:pass
    dialog=QtWidgets.QDialog(hou.qt.mainWindow());dialog.setWindowTitle('Karma · Objet éclairé par le scan');layout=QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(QtWidgets.QLabel('Aperçu du rendu — le scan éclaire l’objet et reste invisible à la caméra.'))
    label=QtWidgets.QLabel();label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);label.setStyleSheet('background:#454545;')
    pixmap=QtGui.QPixmap(str(images[0]));label.setPixmap(pixmap if max(pixmap.width(),pixmap.height())<=900 else pixmap.scaled(900,900,QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation));layout.addWidget(label)
    path=QtWidgets.QLabel(str(images[0]));path.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(path)
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);dialog.show();_PREVIEWS[key]=dialog
    return dialog


def exterior_plan(node):
    """Overlapping facade tiles; reject excessive work before creating a job."""
    import hou,math
    from spirula_object import sop
    from spirula_transform import bounding_box
    from spirula_render import look_at,entry
    source=sop(hou.node(node.evalParm('source')));box=bounding_box(source.geometry(),source.creator().worldTransform())
    lo=np.array(box.minvec());hi=np.array(box.maxvec());size=hi-lo
    detail=node.evalParm('target_detail');width=node.evalParm('width');height=node.evalParm('height')
    if detail<=0:raise ValueError('Définir une précision cible positive, en unités de scène par pixel.')
    span=np.array([detail*width,detail*height]);distance=span[0]/(2*math.tan(math.radians(node.evalParm('fov'))/2))
    layouts=[];total=0
    for axis in range(3):
        other=[[2,1],[0,2],[0,1]][axis]
        counts=np.maximum(1,np.ceil(size[other]/(span*.7)).astype(int));total+=int(2*np.prod(counts));layouts.append((axis,other,counts))
    if total>node.evalParm('max_views'):raise ValueError('%s vues de façade prévues, au-delà de la limite %s. Augmenter les unités/pixel, découper le bâtiment ou relever explicitement la limite.'%(total,node.evalParm('max_views')))
    views=[]
    for axis,other,counts in layouts:
        for side in (-1,1):
            for i in range(int(counts[0])):
                for j in range(int(counts[1])):
                    target=(lo+hi)/2;target[axis]=lo[axis] if side<0 else hi[axis]
                    target[other[0]]=lo[other[0]]+(i+.5)*size[other[0]]/counts[0];target[other[1]]=lo[other[1]]+(j+.5)*size[other[1]]/counts[1]
                    pos=target.copy();pos[axis]+=side*distance
                    views.append(entry(look_at(pos,target),width,height,node.evalParm('fov')))
    return views


def prepare_stage(data, folder):
    """Freeze a small USD layer stack once, without primary scan visibility."""
    import hou
    from pxr import Usd,Sdf,UsdGeom
    from spirula_render import _set
    from spirula_object import sop
    from spirula_transform import transformed
    folder=Path(folder);mesh=sop(hou.node(data['source']));scan=sop(hou.node(data['scan_source']))
    origin=np.array(data.get('training_origin',[0.,0.,0.]));shift=hou.hmath.buildTranslate(tuple(-origin))
    if not scan.geometry().findPointAttrib('GS_Alpha'):raise ValueError('Le décor de capture ne contient pas de splats natifs.')
    if mesh.geometry().findPointAttrib('GS_Alpha'):raise ValueError('Choisir la source mesh de l’objet et non son splat précédent.')
    env_geo=transformed(scan.geometry(),scan.creator().worldTransform()*shift)
    cache=folder/'scan_local.bgeo.sc';env_geo.saveToFile(str(cache))
    env=hou.node('/obj').createNode('geo','SPIRULA_RADIANCE_FIELD')
    f=env.createNode('file','SCAN');f.parm('file').set(str(cache));f.setDisplayFlag(True);f.setRenderFlag(True)
    proxy=hou.node('/obj').createNode('geo','SPIRULA_INSERT_MESH');proxy.setWorldTransform(mesh.creator().worldTransform()*shift)
    _set(proxy,'shop_materialpath',mesh.creator().evalParm('shop_materialpath') if mesh.creator().parm('shop_materialpath') else '')
    m=proxy.createNode('object_merge','MESH_SOURCE');m.parm('objpath1').set(mesh.path());m.parm('xformtype').set(0);m.setDisplayFlag(True);m.setRenderFlag(True)
    # The controller can live in a hidden OBJ; these dedicated proxies stay visible.
    env.setDisplayFlag(True);proxy.setDisplayFlag(True)
    imp=hou.node('/stage').createNode('sceneimport::2.0','SPIRULA_INSERT_IMPORT');imp.parm('objects').set(env.path()+' '+proxy.path())
    settings=hou.node('/stage').createNode('karmarendersettings','SPIRULA_INSERT_SETTINGS');settings.setInput(0,imp)
    for name,value in [('engine','xpu'),('res_mode','manual'),('resolutionx',data['width']),('resolutiony',data['height']),('camera','/SpirulaCapture/camera'),('pathtracedsamples',data['samples']**2),('diffuselimit',2),('reflectlimit',3)]:
        _set(settings,name,value)
        if name=='res_mode':settings.parm(name).pressButton()
    stage=Usd.Stage.Open(settings.stage().Flatten())
    scan_path='/'+env.name();found=False
    for prim in stage.Traverse():
        if str(prim.GetPath()).startswith(scan_path+'/') and prim.GetTypeName()=='ParticleField3DGaussianSplat':
            found=True;prim.CreateAttribute('primvars:karma:object:rendervisibility',Sdf.ValueTypeNames.String).Set('-primary')
    if not found:raise RuntimeError('Le scan n’a pas été importé en ParticleField3DGaussianSplat. Vérifier Bake GSplats et le Scene Import.')
    cam=UsdGeom.Camera.Define(stage,'/SpirulaCapture/camera');cam.CreateClippingRangeAttr()
    path=folder/'lighting_scene.usdc';stage.GetRootLayer().Export(str(path))
    return path


def render_view(data, base, view, target):
    import hou,subprocess,time,re,os
    from pxr import Usd,UsdGeom,Gf
    from spirula_render import atomic_json
    target=Path(target);path=target.parent.parent/'capture.usda'
    stage=Usd.Stage.CreateInMemory();stage.GetRootLayer().subLayerPaths=[str(base)]
    cam=UsdGeom.Camera.Define(stage,'/SpirulaCapture/camera');cam.GetHorizontalApertureAttr().Set(36.);cam.GetVerticalApertureAttr().Set(36.*view['h']/view['w']);cam.GetFocalLengthAttr().Set(36.*view['fl_x']/view['w'])
    origin=np.array(data.get('training_origin',[0.,0.,0.]));matrix=np.array(view['transform_matrix']);matrix[:3,3]-=origin
    cam.MakeMatrixXform().Set(Gf.Matrix4d(*matrix.T.ravel().tolist()))
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(*data.get('clip_range',[.001,100000.])))
    stage.GetRootLayer().Export(str(path))
    command=[hou.text.expandString('$HFS/bin/husk.exe'),str(path),'--headlight','none','--camera','/SpirulaCapture/camera','--res',str(view['w']),str(view['h']),'-o',str(target),'--disable-motionblur','--image-mode','progressive','--snapshot','3','-V','a2','-R','BRAY_HdKarmaXPU']
    folder=target.parent.parent;logpath=folder/'render.log';started=time.time();last_snapshot=None
    try:initial=json.loads((folder/'status.json').read_text(encoding='utf8'))
    except (OSError,ValueError):initial={}
    from spirula_monitor import tail
    from spirula_render import exr_to_png
    with logpath.open('ab',buffering=0) as log:
        offset=logpath.stat().st_size
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while process.poll() is None:
            with logpath.open('rb') as reader:
                reader.seek(max(offset,logpath.stat().st_size-8192));text=reader.read().decode('utf8',errors='replace')
            matches=re.findall(r'ALF_PROGRESS\s+([\d.]+)%?',text)
            state=dict(initial,phase='rendering',message='Karma : image %s / %s'%(int(target.stem)+1,len(data['views'])),rendered=int(target.stem),total=len(data['views']),render_pid=process.pid,worker_pid=os.getpid(),updated=time.time(),frame_seconds=time.time()-started)
            if matches:state['frame_progress']=max(0,min(100,float(matches[-1])))
            atomic_json(folder/'status.json',state)
            partial=target.with_name(target.stem+'_part.exr')
            try:
                signature=partial.stat().st_mtime_ns
                if signature!=last_snapshot:
                    temp=folder/'live.partial.png';exr_to_png(partial,temp,data['exposure'],data if data.get('working_space') else None,allow_incomplete=True);os.replace(temp,folder/'live.png');last_snapshot=signature
            except Exception as exc:
                if partial.exists():(folder/'preview_note.txt').write_text(str(exc),encoding='utf8')
            time.sleep(.75)
        if process.returncode:raise RuntimeError('Karma a échoué (code %s). Voir render.log.'%process.returncode)


def output_geometry(node):
    import hou
    from spirula_transform import transformed
    out=node.geometry();out.clear();parent=node.parent()
    matrix=json.loads(parent.evalParm('result_transform') or '[]')
    source=node.inputs()[0].geometry()
    if matrix and source.findPointAttrib('GS_Alpha'):out.merge(transformed(source,hou.Matrix4(tuple(matrix))))
    else:out.merge(source)
