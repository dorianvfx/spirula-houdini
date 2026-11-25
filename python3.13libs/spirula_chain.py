"""Explicit wired SOP stages, in one Geo: photos to final Gaussian composition."""
import hashlib
import json
import time
from pathlib import Path


def rig(node):
    return node if node.userData('spirula_chain') else node.creator()


def config(node):
    root=rig(node);data=json.loads(root.userData('spirula_chain'))
    for child in root.children():
        role=child.userData('spirula_chain_role')
        if role in ('studio','scan'):data[role]=child.path()
        elif role:
            index=int(child.userData('spirula_chain_branch') or 0)
            if index<len(data['branches']):data['branches'][index][role]=child.path()
    return data


def branch(node):
    return config(node)['branches'][int(node.userData('spirula_chain_branch') or 0)]


def nodes(node):
    import hou
    return {key:hou.node(path) for key,path in branch(node).items() if isinstance(path,str) and path.startswith('/')}


def state(node):
    return json.loads(node.userData('spirula_chain_state') or '{}')


def remember(node,**values):
    data=state(node);data.update(values);node.setUserData('spirula_chain_state',json.dumps(data));return data


def status(node,message):
    if node.parm('status'):node.parm('status').set(message)
    node.setComment(message)
    import hou
    node.setGenericFlag(hou.nodeFlag.DisplayComment,True)


def geometry(node,role):
    import hou
    from spirula_transform import transformed
    out=node.geometry();stage=node.parent();out.clear()
    if role=='scan':
        source=stage.inputs()[0]
        if source is None:return
        source=source.geometry()
        if not source or not source.intrinsicValue('pointcount'):return
        matrix=hou.hmath.buildTransform({'translate':stage.evalParmTuple('t'),'rotate':stage.evalParmTuple('r'),'scale':stage.evalParmTuple('s')})
        out.merge(transformed(source,matrix));return
    if role=='mesh':
        source=stage.inputs()[0] if stage.inputs() else None
        if stage.evalParm('mode')==0:
            if source is not None:out.merge(source.geometry())
            return
        if stage.evalParm('mode')==1:
            filename=stage.evalParm('file')
            if filename:out.loadFromFile(filename)
        else:
            source=hou.node(stage.evalParm('source'))
            if source is None:return
            from spirula_object import sop
            source=sop(source)
            if any(source==n or source.path().startswith(n.path()+'/') for n in nodes(stage).values()):raise hou.NodeError('Choisir une géométrie en amont, pas un nœud de traitement de cette même branche.')
            out.merge(source.geometry());out.transform(source.creator().worldTransform()*stage.creator().worldTransform().inverted())
            material=source.creator().evalParm('shop_materialpath') if source.creator().parm('shop_materialpath') else ''
            if material and not out.findPrimAttrib('shop_materialpath'):out.addAttrib(hou.attribType.Prim,'shop_materialpath',material)
        return
    if role in ('light','cameras'):
        if role=='light':
            for i,source in enumerate(stage.inputs()):
                if source is None:continue
                geo=hou.Geometry();geo.merge(source.geometry())
                if i==1 and not geo.findPointAttrib('Cd'):geo.addAttrib(hou.attribType.Point,'Cd',(1.,1.,1.))
                out.merge(geo)
        elif stage.inputs() and stage.inputs()[0]:out.merge(stage.inputs()[0].geometry())
        if role=='cameras' and stage.evalParm('show_cameras'):
            import numpy as np
            guide=hou.Geometry();guide.addAttrib(hou.attribType.Point,'Cd',(.1,.7,1.))
            for view in camera_plan(stage):
                matrix=np.array(view['transform_matrix']);distance=max(.03,stage.evalParm('guide_size'))
                x=distance*view['w']/(2*view['fl_x']);y=distance*view['h']/(2*view['fl_y'])
                points=(np.array([[0,0,0],[-x,-y,-distance],[x,-y,-distance],[x,y,-distance],[-x,y,-distance]])@matrix[:3,:3].T+matrix[:3,3])
                world=stage.creator().worldTransform().inverted();pts=guide.createPoints([hou.Vector3(tuple(p))*world for p in points])
                for a,b in ((0,1),(0,2),(0,3),(0,4),(1,2),(2,3),(3,4),(4,1)):
                    line=guide.createPolygon(is_closed=False);line.addVertex(pts[a]);line.addVertex(pts[b])
            out.merge(guide)
        return
    if role=='train':
        model=state(stage)
        if not model.get('model'):return
        ns=nodes(stage)
        if model.get('dataset_signature')!=dataset_signature(stage) or model.get('source_render_job')!=state(ns['render']).get('job'):raise hou.NodeError('Les sources ou les rendus ont changé : repasser par 05, 07 puis 08.')
        capture=ns['train'].node('CAPTURE');capture.cook(force=True);geo=capture.geometry()
        if geo is not None:out.merge(geo)
        return
    if role=='assemble':
        for source in stage.inputs():
            if source is not None:out.merge(source.geometry())


