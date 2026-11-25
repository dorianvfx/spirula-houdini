"""A persistent, ordered artist workflow over the render and export engine."""
import hashlib
import json
import time
import uuid
from pathlib import Path

WINDOWS={}


def load(node):
    try:return json.loads(node.userData('spirula_workflow') or '{}')
    except ValueError:return {}


def save(node,state):
    import hou
    from spirula_render import atomic_json
    state.setdefault('project_id',uuid.uuid4().hex)
    state['schema']=1;state['controller']=node.path()
    folder=Path(hou.text.expandString(node.evalParm('workspace')));folder.mkdir(parents=True,exist_ok=True)
    if (folder/'project.json').is_file():
        existing=json.loads((folder/'project.json').read_text(encoding='utf8'))
        if existing.get('project_id')!=state['project_id']:raise ValueError('Ce dossier contient déjà un autre projet. Choisir un nouveau dossier ou Reprendre un projet.')
    node.setUserData('spirula_workflow',json.dumps(state,ensure_ascii=False))
    atomic_json(folder/'project.json',state)


def sources(node):
    import hou
    from spirula_object import sop
    mesh=hou.node(node.evalParm('mesh'));scan=hou.node(node.evalParm('scan'))
    if mesh is None or scan is None:raise ValueError('Choisir un objet 3D et un scan avant de continuer.')
    mesh=sop(mesh);scan=sop(scan)
    if scan.userData('spirula_workflow_wait_for_scan')=='1' and scan.parm('splatfile'):
        if Path(scan.evalParm('splatfile')).name=='demo.ply':raise ValueError('Le Studio affiche encore son exemple. Créer ou ouvrir votre scan, puis cliquer Envoyer vers Houdini avant de continuer.')
    pending=[scan];seen=set()
    while pending:
        current=pending.pop()
        if current.path() in seen:continue
        seen.add(current.path())
        if current==node or current.path().startswith(node.path()+'/'):raise ValueError('Ce décor contient déjà cette insertion. Utiliser Ajouter un autre objet depuis Résultat pour créer une nouvelle insertion.')
        pending.extend(n for n in current.inputs() if n is not None)
        parent=current
        while parent is not None and isinstance(parent,hou.SopNode):
            if parent.type().name()=='spirula::assemble_splats::1.0':pending.extend(n for p in parent.evalParm('sources').split() if (n:=hou.node(p)) is not None)
            parent=parent.parent()
    mesh.cook(force=True);scan.cook(force=True)
    mg=mesh.geometry();sg=scan.geometry()
    if mg is None or not mg.intrinsicValue('pointcount'):raise ValueError('L’objet 3D est vide ou ne peut pas cuire.')
    if mg.findPointAttrib('GS_Alpha'):raise ValueError('Pour l’objet, choisir le mesh avant sa conversion en splat.')
    if sg is None or not sg.intrinsicValue('pointcount'):raise ValueError('Le scan ne peut pas être chargé : '+'; '.join(scan.errors()))
    if not sg.findPointAttrib('GS_Alpha'):raise ValueError('Le scan n’est pas converti en splats natifs : utiliser Importer un scan PLY ou une sortie Bake GSplats.')
    if any(n.path().startswith(node.creator().path()+'/') for n in (mesh,scan)):raise ValueError('Les sources ne peuvent pas dépendre de l’insertion elle-même.')
    return mesh,scan


