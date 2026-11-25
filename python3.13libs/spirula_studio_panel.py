"""Native Studio with a compact Houdini handoff toolbar."""
from pathlib import Path
import shutil
import uuid
import time
from functools import partial
import hou
from PySide6 import QtCore, QtWidgets
import spirula_houdini as bridge
import spirula_native as native

ACTIVE_SESSION = None


def detach_owned(session, host):
    if session and session.host is host:
        session.detach()


class Panel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.session = None
        self._node = None
        self._notice_until = 0
        self.setObjectName('SpirulaNativePanel')
        self.setMinimumSize(640, 420)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        bar = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel('SPIRULA STUDIO')
        title.setStyleSheet('font-weight: bold; color: #b6d9ee; padding: 4px 8px;')
        bar.addWidget(title)
        self.open_button = QtWidgets.QToolButton()
        self.open_button.setText('Ouvrir…')
        self.open_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QtWidgets.QMenu(self.open_button)
        menu.addAction('Splat / mesh…', self.open_model)
        menu.addAction('Photos / dataset / projet…', self.open_folder)
        menu.addAction('Vidéo…', self.open_video)
        self.open_button.setMenu(menu)
        bar.addWidget(self.open_button)
        self.send_button = QtWidgets.QPushButton('Envoyer vers Houdini')
        self.send_button.setToolTip('Enregistre une nouvelle copie du modèle édité et la charge dans Houdini.')
        self.send_button.clicked.connect(self.send)
        self.send_button.setEnabled(False)
        bar.addWidget(self.send_button)
        back = QtWidgets.QPushButton('Houdini → Studio')
        back.setToolTip('Ouvre une copie de la sortie SOP sélectionnée, ou du nœud Spirula lié.')
        back.clicked.connect(self.from_houdini)
        bar.addWidget(back)
        workbench = QtWidgets.QToolButton()
        workbench.setText('Outils Houdini')
        workbench.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        tools = QtWidgets.QMenu(workbench)
        tools.addAction('Créer la chaîne de nœuds Spirula',lambda:self.make_tool('pipeline'))
        tools.addAction('Insérer un objet éclairé par le scan…',lambda:self.make_tool('insert'))
        tools.addAction('Mesh texturé → Splat de surface…',lambda:self.make_tool('surface'))
        tools.addAction('Scène éclairée → Rendus → Splat…',lambda:self.make_tool('render'))
        tools.addAction('Fusionner les splats sélectionnés…',lambda:self.make_tool('assemble'))
        tools.addAction('Découper le scan avec une boîte…',lambda:self.make_tool('cut'))
        workbench.setMenu(tools);bar.addWidget(workbench)
        bar.addStretch(1)
        self.node_label = QtWidgets.QLabel()
        bar.addWidget(self.node_label)
        more = QtWidgets.QToolButton()
        more.setText('⋯')
        more.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        options = QtWidgets.QMenu(more)
        options.addAction('Lier au nœud Spirula sélectionné', self.bind_selected)
        options.addAction('Cadrer le splat dans Houdini', self.frame_houdini)
        options.addAction('Vue côte à côte avec Houdini', self.side_by_side)
        options.addSeparator()
        options.addAction('Détacher Studio dans sa fenêtre', self.detach_window)
        options.addAction('Réintégrer Studio dans ce panneau', self.attach_window)
        options.addAction('Relancer Studio après fermeture', self.start)
        options.addAction('Afficher le journal', self.show_log)
        options.addAction('Fermer Studio…', self.close_studio)
        more.setMenu(options)
        bar.addWidget(more)
        layout.addLayout(bar)
        self.host = QtWidgets.QWidget(self)
        host_layout = QtWidgets.QVBoxLayout(self.host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        self.loading = QtWidgets.QLabel('Démarrage du viewport natif Spirula…')
        self.loading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.loading.setStyleSheet('background: #1d2024; color: #9aa9b8; font-size: 14px; padding: 32px;')
        host_layout.addWidget(self.loading)
        layout.addWidget(self.host, 1)
        self.info = QtWidgets.QLabel('Viewport natif et contrôles Spirula Studio')
        self.info.setStyleSheet('color: #9aa9b8; padding: 2px 6px;')
        layout.addWidget(self.info)
        self.resolve_node()
        QtCore.QTimer.singleShot(0, self.start)

    def resolve_node(self):
        selected = [n for n in hou.selectedNodes() if n.type().name() == 'spirula::studio::1.0']
        preferred = hou.node(getattr(bridge, 'ACTIVE_NODE', ''))
        self._node = selected[0] if selected else preferred
        if self._node is None or self._node.type().name() != 'spirula::studio::1.0':
            self._node = bridge.create()
        self.update_node_label()

    def node(self):
        try:
            return self._node if self._node and self._node.type().name() == 'spirula::studio::1.0' else None
        except hou.ObjectWasDeleted:
            return None

    def update_node_label(self):
        n = self.node()
        self.node_label.setText(n.name() if n else 'Aucun nœud lié')
        self.node_label.setToolTip(n.path() if n else '')

    def bind_selected(self):
        selected = hou.selectedNodes()
        if selected and selected[0].type().name() == 'spirula::studio::1.0':
            self._node = selected[0]
            self.update_node_label()
            self.info.setText('Envoi lié à ' + self._node.path())

    def start(self):
        global ACTIVE_SESSION
        if self.session and self.session.process.poll() is None:
            self.attach_window()
            return
        if self.node() is None:
            self.resolve_node()
        n = self.node()
        try:
            session = ACTIVE_SESSION
            if session is None or session.process.poll() is not None:
                workspace = bridge.workspace(n)
                source = n.evalParm('splatfile')
                if n.userData('spirula_chain_root') and source.endswith('empty.bgeo'):source=''
                if (any(abs(v) > 1e-9 for v in n.evalParmTuple('t') + n.evalParmTuple('r'))
                        or abs(n.evalParm('scale')-1) > 1e-9):
                    from spirula_ply import write_geometry
                    inputs = workspace / 'studio' / 'inputs'
                    inputs.mkdir(parents=True, exist_ok=True)
                    source = inputs / ('placed_' + uuid.uuid4().hex[:10] + '.ply')
                    write_geometry(n.geometry(), source, bool(n.evalParm('linearize')))
                session = native.Session(bridge.executable(n), workspace, source)
                ACTIVE_SESSION = session
            self.session = session
            session.node_path = n.path()
            session.available.connect(self.attach_window)
            session.stateChanged.connect(self.state_changed)
            session.message.connect(self.info.setText)
            session.exported.connect(self.import_export)
            session.failed.connect(self.error)
            session.ended.connect(self.ended)
            owned_session, owned_host = session, self.host
            self.destroyed.connect(lambda: detach_owned(owned_session, owned_host))
            if session.hwnd:
                self.attach_window()
        except Exception as exc:
            self.error(str(exc))

    def attach_window(self):
        if not self.session:
            return
        try:
            if self.session.attach(self.host):
                self.loading.hide()
                self.send_button.setEnabled(True)
                self.info.setText('Spirula natif intégré · menus, navigation et édition disponibles')
        except Exception as exc:
            self.error(str(exc))

    def detach_window(self):
        if self.session:
            self.session.detach(external=True)
            self.loading.setText('Studio est détaché. Menu ⋯ → Réintégrer Studio.')
            self.loading.show()

    def state_changed(self, state):
        if not self.session or self.session.host is not self.host:
            return
        if time.monotonic() < self._notice_until:
            return
        if state.get('train_phase') == 'training':
            self.info.setText('Entraînement Spirula · étape %s' % state.get('step', 0))
        elif not self.session._exporting:
            self.info.setText('Spirula natif · %s · Envoyer vers Houdini pour actualiser la scène' % state.get('screen', ''))

    def send(self):
        if self.session:
            if self.node() is None:
                self.resolve_node()
            self.session.export_copy(on_complete=partial(bridge.receive_model, node_path=self.node().path()))

    def import_export(self, path):
        if self.session and self.session.last_import:
            result = self.session.last_import
            self.info.setText('%s points chargés dans %s' % (result['points'], result['node']))
            self._notice_until = time.monotonic()+20
            return
        if not self.session or self.session.host is not self.host:
            return
        if self.node() is None:
            self.resolve_node()
        n = self.node()
        try:
            probe = hou.Geometry()
            probe.loadFromFile(path)
            if not (probe.findPointAttrib('f_dc_0') or probe.findPointAttrib('f_dc')):
                if probe.prims():
                    n.parm('meshfile').set(path)
                    mesh = bridge.import_mesh(n, apply_placement=False)
                    self.info.setText('Mesh reçu : %s faces → %s' % (len(mesh.geometry().prims()), mesh.path()))
                else:
                    obj = hou.node('/obj').createNode('geo', 'spirula_points')
                    for child in obj.children():
                        child.destroy()
                    file = obj.createNode('file', 'POINTS_STUDIO')
                    file.parm('file').set(path)
                    self.info.setText('Nuage de points reçu : ' + file.path())
                return
            n.parm('splatfile').set(path)
            n.parmTuple('t').set((0, 0, 0))
            n.parmTuple('r').set((0, 0, 0))
            n.parm('scale').set(1)
            bridge.reload_splat(n)
            n.setDisplayFlag(True)
            n.setRenderFlag(True)
            self.info.setText('%s gaussiennes envoyées vers %s' % (len(n.geometry().points()), n.path()))
            bridge.status(n, 'Copie reçue du Studio intégré : ' + path)
            self.frame_houdini()
        except Exception as exc:
            self.error(str(exc))

    def open_model(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Ouvrir dans Spirula', '', 'Splats / meshes PLY (*.ply);;Meshes (*.glb *.gltf *.obj *.stl);;Tous les fichiers (*)')
        if path and self.session:
            if Path(path).suffix.lower() in ('.obj', '.gltf'):
                self.session.open_paths([path])
            else:
                copy = self.session.folder / ('working_' + uuid.uuid4().hex[:8] + Path(path).suffix)
                shutil.copy2(path, copy)
                self.session.open_paths([copy])

    def open_folder(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, 'Photos, dataset ou projet Spirula')
        if path and self.session:
            self.session.open_paths([path])

    def open_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Vidéo source', '', 'Vidéos (*.mp4 *.mov *.mkv *.avi *.360 *.insv);;Tous les fichiers (*)')
        if path and self.session:
            self.session.open_paths([path])

    def from_houdini(self):
        if not self.session:
            return
        try:
            selected = hou.selectedNodes()
            source = selected[0] if selected and isinstance(selected[0], hou.SopNode) else self.node()
            if source is None:
                raise RuntimeError('Sélectionner un SOP de splats ou de mesh.')
            geo = source.geometry()
            target = self.session.folder / ('houdini_to_studio_' + uuid.uuid4().hex[:8] + '.ply')
            if geo.findPointAttrib('GS_Alpha'):
                from spirula_ply import write_geometry
                write_geometry(geo, target, bool(self.node().evalParm('linearize')) if self.node() else True)
            else:
                geo.saveToFile(str(target))
            self.session.open_paths([target])
        except Exception as exc:
            self.error(str(exc))

    def frame_houdini(self):
        n = self.node()
        if n:
            n.setCurrent(True, clear_all_selected=True)
            scene = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if scene:
                scene.curViewport().frameBoundingBox(n.geometry().boundingBox())
                scene.setIsCurrentTab()

    def make_tool(self,kind):
        try:
            if kind=='pipeline':
                import spirula_chain
                hou.ui.postEventCallback(lambda:spirula_chain.create());return
            elif kind=='insert':
                import spirula_insert
                node=spirula_insert.create_simple()
            elif kind=='surface':
                import spirula_object
                node=spirula_object.create()
            elif kind=='render':
                import spirula_render
                node=spirula_render.create()
            else:
                import spirula_scene
                node=spirula_scene.assemble() if kind=='assemble' else spirula_scene.cut()[0]
            self._notice_until=time.monotonic()+30
            self.info.setText('Outil créé : %s. Configurer ses paramètres dans Houdini.'%node.path())
            scene=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if scene:scene.setPwd(node.parent());scene.setIsCurrentTab()
        except Exception as exc:self.error(str(exc))

    def side_by_side(self):
        for tab in hou.ui.paneTabs():
            if tab.type() == hou.paneTabType.PythonPanel and tab.activeInterfaceRootWidget() is self:
                pane = tab.pane()
                scene = pane.tabOfType(hou.paneTabType.SceneViewer)
                if scene is None:
                    scene = pane.createTab(hou.paneTabType.SceneViewer)
                scene.setIsCurrentTab()
                right = pane.splitHorizontally()
                bridge.ACTIVE_NODE = self.node().path() if self.node() else ''
                right.createTab(hou.paneTabType.PythonPanel, python_panel_interface='spirula_studio')
                tab.close()
                return

    def show_log(self):
        if self.session:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Journal Spirula')
            dialog.resize(950, 600)
            box = QtWidgets.QVBoxLayout(dialog)
            text = QtWidgets.QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText(self.session.log_path.read_text(encoding='utf8', errors='replace')[-100000:])
            box.addWidget(text)
            dialog.exec()

    def close_studio(self):
        if self.session:
            self.session.close_studio()

    def ended(self):
        self.send_button.setEnabled(False)
        self.loading.setText('Studio fermé. Menu ⋯ → Relancer Studio.')
        self.loading.show()

    def error(self, message):
        self._notice_until = time.monotonic()+60
        self.info.setText(message)
        self.info.setToolTip(message)
        if self.node():
            bridge.status(self.node(), message)

    def closeEvent(self, event):
        detach_owned(self.session, self.host)
        super().closeEvent(event)