def require_sources(node):
    import hou
    ns=nodes(node);scan=ns['light'].inputs()[0];mesh=ns['place']
    if scan is None:raise ValueError('Brancher le scan 02 sur la première entrée de 05.')
    scan.cook(force=True);mesh.cook(force=True)
    sg=scan.geometry();mg=mesh.geometry()
    if sg is None or not sg.intrinsicValue('pointcount') or not sg.findPointAttrib('GS_Alpha'):raise ValueError('01 : créer le scan depuis les photos dans Spirula, puis Envoyer vers Houdini. Aligner ensuite le scan en 02.')
    if mg is None or not mg.intrinsicValue('pointcount') or mg.findPointAttrib('GS_Alpha'):raise ValueError('03 : charger ou brancher un mesh, puis le placer en 04.')
    return scan,mesh


def look_signature(node):
    scan,mesh=require_sources(node);digest=hashlib.sha256()
    from spirula_quality import geometry_signature,file_signature
    for source in (scan,mesh):
        geo=source.geometry();digest.update(source.path().encode());digest.update(str(source.creator().worldTransform().asTuple()).encode())
        digest.update(geometry_signature(geo).encode())
        for name in ('P','Cd','N','uv','GS_Alpha','scale','pscale','orient','restorient','GS_SPH_R','GS_SPH_G','GS_SPH_B'):
            if geo.findPointAttrib(name):digest.update(geo.pointFloatAttribValuesAsString(name))
        if geo.findVertexAttrib('uv'):digest.update(geo.vertexFloatAttribValuesAsString('uv'))
        if geo.findPrimAttrib('shop_materialpath'):
            import hou
            for path in sorted(set(geo.primStringAttribValues('shop_materialpath'))):
                material=hou.node(path)
                if material:
                    for child in (material,)+material.allSubChildren():
                        for parm in child.parms():
                            try:
                                value=parm.evalAsString();digest.update((parm.path()+':'+value).encode('utf8'))
                                if isinstance(parm.parmTemplate(),hou.StringParmTemplate) and parm.parmTemplate().stringType()==hou.stringParmType.FileReference:digest.update(file_signature(value).encode())
                            except hou.Error:pass
    digest.update(str(nodes(node)['light'].evalParm('exposure')).encode())
    import hou
    digest.update(str(hou.frame()).encode())
    return digest.hexdigest()


def dataset_signature(node):
    ns=nodes(node);digest=hashlib.sha256(look_signature(node).encode())
    for key,parms in [('cameras',('mode','views','elevations','radius','fov','detail','max_views')),('render',('width','height','samples'))]:
        digest.update(str([ns[key].evalParm(name) for name in parms]).encode())
    return digest.hexdigest()


def camera_plan(node):
    require_sources(node)
    from spirula_render import camera_plan as plan
    ns=nodes(node);cam=ns['cameras'];render=ns['render']
    class Camera:
        def evalParm(self,name):
            if name=='source':return ns['place'].path()
            if name=='capture_mode':return 0 if cam.evalParm('mode')==0 else 3
            if name=='target_detail':return cam.evalParm('detail')
            return (render if name in ('width','height') else cam).evalParm(name)
    return plan(Camera())