def signature(node):
    """Stable across HIP reloads; geometry, placement, materials and look settings."""
    import hou
    mesh,scan=sources(node);digest=hashlib.sha256();materials=set()
    for source in (mesh,scan):
        geo=source.geometry();digest.update(source.path().encode());digest.update(str(source.creator().worldTransform().asTuple()).encode())
        digest.update(str((geo.intrinsicValue('pointcount'),geo.intrinsicValue('primitivecount'))).encode())
        digest.update(str((tuple(geo.boundingBox().minvec()),tuple(geo.boundingBox().maxvec()))).encode())
        for name in ('P','N','Cd','uv','scale','pscale','orient','restorient','GS_Alpha','GS_SPH_R','GS_SPH_G','GS_SPH_B'):
            if geo.findPointAttrib(name):digest.update(geo.pointFloatAttribValuesAsString(name))
        for name in ('uv','N','Cd'):
            if geo.findVertexAttrib(name):digest.update(geo.vertexFloatAttribValuesAsString(name))
        if geo.findPrimAttrib('shop_materialpath'):materials.update(geo.primStringAttribValues('shop_materialpath'))
        if source.creator().parm('shop_materialpath'):materials.add(source.creator().evalParm('shop_materialpath'))
        # Include upstream parameters (including packed-file references) without
        # depending on volatile Houdini geometry data IDs.
        upstream=[source];seen=set()
        while upstream:
            current=upstream.pop()
            if current.path() in seen:continue
            seen.add(current.path());upstream.extend(n for n in current.inputs() if n is not None)
            digest.update(current.type().name().encode())
            for parm in current.parms():
                if parm.name() in ('status','jobfile','activity','elapsed','progress','running','workspace','exportfile'):continue
                try:
                    value=parm.evalAsString();digest.update((parm.name()+':'+value).encode('utf8'));asset=Path(value)
                    if asset.is_file():stat=asset.stat();digest.update(str((stat.st_size,stat.st_mtime_ns)).encode())
                except (hou.Error,OSError,ValueError):pass
    for path in sorted(materials):
        material=hou.node(path) if path else None
        if material is None:continue
        for current in (material,)+material.allSubChildren():
            for parm in current.parms():
                try:
                    value=parm.evalAsString();digest.update((parm.path()+':'+value).encode('utf8'))
                    asset=Path(value)
                    if asset.is_file():stat=asset.stat();digest.update(str((stat.st_size,stat.st_mtime_ns)).encode())
                except (hou.Error,OSError,ValueError):pass
    digest.update(str(hou.frame()).encode())
    digest.update(str(node.creator().worldTransform().asTuple()).encode())
    digest.update(json.dumps({p:node.evalParm(p) for p in ('quality','exposure','detail','max_views')},sort_keys=True).encode())
    return digest.hexdigest()


def checkpoint(node,state):
    import hou
    folder=Path(hou.text.expandString(node.evalParm('workspace')));folder.mkdir(parents=True,exist_ok=True)
    original=hou.hipFile.name();hip=hou.getenv('HIP');state['original_hip_directory']=hip
    scene_folder=folder/'scene';scene_folder.mkdir(exist_ok=True);state['scene']=str(scene_folder/Path(original).name)
    save(node,state)
    try:hou.hipFile.save(state['scene'],save_to_recent_files=False)
    finally:hou.hipFile.setName(original);hou.putenv('HIP',hip)


def request(node,kind):
    import spirula_insert
    import spirula_render,spirula_monitor
    capture=node.node('CAPTURE');state=load(node);sig=signature(node)
    if capture.sessionId() in spirula_render.JOBS or capture.sessionId() in spirula_monitor.PENDING:raise ValueError('Un calcul est déjà actif pour ce projet. Ouvrir le suivi.')
    if kind=='train' and state.get('approved_signature')!=sig:raise ValueError('Le placement ou les réglages ont changé. Calculer puis valider un nouvel aperçu à l’étape Éclairage.')
    if kind=='train' and state.get('result_signature')==sig and Path(state.get('result','')).is_file():return spirula_monitor.launch(capture,lambda:export(node),'Résultat existant valide : export sans réentraînement…')
    state.update(request_signature=sig,request_kind=kind)
    if kind=='train':state.pop('export',None);state.pop('result_signature',None)
    checkpoint(node,state)
    capture.setUserData('spirula_workflow_request',json.dumps({'controller':node.path(),'signature':sig,'kind':kind}))
    return spirula_insert.simple_callback(node,'preview' if kind=='preview' else 'start')


def job_started(capture,config,data):
    import hou
    request=data.get('workflow')
    if not request:return
    node=hou.node(request['controller'])
    if node is None:return
    state=load(node);state['preview_job' if request['kind']=='preview' else 'training_job']=str(config)
    if request['kind']=='train':state['training_signature']=request['signature']
    save(node,state)


def completed(capture,result,data):
    import hou
    request=data.get('workflow')
    if not request or result.get('phase')!='done':return
    node=hou.node(request['controller'])
    if node is None:return
    state=load(node);sig=request['signature'];state['last_message']=result.get('message','')
    if sig!=signature(node):
        state['last_message']='Les sources ont changé pendant le calcul. Le cache est conservé ; revenir à Placement et recalculer l’aperçu.';save(node,state);return
    if request['kind']=='preview':state['preview_signature']=sig
    elif result.get('result'):
        state.update(result_signature=sig,result=result['result'],result_transform=data.get('output_transform',[]))
    save(node,state)
    if request['kind']=='train' and state.get('result_signature')==sig:
        export(node)


def export(node):
    import msvcrt
    folder=Path(node.evalParm('exportfile')).parent;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.spirula_export.lock').open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise ValueError('Un export est déjà en cours dans ce dossier. Attendre sa fin, puis réexporter le résultat calculé.')
        try:return _export(node)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


