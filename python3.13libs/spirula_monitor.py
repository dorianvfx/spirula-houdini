"""Live, non-modal Houdini feedback for render-to-splat jobs."""
import json
import re
import time
from pathlib import Path

WINDOWS={}
PENDING={}
OVERRIDES={}
PHASES={'pending':'Préparation de la demande','queued':'Démarrage du worker','loading':'Chargement de la scène','lighting':'Construction du champ lumineux','rendering':'Rendu Karma','training':'Génération du splat','finishing':'Finalisation du worker','importing':'Import dans Houdini','exporting':'Export / compression','done':'Terminé','failed':'Échec','cancelled':'Arrêté'}


def tail(path,limit=24000):
    try:
        with Path(path).open('rb') as f:
            f.seek(max(0,Path(path).stat().st_size-limit));return f.read().decode('utf8',errors='replace')
    except OSError:return ''


def owner(node):
    if node.userData('spirula_refine_owner'):
        import hou
        stage=hou.node(node.userData('spirula_refine_owner'))
        if stage is not None:return stage
    if node.userData('spirula_arch_active_stage'):
        import hou
        stage=hou.node(node.userData('spirula_arch_active_stage'))
        if stage is not None:return stage
    if node.userData('spirula_chain_active_stage'):
        import hou
        stage=hou.node(node.userData('spirula_chain_active_stage'))
        if stage is not None:return stage
        if node.userData('spirula_chain_active_role'):
            import spirula_chain
            stage=spirula_chain.nodes(node.parent()).get(node.userData('spirula_chain_active_role'))
            if stage is not None:return stage
    parent=node.parent()
    return parent if parent.type().name()=='spirula::insert_asset::1.0' else node