def configure(node,preview=False):
    ns=nodes(node);scan,mesh=require_sources(node);capture=ns['render'].node('CAPTURE');cam=ns['cameras'];light=ns['light'];r=ns['render'];train=ns['train']
    settings={'source':mesh.path(),'seed':mesh.path(),'scan_source':scan.path(),'scan_lighting':1,'backend':1,'studio_lights':0,'isolate':1,'capture_mode':0 if cam.evalParm('mode')==0 else 3,'views':cam.evalParm('views'),'elevations':cam.evalParm('elevations'),'radius':cam.evalParm('radius'),'fov':cam.evalParm('fov'),'target_detail':cam.evalParm('detail'),'max_views':cam.evalParm('max_views'),'width':512 if preview else r.evalParm('width'),'height':512 if preview else r.evalParm('height'),'samples':8 if preview else r.evalParm('samples'),'exposure':light.evalParm('exposure'),'iterations':train.evalParm('iterations'),'cap':train.evalParm('cap')}
    for name,value in settings.items():capture.parm(name).set(value)
    __import__('spirula_train_profiles').apply_to_capture(train,capture)
    return capture


def started(capture,path,data):
    import hou
    request=data.get('chain')
    if not request:return
    stage=hou.node(request['stage']) or nodes(capture.parent())[{'preview':'light','render':'render','train':'train'}[request['kind']]];remember(stage,job=str(path))
    if request['kind']=='render':remember(stage,dataset_signature=None)
    status(stage,'Calcul lancé · ouvrir le suivi en direct.')


def completed(capture,result,data):
    import hou
    request=data.get('chain')
    if not request:return
    stage=hou.node(request['stage']) or nodes(capture.parent())[{'preview':'light','render':'render','train':'train'}[request['kind']]];ns=nodes(stage)
    if result.get('phase')!='done':return
    if request['kind']=='preview':
        remember(stage,preview_signature=request['signature'],job=str(Path(data['folder'])/'job.json'));status(stage,'Aperçu prêt. Vérifier l’image, puis Valider et passer en 06.')
    elif request['kind']=='render':
        remember(stage,dataset_signature=request['signature'],job=str(Path(data['folder'])/'job.json'));status(stage,'Rendus terminés. Passer en 08 pour apprendre le splat.');status(ns['train'],'Dataset prêt : lancer l’apprentissage depuis ces rendus.')
    else:
        remember(stage,model=result['result'],dataset_signature=request['signature'],source_render_job=data['source_render_job'],iterations=data['iterations']);status(stage,'Splat chargé. Passer en 09 pour vérifier l’assemblage.')
        ns['train'].cook(force=True);ns['assemble'].cook(force=True);ns['assemble'].setDisplayFlag(True);ns['assemble'].setRenderFlag(True)