def _export(node):
    import hou
    import spirula_scene,spirula_monitor
    state=load(node)
    if state.get('result_signature')!=signature(node):raise ValueError('La génération ne correspond plus aux sources actuelles. Repasser par l’aperçu puis la génération.')
    capture=node.node('CAPTURE');key=capture.sessionId();started=time.time()
    status={'phase':'exporting','message':'Assemblage et export automatique de la scène…','active':True,'started':started}
    spirula_monitor.OVERRIDES[key]=status;spirula_monitor.update_node(capture,status);capture.parm('status').set(status['message'])
    mesh,scan=sources(node);assembly=hou.node(state.get('composition',''))
    if assembly is None:
        assembly=spirula_scene.assemble([scan,node]);state['composition']=assembly.path()
    assembly.parm('exportfile').set(node.evalParm('exportfile'));report=spirula_scene.export(assembly)
    assembly.creator().setDisplayFlag(True);node.creator().setDisplayFlag(False)
    for source in (mesh,scan):
        if source.creator()!=assembly.creator():source.creator().setDisplayFlag(False)
    state['export']=report;state['last_message']='Scène prête : '+report['file'];save(node,state)
    status.update(phase='done',message=state['last_message'],active=False,finished=time.time());spirula_monitor.OVERRIDES[key]=status;spirula_monitor.update_node(capture,status);capture.parm('status').set(status['message'])
    return report


def blank():
    import hou
    obj=hou.node('/obj').createNode('geo','SPIRULA_PIPELINE');node=obj.createNode('spirula::insert_asset::1.0','PIPELINE')
    identifier=uuid.uuid4().hex[:8]
    if Path(hou.hipFile.name()).name.lower().startswith('untitled'):folder=Path.home()/'Documents'/'SpirulaProjects'/identifier
    else:folder=Path(hou.hipFile.path()).parent/'SpirulaProjects'/identifier
    node.parm('workspace').set(str(folder));node.parm('exportfile').set(str(folder/'03_exports'/'Scene_finale.ply'));obj.moveToGoodPosition()
    return node


def restore_project(path):
    import hou
    state=json.loads(Path(path).read_text(encoding='utf8'));scene=state.get('scene')
    if not scene or not Path(scene).is_file():raise ValueError('Le snapshot de ce projet est introuvable.')
    hou.hipFile.load(scene,suppress_save_prompt=True,ignore_load_warnings=True);hou.putenv('HIP',state['original_hip_directory']);node=hou.node(state['controller'])
    if node is None:raise ValueError('Le contrôleur du projet est introuvable dans sa scène.')
    node.parm('workspace').set(str(Path(path).parent));save(node,state)
    if state.get('training_job') or state.get('preview_job'):node.node('CAPTURE').parm('jobfile').set(state.get('training_job') or state['preview_job'])
    if state.get('result') and Path(state['result']).is_file():
        capture=node.node('CAPTURE');capture.parm('splatfile').set(state['result']);capture.parm('result_transform').set(json.dumps(state.get('result_transform',[])));capture.node('read_splat').parm('reload').pressButton();capture.cook(force=True)
        if hou.node(state.get('composition','')) is None:
            import spirula_scene
            _,scan=sources(node);assembly=spirula_scene.assemble([scan,node]);state['composition']=assembly.path();save(node,state)
    return node


def hydrate(node):
    """A normally opened HIP can catch up with its latest project manifest."""
    import hou
    import spirula_render
    state=load(node);path=Path(node.evalParm('workspace'))/'project.json'
    if not path.is_file() or not state.get('project_id') or node.node('CAPTURE').sessionId() in spirula_render.JOBS:return
    latest=json.loads(path.read_text(encoding='utf8'))
    if latest.get('project_id')!=state['project_id']:return
    node.setUserData('spirula_workflow',json.dumps(latest,ensure_ascii=False))
    if latest.get('training_job') or latest.get('preview_job'):node.node('CAPTURE').parm('jobfile').set(latest.get('training_job') or latest['preview_job'])
    if latest.get('original_hip_directory'):hou.putenv('HIP',latest['original_hip_directory'])
    if latest.get('result') and Path(latest['result']).is_file():
        capture=node.node('CAPTURE');capture.parm('splatfile').set(latest['result']);capture.parm('result_transform').set(json.dumps(latest.get('result_transform',[])));capture.node('read_splat').parm('reload').pressButton();capture.cook(force=True)
        if hou.node(latest.get('composition','')) is None:
            import spirula_scene
            _,scan=sources(node);composition=spirula_scene.assemble([scan,node]);latest['composition']=composition.path();save(node,latest)