def duration(seconds):
    seconds=max(0,int(seconds));return '%02d:%02d:%02d'%(seconds//3600,(seconds//60)%60,seconds%60)


def snapshot(node):
    import spirula_render as render
    key=node.sessionId();pending=PENDING.get(key)
    if pending:return dict(phase='pending',message=pending['message'],started=pending['started'],active=True),None,{}
    if key in OVERRIDES:return OVERRIDES[key],None,{}
    config=Path(node.evalParm('jobfile'))
    try:
        data=json.loads(config.read_text(encoding='utf8'));folder=Path(data['folder']);state=json.loads((folder/'status.json').read_text(encoding='utf8'))
    except (OSError,ValueError,TypeError):return {'phase':'idle','message':node.evalParm('status'),'active':False},None,{}
    job=render.JOBS.get(key);state['active']=bool(job and job['process'].poll() is None)
    state.setdefault('started',data.get('started',config.stat().st_mtime))
    if state.get('phase') in ('done','failed','cancelled'):state.setdefault('finished',state.get('updated',(folder/'status.json').stat().st_mtime))
    if job:state['worker_pid']=job['process'].pid
    if state.get('phase')=='done' and job:
        if state['active']:state.update(phase='finishing',message='Résultat écrit ; fermeture du worker avant le retour dans Houdini…')
        elif state.get('result'):state.update(phase='importing',message='Résultat disponible ; préparation de l’import Houdini…')
    if not state['active'] and state.get('worker_pid') and state.get('phase') not in ('done','failed','cancelled'):
        try:
            import psutil
            if not psutil.pid_exists(int(state['worker_pid'])):state.update(phase='failed',message='Le worker est arrêté sans résultat final. Voir le journal ou reprendre le calcul.')
            else:
                process=psutil.Process(int(state['worker_pid']))
                if 'hython' in process.name().lower() and abs(process.create_time()-state['started'])<180:state['active']=True
        except ImportError:pass
    if (folder/'cancel.request').exists() and state.get('phase') not in ('done','failed','cancelled'):state['cancel_requested']=True
    return state,folder,data


def update_node(node,state):
    import hou
    n=owner(node);phase=state.get('phase','idle');message=state.get('message','')
    if (node.userData('spirula_chain_active_stage') or node.userData('spirula_arch_active_stage') or node.userData('spirula_refine_owner')) and n.parm('status'):n.parm('status').set(message)
    progress=state.get('frame_progress')
    if phase=='training' and state.get('steps'):progress=100*state.get('step',0)/state['steps']
    if phase=='done':progress=100
    for name,value in [('activity',PHASES.get(phase,'Prêt')),('elapsed',duration((state.get('finished') or time.time())-state.get('started',time.time()))),('progress',progress or 0),('running',int(bool(state.get('active'))))]:
        p=n.parm(name)
        if p is not None:p.set(value)
    label=PHASES.get(phase,'Prêt')+' · '+message
    if state.get('cancel_requested'):label='Arrêt demandé après cette image · '+label
    n.setComment(label[:240]);n.setGenericFlag(hou.nodeFlag.DisplayComment,True)
    if hou.isUIAvailable() and state.get('active'):hou.ui.setStatusMessage(label[:200])


def show(node):
    import hou
    if not hou.isUIAvailable():return None
    from PySide6 import QtWidgets,QtCore,QtGui
    key=node.sessionId();existing=WINDOWS.get(key)
    if existing is not None:
        try:existing.show();existing.raise_();existing.activateWindow();return existing
        except RuntimeError:WINDOWS.pop(key,None)

    class Monitor(QtWidgets.QDialog):
        def __init__(self):
            super().__init__(hou.qt.mainWindow());self.node=node;self.config=None;self.last_image=None;self.processes={};self.log_signature=None
            self.setWindowTitle('Spirula · Suivi du calcul');self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);self.resize(850,820)
            layout=QtWidgets.QVBoxLayout(self)
            self.title=QtWidgets.QLabel();self.title.setStyleSheet('font-size:20px;font-weight:bold;padding:6px;');layout.addWidget(self.title)
            self.message=QtWidgets.QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
            self.bar=QtWidgets.QProgressBar();layout.addWidget(self.bar)
            self.count=QtWidgets.QLabel();layout.addWidget(self.count)
            self.activity=QtWidgets.QLabel();self.activity.setWordWrap(True);layout.addWidget(self.activity)
            tabs=QtWidgets.QTabWidget();layout.addWidget(tabs,1)
            image_tab=QtWidgets.QWidget();image_layout=QtWidgets.QVBoxLayout(image_tab)
            self.image=QtWidgets.QLabel('La première image apparaîtra ici dès que Karma aura enregistré un aperçu.');self.image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);self.image.setMinimumSize(400,300);self.image.setStyleSheet('background:#353535;');self.image.setWordWrap(True);image_layout.addWidget(self.image,1)
            self.image_info=QtWidgets.QLabel();image_layout.addWidget(self.image_info);tabs.addTab(image_tab,'Rendu en cours / dernière image')
            self.log=QtWidgets.QPlainTextEdit();self.log.setReadOnly(True);tabs.addTab(self.log,'Journal en direct')
            self.path=QtWidgets.QLabel();self.path.setWordWrap(True);self.path.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.path)
            buttons=QtWidgets.QHBoxLayout();layout.addLayout(buttons)
            self.stop=QtWidgets.QPushButton('Arrêter après l’image en cours');self.stop.clicked.connect(self.cancel);buttons.addWidget(self.stop)
            refresh=QtWidgets.QPushButton('Actualiser');refresh.clicked.connect(self.refresh);buttons.addWidget(refresh)
            folder=QtWidgets.QPushButton('Ouvrir le dossier');folder.clicked.connect(self.folder);buttons.addWidget(folder)
            close=QtWidgets.QPushButton('Masquer le suivi');close.clicked.connect(self.close);buttons.addWidget(close)
            note=QtWidgets.QLabel('Masquer cette fenêtre laisse le calcul continuer. Les aperçus partiels ne servent pas à l’apprentissage.');note.setWordWrap(True);layout.addWidget(note)
            if node.userData('spirula_exchange_ui'):
                tabs.setTabVisible(0,False);self.stop.setText('Arrêter la conversion');note.setText('Le fichier apparaît à la fin de la conversion. Masquer le suivi laisse le calcul continuer.')
            self.timer=QtCore.QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()

        def cancel(self):
            import spirula_render
            try:spirula_render.stop(self.node)
            except Exception as exc:self.message.setText(str(exc))
            self.refresh()

        def folder(self):
            import spirula_render
            spirula_render.callback(self.node,'folder')

        def process_activity(self,pid):
            if not pid:return ''
            try:
                import psutil
                root=psutil.Process(int(pid));live=[root]+root.children(recursive=True);cpu=0.;memory=0;names=[]
                for process in live:
                    cached=self.processes.setdefault(process.pid,process)
                    try:cpu+=cached.cpu_percent(None);memory+=cached.memory_info().rss;names.append(cached.name())
                    except psutil.Error:pass
                return 'Processus actifs : %s · CPU machine %.0f %% · RAM %.1f Go'%(', '.join(sorted(set(names))),cpu/max(1,psutil.cpu_count() or 1),memory/2**30)
            except Exception:return 'Worker PID %s'%pid

        def refresh(self):
            try:
                state,folder,data=snapshot(self.node);phase=state.get('phase','idle');update_node(self.node,state)
                self.title.setText(PHASES.get(phase,'Prêt'))
                color='#e78b81' if phase=='failed' else '#8fce9b' if phase=='done' else '#8dbce5';self.title.setStyleSheet('font-size:20px;font-weight:bold;padding:6px;color:'+color)
                message=state.get('message','')
                if state.get('cancel_requested'):message='Arrêt demandé : l’image en cours sera terminée, puis les fichiers seront conservés.\n'+message
                self.message.setText(message)
                percent=state.get('frame_progress');completed=state.get('rendered',0);total=state.get('total',len(data.get('views',[])))
                if phase=='training' and state.get('steps'):percent=100*state.get('step',0)/state['steps']
                if phase=='done':percent=100;completed=total
                if percent is None and phase not in ('failed','cancelled','idle'):self.bar.setRange(0,0)
                else:self.bar.setRange(0,100);self.bar.setValue(round(percent or 0))
                text='Fichier : '+str(data.get('target','')) if data.get('exchange') else 'Images terminées : %s / %s'%(completed,total or '—')
                if phase=='rendering':text+=' · Image en cours : %s'%(completed+1)
                if phase=='training':text+=' · Itérations : %s / %s'%(state.get('step','…'),state.get('steps',data.get('iterations','…')))
                self.count.setText(text)
                elapsed=duration((state.get('finished') or time.time())-state.get('started',time.time()))
                process_text='Worker terminé.' if phase=='done' else 'Calcul arrêté.' if phase in ('failed','cancelled') else self.process_activity(state.get('worker_pid'))
                self.activity.setText('Temps écoulé : '+elapsed+'\n'+process_text)
                self.stop.setEnabled(phase in ('queued','loading','lighting','rendering','training','exporting') and not state.get('cancel_requested'))
                if folder:
                    if self.config!=str(folder):
                        self.config=str(folder);self.last_image=None;self.image.clear();self.image.setText('Attente du premier aperçu Karma…');self.image_info.clear()
                    self.path.setText(str(folder));logs='\n\n'.join('── '+name+' ──\n'+tail(folder/name,12000) for name in ('worker.log','render.log','training.log') if (folder/name).exists())
                    if logs!=self.log_signature:
                        bar=self.log.verticalScrollBar();at_end=bar.value()>=bar.maximum()-8;self.log.setPlainText(logs);self.log_signature=logs
                        if at_end:self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
                    live=folder/'live.png';images=list((folder/'images').glob('*.png'))
                    image=max(([live] if live.exists() else [])+images,key=lambda p:p.stat().st_mtime_ns,default=None)
                    if image:
                        signature=(str(image),image.stat().st_mtime_ns)
                        if signature!=self.last_image:
                            pix=QtGui.QPixmap(str(image))
                            if not pix.isNull():self.image.setPixmap(pix.scaled(720,520,QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation));self.last_image=signature;self.image_info.setText(('Aperçu partiel du rendu' if image==live else 'Image terminée : '+image.name))
                elif phase=='pending':self.image.clear();self.image.setText('Préparation de la capture…');self.image_info.clear()
                self.setWindowTitle('Spirula · '+PHASES.get(phase,'Suivi')+' · '+owner(self.node).name())
            except hou.ObjectWasDeleted:self.timer.stop();self.message.setText('Le nœud a été supprimé. Le worker éventuel continue dans son dossier.')
            except Exception as exc:self.message.setText('Suivi : '+str(exc))

        def closeEvent(self,event):
            self.timer.stop();WINDOWS.pop(key,None);super().closeEvent(event)

    dialog=Monitor();WINDOWS[key]=dialog;dialog.show();dialog.raise_();return dialog


def launch(node,function,message):
    """Paint immediate feedback before main-thread Houdini snapshot work."""
    import hou
    key=node.sessionId()
    if key in PENDING:raise RuntimeError('La demande est déjà en préparation.')
    OVERRIDES.pop(key,None)
    PENDING[key]={'message':message,'started':time.time()};node.parm('status').set(message)
    if not hou.isUIAvailable():
        try:return function()
        finally:PENDING.pop(key,None)
    from PySide6 import QtCore
    show(node)
    def run():
        if key not in PENDING:return
        try:function()
        except Exception as exc:
            node.parm('status').set(str(exc));PENDING.pop(key,None)
            state={'phase':'failed','message':str(exc),'started':time.time(),'finished':time.time()};OVERRIDES[key]=state;update_node(node,state)
            dialog=WINDOWS.get(key)
            if dialog:dialog.title.setText('Échec de la préparation');dialog.message.setText(str(exc))
            hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        finally:PENDING.pop(key,None)
    QtCore.QTimer.singleShot(75,lambda:hou.ui.postEventCallback(run))