def _run(node,command):
    import hou
    import spirula_render as render
    ns=nodes(node);capture=ns['train' if command=='train' else 'render'].node('CAPTURE');capture.setUserData('spirula_chain_active_stage',node.path());capture.setUserData('spirula_chain_active_role',node.userData('spirula_chain_role'))
    if command=='preview':
        capture=configure(node,True);sig=look_signature(node);kind='preview'
    elif command=='render':
        if state(ns['light']).get('approved_signature')!=look_signature(node):raise ValueError('05 : calculer puis valider l’éclairage avant les rendus.')
        capture=configure(node);sig=dataset_signature(node);kind='render'
    else:
        dataset=state(ns['render']);sig=dataset_signature(node)
        if dataset.get('dataset_signature')!=sig:raise ValueError('07 : rendre les vues actuelles avant d’entraîner le splat.')
        import os,shutil,uuid
        primitive=__import__('spirula_train_profiles').selected(ns['train']);previous=state(ns['train']);source_job=Path(dataset['job'])
        if previous.get('source_render_job')==str(source_job) and previous.get('dataset_signature')==sig and previous.get('job') and Path(previous['job']).is_file() and __import__('spirula_train_profiles').compatible(json.loads(Path(previous['job']).read_text(encoding='utf8')),primitive) and __import__('spirula_train_profiles').engine_matches(json.loads(Path(previous['job']).read_text(encoding='utf8')),ns['train']) and json.loads(Path(previous['job']).read_text(encoding='utf8'))['cap']==ns['train'].evalParm('cap'):
            path=Path(previous['job']);data=json.loads(path.read_text(encoding='utf8'))
        else:
            data=json.loads(source_job.read_text(encoding='utf8'));root=hou.node(config(node)['studio']);folder=Path(root.evalParm('workspace'))/'03_apprentissage'/('objet_%02d'%(int(node.userData('spirula_chain_branch'))+1))/('train_'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
            for directory in ('images','renders'):
                (folder/directory).mkdir()
                for i in range(len(data['views'])):
                    source=source_job.parent/directory/('%05d.%s'%(i,'png' if directory=='images' else 'exr'))
                    if not source.is_file():raise ValueError('Image manquante : revenir en 07 pour rendre le dataset complet.')
                    target=folder/directory/source.name
                    try:os.link(source,target)
                    except OSError:shutil.copy2(source,target)
            data.update(folder=str(folder),source_render_job=str(source_job),require_cached_renders=True);path=folder/'job.json'
        data.update(executable=__import__('spirula_train_profiles').engine_path(ns['train']),primitive=primitive,iterations=ns['train'].evalParm('iterations'),cap=ns['train'].evalParm('cap'),train=True,chain={'stage':node.path(),'kind':'train','signature':sig})
        remember(ns['train'],model=None,source_render_job=str(source_job),dataset_signature=sig,job=str(path));ns['light'].setDisplayFlag(True)
        render.atomic_json(path,data);capture.parm('jobfile').set(str(path));__import__('spirula_train_profiles').apply_to_capture(ns['train'],capture);return render.start(capture,train=True,resume=True)
    root=hou.node(config(node)['studio']);folder=Path(root.evalParm('workspace'))/('01_apercus' if kind=='preview' else '02_rendus')/('objet_%02d'%(int(node.userData('spirula_chain_branch'))+1));capture.parm('workspace').set(str(folder))
    capture.setUserData('spirula_chain_request',json.dumps({'stage':node.path(),'kind':kind,'signature':sig}));return render.start(capture,train=False,preview=kind=='preview')


def action(node,command):
    import hou
    try:
        if command=='audit':
            import spirula_quality
            return spirula_quality.audit(node)
        ns=nodes(node)
        if command in ('preview','render','train'):
            import spirula_monitor,spirula_render
            capture=ns['train' if command=='train' else 'render'].node('CAPTURE');capture.setUserData('spirula_chain_active_stage',node.path());capture.setUserData('spirula_chain_active_role',node.userData('spirula_chain_role'))
            if any(ns[role].node('CAPTURE').sessionId() in spirula_render.JOBS or ns[role].node('CAPTURE').sessionId() in spirula_monitor.PENDING for role in ('render','train')):raise ValueError('Un calcul est déjà actif pour cet objet. Ouvrir le suivi.')
            return spirula_monitor.launch(capture,lambda:_run(node,command),'Préparation de l’étape '+node.name()+'…')
        if command=='monitor':
            import spirula_monitor
            return spirula_monitor.show(ns['train' if node.userData('spirula_chain_role')=='train' else 'render'].node('CAPTURE'))
        if command=='stop':
            import spirula_render
            return spirula_render.stop(ns['train' if node.userData('spirula_chain_role')=='train' else 'render'].node('CAPTURE'))
        if command=='approve':
            sig=look_signature(node)
            if state(node).get('preview_signature')!=sig:raise ValueError('Recalculer l’aperçu avec le placement et l’exposition actuels avant de valider.')
            remember(node,approved_signature=sig);status(node,'Éclairage validé. Continuer en 06 : caméras.');return action(node,'next')
        if command=='export_sog':
            import spirula_render,spirula_exchange
            if node.sessionId() in spirula_render.JOBS:raise ValueError('Une conversion est déjà active pour ce node.')
            return spirula_exchange.launch(node,lambda:action(node,'export'),node.evalParm('webfile'))
        if command=='export_monitor':
            import spirula_monitor
            return spirula_monitor.show(node)
        if command=='export_stop':
            import spirula_render
            return spirula_render.stop(node)
        if command=='export':
            import spirula_render,spirula_monitor
            if any(ns[role].node('CAPTURE').sessionId() in spirula_render.JOBS or ns[role].node('CAPTURE').sessionId() in spirula_monitor.PENDING for role in ('render','train')):raise ValueError('Terminer le calcul actif avant d’exporter.')
            from spirula_ply import write_geometry
            from spirula_transform import transformed
            if state(ns['train']).get('dataset_signature')!=dataset_signature(node):raise ValueError('Le splat 08 ne correspond pas aux sources actuelles.')
            source=node.inputs()[0];source.cook(force=True);geo=source.geometry()
            if not state(ns['train']).get('model') or not geo or not geo.intrinsicValue('pointcount'):raise ValueError('Terminer 08 avant d’exporter.')
            path=Path(node.evalParm('exportfile'));path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name('.partial_'+path.name)
            try:
                with hou.InterruptableOperation('Exporter la scène complète',open_interrupt_dialog=True):write_geometry(transformed(geo,node.creator().worldTransform()),temp,linearized=True);temp.replace(path)
            finally:
                if temp.exists():temp.unlink()
            status(node,'Export terminé : %s gaussiennes · %s'%(geo.intrinsicValue('pointcount'),path));remember(node,export=str(path));return str(path)
        if command=='repeat':
            if not state(node).get('export') or not Path(state(node)['export']).is_file():raise ValueError('Exporter la scène en 10 avant d’ajouter une nouvelle branche objet.')
            node.cook(force=True);return add_branch(rig(node),node,True)
        if command=='pick':
            from spirula_object import sop
            selected=[n for n in hou.selectedNodes() if n!=node]
            if not selected:raise ValueError('Sélectionner un OBJ ou un SOP mesh, puis cliquer ce bouton depuis le panneau de paramètres épinglé.')
            source=sop(selected[0]);node.parm('mode').set(2);node.parm('source').set(source.path())
            if source.creator()!=rig(node):source.creator().setDisplayFlag(False)
            return action(node,'next')
        if command=='cameras':
            views=camera_plan(node);node.parm('show_cameras').set(1);node.setDisplayFlag(True);status(node,'%s poses de caméra. Régler la couverture puis passer en 07.'%len(views));return
        if command=='next':
            role=node.userData('spirula_chain_role');order=['studio','scan','mesh','place','light','cameras','render','train','assemble','export'];target=ns.get(order[order.index(role)+1]) if role!='export' else None
            if role in ('studio','scan'):
                check=hou.node(config(node)['scan']).geometry()
                if not check or not check.intrinsicValue('pointcount'):raise ValueError('Créer le scan dans Spirula puis Envoyer vers Houdini avant de continuer.')
            if role=='mesh':
                check=node.geometry()
                if not check or not check.intrinsicValue('pointcount'):raise ValueError('Charger un fichier ou brancher un mesh sur 03 avant de le placer.')
            if role=='render' and state(node).get('dataset_signature')!=dataset_signature(node):raise ValueError('Terminer les rendus 07 avant de passer à l’apprentissage.')
            if role in ('train','assemble') and not state(ns['train']).get('model'):raise ValueError('Terminer l’apprentissage 08 avant la composition et l’export.')
            if role=='studio':target=hou.node(config(node)['scan'])
            if role=='scan':target=ns['mesh']
            if target:
                target.setCurrent(True,clear_all_selected=True)
                display=ns['light'] if role in ('scan','mesh','place') else target
                display.setDisplayFlag(True);display.setRenderFlag(True)
                viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer) if hou.isUIAvailable() else None
                if viewer:
                    viewer.setPwd(rig(node))
                    if role=='mesh':viewer.setCurrentState('xform')
                    else:viewer.enterViewState()
            return target
    except Exception as exc:
        status(node,str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def add_branch(root,scan=None,focus=False):
    import hou
    data=config(root);index=len(data['branches']);suffix='' if index==0 else '_OBJET_%02d'%(index+1);x=4+index*8
    names=[('mesh','spirula::chain_mesh::1.0','03_OBJET_3D',0),('place','xform','04_PLACER_OBJET',-2),('light','spirula::chain_light::1.0','05_ECLAIRAGE',-4),('cameras','spirula::chain_cameras::1.0','06_CAMERAS',-6),('render','spirula::chain_render::1.0','07_RENDUS_KARMA',-8),('train','spirula::chain_train::1.0','08_APPRENTISSAGE_SPLAT',-10),('assemble','spirula::chain_assemble::1.0','09_ASSEMBLAGE',-12),('export','spirula::chain_export::1.0','10_EXPORT_SCENE',-14)]
    created={}
    for role,kind,name,y in names:
        n=root.createNode(kind,name+suffix);n.setPosition(hou.Vector2(x,y-8 if root.userData('spirula_repair_layout') else y));n.setUserData('spirula_chain_role',role);n.setUserData('spirula_chain_branch',str(index));n.setUserData('nodeshape','rect');created[role]=n
        n.setColor(hou.Color((.28,.46,.65) if role in ('mesh','place') else (.65,.46,.22) if role in ('light','cameras','render') else (.35,.6,.38)))
    scan=scan or hou.node(data['scan']);created['place'].setInput(0,created['mesh']);created['light'].setInput(0,scan);created['light'].setInput(1,created['place'])
    for a,b in [('cameras','light'),('render','cameras'),('train','render')]:created[a].setInput(0,created[b])
    created['assemble'].setInput(0,scan);created['assemble'].setInput(1,created['train']);created['export'].setInput(0,created['assemble'])
    created['export'].parm('exportfile').set(str(Path(hou.node(data['studio']).evalParm('workspace'))/'04_exports'/('scene_objets_%02d.ply'%(index+1))))
    data['branches'].append({key:n.path() for key,n in created.items()});root.setUserData('spirula_chain',json.dumps(data))
    place=created['place'];group=place.parmTemplateGroup();button=hou.ButtonParmTemplate('chain_next','Continuer en 05 · Éclairage');button.setScriptCallback("import spirula_chain;spirula_chain.action(kwargs['node'],'next')");button.setScriptCallbackLanguage(hou.scriptLanguage.Python);group.append(button);place.setParmTemplateGroup(group)
    for role,n in created.items():status(n,{'mesh':'Charger un fichier ou brancher ici votre géométrie créée dans ce même réseau.','place':'Placer le mesh ici. Le scan reste visible via 05.','light':'Calculer l’aperçu, le vérifier, puis valider l’éclairage.','cameras':'Définir le tour d’objet ou les vues de façade.','render':'Rendre les images. Cette étape ne lance pas l’apprentissage.','train':'Apprendre depuis les images terminées en 07, sans les recalculer.','assemble':'Le scan et le splat 08 sont assemblés par les connexions.','export':'Exporter la composition ou ajouter une nouvelle branche objet.'}[role])
    for n in created.values():n.setGenericFlag(hou.nodeFlag.DisplayComment,False)
    box=root.createNetworkBox('OBJET_%02d'%(index+1));box.setComment('OBJET %02d · étapes 03 à 10'%(index+1))
    for n in created.values():box.addItem(n)
    box.fitAroundContents()
    if focus:
        created['mesh'].setCurrent(True,clear_all_selected=True);created['light'].setDisplayFlag(True)
        network=hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor) if hou.isUIAvailable() else None
        if network:network.setPwd(root);network.setVisibleBounds(hou.BoundingRect(-12 if root.userData('spirula_repair_layout') else -5,-25 if root.userData('spirula_repair_layout') else -17,x+7,7))
    return created


