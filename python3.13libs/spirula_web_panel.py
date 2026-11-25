from pathlib import Path
import hou
from PySide6 import QtCore, QtWidgets
from PySide6.QtWebEngineWidgets import QWebEngineView
import spirula_houdini as bridge


class Panel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        self.path = QtWidgets.QLineEdit(getattr(bridge, 'ACTIVE_NODE', ''))
        row.addWidget(self.path)
        bind = QtWidgets.QPushButton('Utiliser le nœud sélectionné')
        bind.clicked.connect(self.bind)
        row.addWidget(bind)
        layout.addLayout(row)
        row = QtWidgets.QHBoxLayout()
        for label, action in [('Photos → splat', 'pipeline'), ('Entraîner', 'train'),
                              ('Mesh', 'mesh'), ('Recharger le splat', 'reload_splat'), ('Arrêter', 'stop')]:
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda checked=False, a=action: self.action(a))
            row.addWidget(b)
        load = QtWidgets.QPushButton('Connecter le viewer')
        load.clicked.connect(self.connect_viewer)
        row.addWidget(load)
        layout.addLayout(row)
        self.info = QtWidgets.QLabel('Le viewer est disponible pendant un entraînement. Les réglages sont dans le nœud Spirula.')
        layout.addWidget(self.info)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.web = QWebEngineView()
        self.web.setHtml('<html><body style="background:#24282d;color:#ddd;font-family:sans-serif;padding:32px"><h2>Spirula Studio · Houdini</h2><p>Sélectionner le nœud Spirula, lancer un entraînement puis connecter le viewer.</p><p>Les splats terminés s’affichent directement dans le viewport 3D Houdini.</p></body></html>')
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        split.addWidget(self.web)
        split.addWidget(self.log)
        split.setSizes([600, 180])
        layout.addWidget(split)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)

    def node(self):
        n = hou.node(self.path.text())
        return n if n and n.type().name() == 'spirula::studio::1.0' else None

    def bind(self):
        selected = hou.selectedNodes()
        if selected and selected[0].type().name() == 'spirula::studio::1.0':
            self.path.setText(selected[0].path())
        self.refresh()

    def action(self, action):
        n = self.node()
        if n:
            bridge.callback(n, action)

    def connect_viewer(self):
        n = self.node()
        if n:
            self.web.setUrl(QtCore.QUrl('http://127.0.0.1:%d' % n.evalParm('port')))

    def refresh(self):
        n = self.node()
        if not n:
            return
        self.info.setText(n.evalParm('status'))
        path = Path(n.evalParm('logfile'))
        if path.is_file():
            with path.open('rb') as f:
                f.seek(max(0, path.stat().st_size-32000))
                text = f.read().decode('utf8', errors='replace')
            if self.log.toPlainText() != text:
                self.log.setPlainText(text)
                self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