def open(node=None):
    import hou
    from PySide6 import QtWidgets,QtCore,QtGui
    if node is None:
        selected=hou.selectedNodes();node=next((n for n in selected if n.type().name()=='spirula::insert_asset::1.0'),None)
        if node is None:
            from spirula_object import sop
            candidates=[]
            for n in selected:
                try:candidates.append(sop(n))
                except ValueError:pass
            node=blank()
            for candidate in candidates:
                geo=candidate.geometry()
                if geo is not None:node.parm('scan' if geo.findPointAttrib('GS_Alpha') else 'mesh').set(candidate.path())
    key=node.path();existing=WINDOWS.get(key)
    if existing:
        try:existing.show();existing.raise_();return existing
        except RuntimeError:WINDOWS.pop(key,None)
    hydrate(node)
    for other in hou.node('/obj').allSubChildren():
        if other.type().name()=='spirula::insert_asset::1.0':other.setUserData('spirula_workflow_auto','0')
    node.setUserData('spirula_workflow_auto','1');node.setCurrent(True,clear_all_selected=True)

    class Page(QtWidgets.QWizardPage):
        def __init__(self,wizard,index,title,description):
            super().__init__();self.wizard=wizard;self.index=index;self.setTitle(title);self.setSubTitle(description);self.box=QtWidgets.QVBoxLayout(self);self.route=QtWidgets.QLabel();self.route.setWordWrap(True);self.box.addWidget(self.route)
        def validatePage(self):
            if self.index==4:return True
            if self.wizard.verified_step==self.index:self.wizard.verified_step=None;return True
            self.wizard.advance(self.index);return False

    class Workflow(QtWidgets.QWizard):
        def __init__(self):
            super().__init__(hou.qt.mainWindow());self.node=node;self.verified_step=None;self.validating=False;self.setWindowTitle('Spirula Pipeline');self.resize(880,740);self.setWizardStyle(QtWidgets.QWizard.WizardStyle.ModernStyle)
            self.setButtonText(QtWidgets.QWizard.WizardButton.BackButton,'Précédent');self.setButtonText(QtWidgets.QWizard.WizardButton.NextButton,'Continuer');self.setButtonText(QtWidgets.QWizard.WizardButton.FinishButton,'Terminer');self.setButtonText(QtWidgets.QWizard.WizardButton.CancelButton,'Fermer')
            self.setOption(QtWidgets.QWizard.WizardOption.NoBackButtonOnStartPage)
            self.setOption(QtWidgets.QWizard.WizardOption.HaveCustomButton1)
            self.setButtonText(QtWidgets.QWizard.WizardButton.CustomButton1,'Revoir la configuration')
            self.customButtonClicked.connect(lambda *_:(self.setStartId(0),self.restart()))
            self.pages=[];self.image_signature=None
            titles=[('1 / 5 · Scan et objet','Choisir le décor capturé et le mesh à ajouter. Le projet conserve les calculs et les exports.'),('2 / 5 · Placement','Placer le mesh dans la scène avec les outils Houdini, puis continuer.'),('3 / 5 · Éclairage','Calculer un aperçu, vérifier son éclairage, puis valider pour continuer.'),('4 / 5 · Génération','Un seul calcul : rendus → Spirula → chargement Houdini → export de la scène.'),('5 / 5 · Résultat','Le PLY final contient le décor et l’objet. Les sources et les calculs restent disponibles.')]
            for i,(title,text) in enumerate(titles):page=Page(self,i,title,text);self.pages.append(page);self.addPage(page)
            self.error=QtWidgets.QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#edb889;padding:6px;')
            self.setSideWidget(self.error)
            p=self.pages[0];form=QtWidgets.QFormLayout();p.box.addLayout(form)
            self.workspace=QtWidgets.QLineEdit(node.evalParm('workspace'));row=QtWidgets.QHBoxLayout();row.addWidget(self.workspace);button=QtWidgets.QPushButton('Choisir…');button.clicked.connect(self.choose_workspace);row.addWidget(button);form.addRow('Dossier du projet',row)
            self.scan=self.source_field(form,'Scan Gaussian splat','scan');self.mesh=self.source_field(form,'Objet 3D','mesh')
            buttons=QtWidgets.QHBoxLayout();p.box.addLayout(buttons)
            for label,fn in [('Importer un scan PLY…',self.import_scan),('Créer un scan dans Studio',self.studio),('Reprendre un projet…',self.restore)]:b=QtWidgets.QPushButton(label);b.clicked.connect(lambda _=False,fn=fn:hou.ui.postEventCallback(fn));buttons.addWidget(b)
            self.source_info=QtWidgets.QLabel('Sélectionner un objet dans Houdini, puis Utiliser la sélection.');self.source_info.setWordWrap(True);p.box.addWidget(self.source_info);p.box.addStretch()
            p=self.pages[1];self.placement_info=QtWidgets.QLabel();self.placement_info.setWordWrap(True);p.box.addWidget(self.placement_info)
            for label,fn in [('Sélectionner le mesh et afficher ses poignées',self.select_mesh),('Cadrer le mesh dans le viewport',self.frame),('Afficher le décor et le mesh',self.show_sources)]:b=QtWidgets.QPushButton(label);b.clicked.connect(lambda _=False,fn=fn:hou.ui.postEventCallback(fn));p.box.addWidget(b)
            p.box.addWidget(QtWidgets.QLabel('Vous pouvez déplacer, tourner et redimensionner l’OBJ source. Les caméras suivront sa taille.'));p.box.addStretch()
            p=self.pages[2];form=QtWidgets.QFormLayout();p.box.addLayout(form)
            self.quality=QtWidgets.QComboBox();self.quality.addItems(['Haute qualité','Production détaillée']);self.quality.setCurrentIndex(max(0,node.evalParm('quality')-1));form.addRow('Qualité finale',self.quality)
            self.exposure=QtWidgets.QDoubleSpinBox();self.exposure.setRange(-12,12);self.exposure.setSingleStep(.5);self.exposure.setValue(node.evalParm('exposure'));form.addRow('Exposition',self.exposure)
            self.detail=QtWidgets.QDoubleSpinBox();self.detail.setDecimals(5);self.detail.setRange(0,10000);self.detail.setValue(node.evalParm('detail'));self.detail.setSpecialValueText('Tour automatique de l’objet');form.addRow('Façades : unités / pixel (0 = auto)',self.detail)
            self.preview_button=QtWidgets.QPushButton('Calculer / actualiser l’aperçu');self.preview_button.clicked.connect(lambda:self.run('preview'));p.box.addWidget(self.preview_button)
            self.preview=QtWidgets.QLabel('L’aperçu calculé apparaîtra ici.');self.preview.setMinimumHeight(270);self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);self.preview.setStyleSheet('background:#353535;');p.box.addWidget(self.preview,1)
            self.preview_info=QtWidgets.QLabel();self.preview_info.setWordWrap(True);p.box.addWidget(self.preview_info)
            p=self.pages[3];self.summary=QtWidgets.QLabel();self.summary.setWordWrap(True);p.box.addWidget(self.summary)
            form=QtWidgets.QFormLayout();p.box.addLayout(form);self.output=QtWidgets.QLineEdit(node.evalParm('exportfile'));self.output_auto=not bool(load(node).get('export'));self.output.textEdited.connect(lambda *_:setattr(self,'output_auto',False));form.addRow('PLY final décor + objet',self.output)
            self.build_button=QtWidgets.QPushButton('Générer et exporter la scène');self.build_button.clicked.connect(lambda:self.run('train'));p.box.addWidget(self.build_button)
            row=QtWidgets.QHBoxLayout();p.box.addLayout(row)
            for label,fn in [('Suivi en direct',self.monitor),('Reprendre ce calcul',self.resume),('Arrêter',self.stop)]:b=QtWidgets.QPushButton(label);b.clicked.connect(lambda _=False,fn=fn:hou.ui.postEventCallback(fn));row.addWidget(b)
            self.generation_info=QtWidgets.QLabel();self.generation_info.setWordWrap(True);p.box.addWidget(self.generation_info);p.box.addStretch()
            p=self.pages[4];self.result_info=QtWidgets.QLabel();self.result_info.setWordWrap(True);self.result_info.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse);p.box.addWidget(self.result_info)
            for label,fn in [('Voir la composition dans Houdini',self.show_result),('Ouvrir le dossier de sortie',self.folder),('Ajouter un autre objet à cette scène',self.add_object),('Réexporter la scène',self.reexport)]:b=QtWidgets.QPushButton(label);b.clicked.connect(lambda _=False,fn=fn:hou.ui.postEventCallback(fn));p.box.addWidget(b)
            p.box.addStretch();self.currentIdChanged.connect(self.changed)
            state=load(node)
            start=4 if state.get('export') and Path(state['export']['file']).is_file() else 3 if state.get('approved_signature') else 2 if state.get('placement_signature') else 1 if state.get('sources_validated') else 0
            self.setStartId(start)
            self.timer=QtCore.QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
            self.finished.connect(lambda *_:(self.timer.stop(),WINDOWS.pop(key,None)))

        def source_field(self,form,label,name):
            edit=QtWidgets.QLineEdit(node.evalParm(name));row=QtWidgets.QHBoxLayout();row.addWidget(edit);button=QtWidgets.QPushButton('Utiliser la sélection');button.clicked.connect(lambda:self.pick(edit,name));row.addWidget(button);form.addRow(label,row);return edit
        def fail(self,exc):self.error.setText(str(exc));return False
        def pick(self,edit,name):
            try:
                from spirula_object import sop
                selected=[n for n in hou.selectedNodes() if n!=node]
                if not selected:raise ValueError('Sélectionner d’abord un objet ou un SOP dans Houdini.')
                source=sop(selected[0]);edit.setText(source.path());self.error.clear()
            except Exception as exc:self.fail(exc)
        def choose_workspace(self):
            path=QtWidgets.QFileDialog.getExistingDirectory(self,'Dossier du projet',self.workspace.text())
            if path:self.workspace.setText(path)
        def apply(self):
            if self.output_auto and self.workspace.text().strip()!=node.evalParm('workspace'):self.output.setText(str(Path(hou.text.expandString(self.workspace.text().strip()))/'03_exports'/'Scene_finale.ply'))
            for name,value in [('mesh',self.mesh.text().strip()),('scan',self.scan.text().strip()),('workspace',self.workspace.text().strip()),('quality',self.quality.currentIndex()+1),('exposure',self.exposure.value()),('detail',self.detail.value()),('exportfile',self.output.text().strip())]:node.parm(name).set(value)
        def advance(self,index):
            if self.validating:return
            self.validating=True;self.currentPage().setSubTitle('Vérification et sauvegarde du projet…');self.refresh()
            def check():
                try:
                    valid=self.validate_step(index)
                    if valid:self.verified_step=index;self.next()
                finally:self.validating=False;self.refresh()
            hou.ui.postEventCallback(check)
        def validate_step(self,index):
            try:
                self.apply();mesh,scan=sources(node);state=load(node)
                if index==0:
                    folder=Path(node.evalParm('workspace'))
                    if not self.workspace.text().strip():raise ValueError('Choisir un dossier de projet.')
                    from spirula_transform import bounding_box
                    node.creator().setWorldTransform(hou.hmath.buildTranslate(bounding_box(mesh.geometry(),mesh.creator().worldTransform()).center()))
                    node.creator().setDisplayFlag(False);mesh.creator().setDisplayFlag(True);scan.creator().setDisplayFlag(True)
                    old_composition=hou.node(state.get('composition',''))
                    if old_composition:old_composition.creator().setDisplayFlag(False)
                    folder.mkdir(parents=True,exist_ok=True);state['sources_validated']=True;checkpoint(node,state)
                    self.source_info.setText('Scan : %s gaussiennes · Objet : %s points.'%(scan.geometry().intrinsicValue('pointcount'),mesh.geometry().intrinsicValue('pointcount')))
                if index==1:state['placement_signature']=signature(node);checkpoint(node,state)
                if index==2:
                    sig=signature(node)
                    if state.get('preview_signature')!=sig:raise ValueError('Calculer un aperçu avec le placement et les réglages actuels avant de valider l’éclairage.')
                    state['approved_signature']=sig;save(node,state)
                if index==3:
                    if not state.get('export') or not Path(state['export']['file']).is_file() or state.get('result_signature')!=signature(node):raise ValueError('Attendre la génération et l’export de la scène avant de passer au résultat.')
                self.error.clear();return True
            except Exception as exc:return self.fail(exc)
        def changed(self,index):
            self.setButtonText(QtWidgets.QWizard.WizardButton.NextButton,'Valider l’éclairage' if index==2 else 'Continuer');self.error.clear()
            names=['Scan et objet','Placement','Éclairage','Génération','Résultat']
            for page in self.pages:page.route.setText(' → '.join('<b style="color:#eabd6c">'+name+'</b>' if i==index else name for i,name in enumerate(names)))
            self.refresh()
        def run(self,kind):
            if self.validating:return
            if node.evalParm('running'):self.fail('Le calcul actuel est encore actif. Ouvrir le suivi ou attendre sa fin.');return
            import spirula_monitor
            capture=node.node('CAPTURE');key=capture.sessionId();started=time.time()
            pending={'phase':'pending','message':'Vérification des sources et sauvegarde du projet…','active':True,'started':started}
            spirula_monitor.OVERRIDES[key]=pending;spirula_monitor.update_node(capture,pending);capture.parm('status').set(pending['message']);spirula_monitor.show(capture)
            self.validating=True;self.refresh()
            def start():
                try:
                    self.apply();request(node,kind);self.error.clear()
                except Exception as exc:
                    failed={'phase':'failed','message':str(exc),'active':False,'started':started,'finished':time.time()};spirula_monitor.OVERRIDES[key]=failed;spirula_monitor.update_node(capture,failed);capture.parm('status').set(str(exc));self.fail(exc)
                finally:self.validating=False;self.refresh()
            QtCore.QTimer.singleShot(75,lambda:hou.ui.postEventCallback(start))
        def monitor(self):
            import spirula_monitor
            spirula_monitor.show(node.node('CAPTURE'))
        def resume(self):
            try:
                state=load(node);path=state.get('training_job')
                if not path:raise ValueError('Aucun calcul de génération à reprendre dans ce projet.')
                expected=state.get('training_signature') or json.loads(Path(path).read_text(encoding='utf8')).get('workflow',{}).get('signature')
                if expected!=signature(node):raise ValueError('Les sources ou réglages diffèrent de ce calcul. Revenir à l’aperçu pour démarrer une nouvelle génération.')
                node.node('CAPTURE').parm('jobfile').set(path)
                import spirula_insert
                spirula_insert.simple_callback(node,'resume')
            except Exception as exc:self.fail(exc)
        def stop(self):
            import spirula_render
            try:spirula_render.stop(node.node('CAPTURE'))
            except Exception as exc:self.fail(exc)
        def select_mesh(self):
            try:
                mesh,_=sources(node);mesh.creator().setDisplayFlag(True);mesh.creator().setCurrent(True,clear_all_selected=True)
                viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                if viewer:viewer.setPwd(hou.node('/obj'));viewer.setCurrentState('xform')
            except Exception as exc:self.fail(exc)
        def frame(self):
            try:
                from spirula_transform import bounding_box
                mesh,_=sources(node);viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                if viewer:viewer.setPwd(hou.node('/obj'));viewer.curViewport().frameBoundingBox(bounding_box(mesh.geometry(),mesh.creator().worldTransform()))
            except Exception as exc:self.fail(exc)
        def show_sources(self):
            try:
                mesh,scan=sources(node);mesh.creator().setDisplayFlag(True);scan.creator().setDisplayFlag(True)
            except Exception as exc:self.fail(exc)
        def import_scan(self):
            path,_=QtWidgets.QFileDialog.getOpenFileName(self,'Importer le scan','','Gaussian splats (*.ply *.bgeo *.bgeo.sc)')
            if not path:return
            try:
                obj=hou.node('/obj').createNode('geo','SPIRULA_SCAN');read=obj.createNode('file','SOURCE');read.parm('file').set(path)
                if read.geometry().findPointAttrib('GS_Alpha'):bake=read
                else:bake=obj.createNode('bakegsplat','SCAN');bake.setInput(0,read);bake.parm('sphcoeff').set(1)
                bake.setDisplayFlag(True);bake.setRenderFlag(True);obj.layoutChildren();self.scan.setText(bake.path())
            except Exception as exc:self.fail(exc)
        def studio(self):
            import spirula_houdini
            for selected in hou.selectedNodes():selected.setSelected(False)
            studio=spirula_houdini.create();studio.setUserData('spirula_workflow_wait_for_scan','1');self.scan.setText(studio.path());self.source_info.setText('Créer ou ouvrir le scan dans Studio, puis Envoyer vers Houdini. Revenir ensuite ici et Continuer.')
        def restore(self):
            path,_=QtWidgets.QFileDialog.getOpenFileName(self,'Reprendre un projet Spirula','','Projet Spirula (project.json)')
            if not path:return
            try:
                state=json.loads(Path(path).read_text(encoding='utf8'));scene=state.get('scene')
                if not scene or not Path(scene).is_file():raise ValueError('Le snapshot de ce projet est introuvable.')
                if hou.hipFile.hasUnsavedChanges() and hou.ui.displayMessage('Enregistrer les changements de la scène actuelle avant d’ouvrir ce projet ?',buttons=('Enregistrer','Annuler'),default_choice=0,close_choice=1)!=0:return
                if hou.hipFile.hasUnsavedChanges():hou.hipFile.save()
                self.close();restored=restore_project(path);open(restored)
            except Exception as exc:self.fail(exc)
        def show_result(self):
            state=load(node);composition=hou.node(state.get('composition',''))
            if composition:composition.creator().setDisplayFlag(True);composition.setCurrent(True,clear_all_selected=True)
        def add_object(self):
            try:
                composition=hou.node(load(node).get('composition',''))
                if composition is None:raise ValueError('La composition doit être générée avant d’ajouter un autre objet.')
                next_node=blank();next_node.parm('scan').set(composition.path());self.close();open(next_node)
            except Exception as exc:self.fail(exc)
        def folder(self):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            state=load(node);path=Path(state['export']['file']).parent if state.get('export') else Path(node.evalParm('workspace'));QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        def reexport(self):
            try:self.apply();export(node);self.refresh()
            except Exception as exc:self.fail(exc)
        def refresh(self):
            try:
                state=load(node);capture=node.node('CAPTURE');active=bool(node.evalParm('running')) or self.validating;self.preview_button.setEnabled(not active);self.build_button.setEnabled(not active)
                import spirula_monitor
                tracked,_,_=spirula_monitor.snapshot(capture)
                if tracked.get('active'):
                    spirula_monitor.update_node(capture,tracked);capture.parm('status').set(tracked.get('message','Calcul en cours…'));active=True
                elif not self.validating and not tracked.get('active') and node.evalParm('running'):
                    spirula_monitor.update_node(capture,tracked);active=False
                self.preview_button.setEnabled(not active);self.build_button.setEnabled(not active)
                for widget in (self.workspace,self.scan,self.mesh,self.quality,self.exposure,self.detail,self.output):widget.setEnabled(not active)
                self.button(QtWidgets.QWizard.WizardButton.BackButton).setEnabled(not active)
                self.button(QtWidgets.QWizard.WizardButton.CustomButton1).setEnabled(not active);self.button(QtWidgets.QWizard.WizardButton.CustomButton1).setVisible(self.currentId()>0)
                ready=not active
                dirty=(self.quality.currentIndex()+1!=node.evalParm('quality') or self.exposure.value()!=node.evalParm('exposure') or self.detail.value()!=node.evalParm('detail'))
                if self.currentId()==2:ready=ready and bool(state.get('preview_signature')) and not dirty
                if self.currentId()==3:ready=ready and bool(state.get('export')) and Path(state['export']['file']).is_file()
                self.button(QtWidgets.QWizard.WizardButton.NextButton).setEnabled(ready)
                if self.currentId()==3:self.setButtonText(QtWidgets.QWizard.WizardButton.NextButton,'Afficher la scène finale' if ready else 'Calcul en cours…' if active else 'En attente de génération')
                self.placement_info.setText('Mesh : '+node.evalParm('mesh')+'\nDécor : '+node.evalParm('scan')+'\nLe placement est incorporé lors des rendus ; les sources restent éditables.')
                self.summary.setText(('Production détaillée · 2048² · 40 000 itérations' if self.quality.currentIndex()==1 else 'Haute qualité · 1536² · 30 000 itérations')+'\nLes vues sont générées selon le cadrage choisi. Le suivi affiche chaque étape.\nL’assemblage et l’export s’enchaînent après le chargement du splat.')
                self.generation_info.setText(capture.evalParm('status')+'\n'+state.get('last_message',''))
                preview_job=state.get('preview_job')
                if preview_job:
                    images=list((Path(preview_job).parent/'images').glob('*.png'))
                    if images:
                        image=images[0];key=(str(image),image.stat().st_mtime_ns)
                        if key!=self.image_signature:self.preview.setPixmap(QtGui.QPixmap(str(image)).scaled(650,330,QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation));self.image_signature=key
                self.preview_info.setText('Aperçu calculé. Vérifier l’image puis Valider l’éclairage.' if state.get('preview_signature') and not dirty else 'Calculer un aperçu avant de continuer. Les réglages modifiés nécessitent un nouvel aperçu.')
                result=state.get('export');self.result_info.setText('Scène exportée :\n'+result['file']+'\n%s gaussiennes'%result['gaussians'] if result else 'La scène finale apparaîtra ici après la génération et l’export.')
            except hou.ObjectWasDeleted:self.timer.stop();self.error.setText('Ce contrôleur a été supprimé.')
        def closeEvent(self,event):self.timer.stop();WINDOWS.pop(key,None);super().closeEvent(event)

    dialog=Workflow();WINDOWS[key]=dialog;dialog.show();return dialog