def create(open_studio=True):
    import hou
    root=hou.node('/obj').createNode('geo','SPIRULA_CHAINE');studio=root.createNode('spirula::studio::1.0','01_SPIRULA_PHOTOS',run_init_scripts=False);studio.parm('splatfile').set('$SPIRULA_ROOT/examples/empty.bgeo');studio.parm('workspace').set('$HIP/SpirulaProjets/'+root.name());studio.setPosition(hou.Vector2(0,2));studio.setUserData('spirula_chain_root',root.path());studio.setUserData('spirula_chain_role','studio');studio.setUserData('spirula_chain_branch','0')
    scan=root.createNode('spirula::chain_scan::1.0','02_SCAN_HOUDINI');scan.setInput(0,studio);scan.setPosition(hou.Vector2(0,0));scan.setUserData('spirula_chain_role','scan');scan.setUserData('spirula_chain_branch','0')
    root.setUserData('spirula_chain',json.dumps({'studio':studio.path(),'scan':scan.path(),'branches':[]}));root.setUserData('spirula_chain_auto_studio','1');add_branch(root)
    studio.setComment('01 · Photos dans Spirula\npuis Envoyer vers Houdini');studio.setGenericFlag(hou.nodeFlag.DisplayComment,True);scan.setComment('ÉTAPE 2 · Scan reçu, orientation et échelle.');scan.setGenericFlag(hou.nodeFlag.DisplayComment,False)
    group=studio.parmTemplateGroup()
    for entry in group.entries():
        if entry.name()!='project':entry.hide(True);group.replace(entry.name(),entry)
    project=group.find('project');fields=[]
    for parm in project.parmTemplates():
        if parm.name() not in ('gui','workspace'):parm.hide(True)
        if parm.name()=='gui':parm.setLabel('Ouvrir Spirula · photos vers splat')
        if parm.name()=='workspace':parm.setLabel('Dossier du projet')
        fields.append(parm)
    project.setParmTemplates(fields);project.setLabel('01 · Photos dans Spirula');group.replace('project',project)
    audit=hou.ButtonParmTemplate('chain_audit','Vérifier tout le pipeline');audit.setScriptCallback("import hou,spirula_quality;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_quality.audit(n))");audit.setScriptCallbackLanguage(hou.scriptLanguage.Python);group.insertBefore('project',audit)
    replace=hou.ButtonParmTemplate('chain_replace','Remplacer un objet du scan : créer les étapes de réparation');replace.setScriptCallback("import hou,spirula_replace;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_replace.install(n.creator()))");replace.setScriptCallbackLanguage(hou.scriptLanguage.Python);group.insertBefore('project',replace)
    step=hou.ButtonParmTemplate('chain_next','Scan envoyé : continuer en 02');step.setScriptCallback("import hou,spirula_chain;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_chain.action(n,'next'))");step.setScriptCallbackLanguage(hou.scriptLanguage.Python);group.insertBefore('project',step);studio.setParmTemplateGroup(group)
    source_box=root.createNetworkBox('SCAN_PHOTOS');source_box.setComment('DÉCOR · étapes 01 et 02');source_box.addItem(studio);source_box.addItem(scan);source_box.fitAroundContents()
    note=root.createStickyNote('PARCOURS');note.setText('01 PHOTOS → SPIRULA → ENVOYER VERS HOUDINI\n02 scan à gauche · 03–04 mesh à droite\n05 éclairage → 06 caméras → 07 images → 08 apprentissage\n09 assemblage → 10 export / ajouter un objet\nTout se fait dans ce même Geo.');note.setPosition(hou.Vector2(-4,4));note.setSize(hou.Vector2(13,2.5))
    studio.setCurrent(True,clear_all_selected=True);scan.setDisplayFlag(True);scan.setRenderFlag(True);root.moveToGoodPosition()
    if hou.isUIAvailable():
        for kind in (hou.paneTabType.NetworkEditor,hou.paneTabType.SceneViewer):
            pane=hou.ui.paneTabOfType(kind)
            if pane:pane.setPwd(root)
        network=hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if network:network.setVisibleBounds(hou.BoundingRect(-5,-17,12,7))
        if open_studio:
            import spirula_houdini
            import spirula_tools
            hou.ui.postEventCallback(spirula_tools._guard('ouvrir la fenêtre Spirula Studio',lambda:spirula_houdini.studio(studio)))
    return root


def focus(root,open_studio=False):
    import hou
    if not hou.isUIAvailable():return
    data=config(root)
    for kind in (hou.paneTabType.NetworkEditor,hou.paneTabType.SceneViewer):
        pane=hou.ui.paneTabOfType(kind)
        if pane:pane.setPwd(root)
    network=hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if network:network.setVisibleBounds(hou.BoundingRect(-12 if root.userData('spirula_repair_layout') else -5,-25 if root.userData('spirula_repair_layout') else -17,12+8*(len(data['branches'])-1),7))
    if open_studio:
        import spirula_houdini
        studio=hou.node(data['studio']);studio.setCurrent(True,clear_all_selected=True);spirula_houdini.studio(studio)
