"""Host the unmodified Spirula desktop renderer inside a Houdini Qt pane."""
import atexit
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

from PySide6 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = []


def expected_ply_size(path):
    sizes = {'char': 1, 'uchar': 1, 'int8': 1, 'uint8': 1, 'short': 2,
             'ushort': 2, 'int16': 2, 'uint16': 2, 'int': 4, 'uint': 4,
             'int32': 4, 'uint32': 4, 'float': 4, 'float32': 4,
             'double': 8, 'float64': 8}
    elements = []
    binary = False
    with Path(path).open('rb') as stream:
        for unused in range(4096):
            line = stream.readline(4096)
            if not line or not line.endswith(b'\n'):
                return None
            words = line.decode('ascii', errors='replace').split()
            if words[:1] == ['format']:
                binary = words[1].startswith('binary_')
            elif words[:1] == ['element']:
                elements.append([int(words[2]), 0])
            elif words[:1] == ['property']:
                if len(words) != 3 or words[1] not in sizes or not elements:
                    return None
                elements[-1][1] += sizes[words[1]]
            elif words == ['end_header']:
                return stream.tell()+sum(n*stride for n, stride in elements) if binary else None
    return None


class Win32:
    """Window ownership and sizing for this plugin's own child processes."""
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Le viewport natif intégré nécessite Windows.')
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = {
            'EnumWindows': (wintypes.BOOL, [self.callback_type, wintypes.LPARAM]),
            'GetWindowThreadProcessId': (wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
            'GetClassNameW': (ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
            'GetWindowLongPtrW': (ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int]),
            'SetWindowLongPtrW': (ctypes.c_ssize_t, [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]),
            'GetParent': (wintypes.HWND, [wintypes.HWND]),
            'SetParent': (wintypes.HWND, [wintypes.HWND, wintypes.HWND]),
            'ShowWindow': (wintypes.BOOL, [wintypes.HWND, ctypes.c_int]),
            'IsWindow': (wintypes.BOOL, [wintypes.HWND]),
            'IsChild': (wintypes.BOOL, [wintypes.HWND, wintypes.HWND]),
            'SetWindowPos': (wintypes.BOOL, [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]),
            'PostMessageW': (wintypes.BOOL, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
            'GetClientRect': (wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(self.api, name)
            fn.restype, fn.argtypes = result, args

    def find(self, pid):
        matches = []
        @self.callback_type
        def visit(hwnd, unused):
            owner = wintypes.DWORD()
            self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid:
                name = ctypes.create_unicode_buffer(256)
                self.api.GetClassNameW(hwnd, name, len(name))
                width, height = self.geometry(hwnd)
                if name.value.startswith('GLFW') and width >= 320 and height >= 200:
                    matches.append(int(hwnd))
            return True
        self.api.EnumWindows(visit, 0)
        if len(matches) > 1:
            raise RuntimeError('Plusieurs fenêtres Spirula pour le même processus.')
        return matches[0] if matches else None

    def save_style(self, hwnd):
        return (self.api.GetWindowLongPtrW(hwnd, -16), self.api.GetWindowLongPtrW(hwnd, -20))

    def child_style(self, hwnd):
        style = self.api.GetWindowLongPtrW(hwnd, -16)
        style = (style & ~0x80CF0000) | 0x46000000
        self.api.SetWindowLongPtrW(hwnd, -16, style)

    def restore(self, hwnd, styles, show=False):
        if not hwnd or not self.api.IsWindow(hwnd):
            return
        self.api.SetParent(hwnd, None)
        self.api.SetWindowLongPtrW(hwnd, -16, styles[0])
        self.api.SetWindowLongPtrW(hwnd, -20, styles[1])
        self.api.SetWindowPos(hwnd, None, 80, 80, 1440, 900, 0x0020 | 0x0004 | 0x0010)
        self.api.ShowWindow(hwnd, 5 if show else 0)

    def geometry(self, hwnd):
        rect = wintypes.RECT()
        self.api.GetClientRect(hwnd, ctypes.byref(rect))
        return [rect.right - rect.left, rect.bottom - rect.top]


class Session(QtCore.QObject):
    available = QtCore.Signal()
    stateChanged = QtCore.Signal(dict)
    message = QtCore.Signal(str)
    exported = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    ended = QtCore.Signal()

    def __init__(self, executable, workspace, source='', parent=None):
        super().__init__(parent)
        self.win32 = Win32()
        self.workspace = Path(workspace).resolve()
        self.folder = self.workspace / 'studio' / ('session_' + uuid.uuid4().hex[:10])
        self.folder.mkdir(parents=True, exist_ok=True)
        self.config = self.workspace / 'studio' / 'preferences'
        settings = self.config / 'spirula-studio' / 'gui.conf'
        settings.parent.mkdir(parents=True, exist_ok=True)
        if not settings.exists():
            settings.write_text('lang=fr\nnative_dialogs=0\nshow_log=0\nui_scale=0.900\n', encoding='utf8')
        else:
            lines = settings.read_text(encoding='utf8').splitlines()
            lines = [s for s in lines if not s.startswith('native_dialogs=')]
            settings.write_text('\n'.join(lines + ['native_dialogs=0']) + '\n', encoding='utf8')
        self.source = ''
        self.working = None
        args = [str(executable)]
        if source and Path(source).is_file():
            self.source = str(Path(source).resolve())
            self.working = self.folder / ('working' + Path(source).suffix)
            shutil.copy2(source, self.working)
            args.append(str(self.working))
        self.token = secrets.token_hex(24)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(SS_GUI_AUTOMATION='1', SS_GUI_AUTOMATION_PORT=str(self.port),
                   SS_GUI_AUTOMATION_TOKEN=self.token, SS_GUI_OFFSCREEN='1',
                   APPDATA=str(self.config), SS_LANG='fr')
        self.log_path = self.folder / 'studio.log'
        self.log = self.log_path.open('ab', buffering=0)
        self.process = subprocess.Popen(args, cwd=str(self.workspace), env=env,
                                        stdout=self.log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.hwnd = None
        self.styles = None
        self.window = None
        self.container = None
        self.host = None
        self.state = {}
        self.node_path = ''
        self._pending_state = False
        self._exporting = False
        self._export_callback = None
        self.last_import = None
        self._ready = False
        self._last_poll = 0
        self._born = time.monotonic()
        self._timeout_reported = False
        self._stopped = False
        self._results = queue.SimpleQueue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='spirula-native')
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        SESSIONS.append(self)

    def request(self, action, **params):
        params['token'] = self.token
        url = 'http://127.0.0.1:%d/ui/%s?' % (self.port, action) + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=12) as response:
            data = response.read()
        if action == 'screenshot':
            return data
        result = json.loads(data)
        if not result.get('ok', True):
            raise RuntimeError(result.get('error', str(result)))
        return result

    def submit(self, name, function):
        future = self.executor.submit(function)
        def done(f):
            try:
                self._results.put((name, f.result(), None))
            except Exception as exc:
                self._results.put((name, None, str(exc)))
        future.add_done_callback(done)

    def tick(self):
        if self._stopped:
            return
        if self.process.poll() is not None:
            self._stopped = True
            self.timer.stop()
            self.log.close()
            self.executor.shutdown(wait=False, cancel_futures=True)
            if self.process.returncode:
                self.failed.emit('Spirula a quitté (code %s). Journal : %s' % (self.process.returncode, self.log_path))
            self.ended.emit()
            return
        if self.hwnd is None:
            self.hwnd = self.win32.find(self.process.pid)
            if self.hwnd:
                self.styles = self.win32.save_style(self.hwnd)
                self.available.emit()
            elif time.monotonic() - self._born > 45 and not self._timeout_reported:
                self._timeout_reported = True
                self.failed.emit('La fenêtre Spirula tarde à démarrer. Journal : ' + str(self.log_path))
        while not self._results.empty():
            name, result, error = self._results.get()
            if name == 'state':
                self._pending_state = False
                if not error:
                    self.state = result
                    self._ready = result.get('app_ready', False)
                    self.stateChanged.emit(result)
            elif name == 'export':
                self._exporting = False
                if error:
                    self.failed.emit(error)
                else:
                    try:
                        if self._export_callback:
                            self.last_import = self._export_callback(str(result))
                        self.exported.emit(str(result))
                    except Exception as exc:
                        self.failed.emit('Import Houdini : ' + str(exc))
                self._export_callback = None
            elif error:
                self.failed.emit(error)
            elif name == 'drop':
                self.message.emit('Ouverture dans Spirula…')
        now = time.monotonic()
        if self.hwnd and not self._pending_state and not self._exporting and now-self._last_poll > 1:
            self._pending_state = True
            self._last_poll = now
            self.submit('state', lambda: self.request('state'))

    def attach(self, host):
        if not self.hwnd:
            return False
        if self.host is host and self.container:
            return True
        self.detach()
        self.host = host
        self.win32.child_style(self.hwnd)
        if self.window is None:
            self.window = QtGui.QWindow.fromWinId(self.hwnd)
        if self.window is None:
            raise RuntimeError('Qt ne peut pas héberger la fenêtre Spirula.')
        self.container = QtWidgets.QWidget.createWindowContainer(self.window, host)
        self.container.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.container.setMinimumSize(320, 240)
        host.layout().addWidget(self.container)
        self.container.show()
        self.window.show()
        self.container.setFocus()
        return True

    def detach(self, external=False):
        if self.container:
            if self.window:
                self.window.setParent(None)
                self.window.hide()
            if self.host and self.host.layout():
                self.host.layout().removeWidget(self.container)
            self.container.deleteLater()
            self.container = None
        self.host = None
        if self.hwnd and self.styles:
            self.win32.restore(self.hwnd, self.styles, show=external)

    def open_paths(self, paths):
        self.submit('drop', lambda: self.request('drop', paths='\n'.join(str(p) for p in paths)))

    def _wait_item(self, id, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            items = self.request('tree')['items']
            candidates = [item for item in items if item['id'] == id]
            if candidates:
                return candidates
            time.sleep(.15)
        raise RuntimeError('Le contrôle Spirula « %s » est indisponible. Fermer les dialogues ouverts et sélectionner un modèle de splats.' % id)

    def trained_checkpoint(self, state):
        candidates = []
        settings = self.config / 'spirula-studio' / 'gui.conf'
        if settings.exists():
            for line in settings.read_text(encoding='utf8', errors='replace').splitlines():
                if line.startswith('recent.run='):
                    value = line.split('=', 1)[1].split(' ', 1)
                    if len(value) == 2:
                        candidates.append(Path(value[1]))
        dataset = Path(state.get('dataset', ''))
        if state.get('dataset') and (dataset / 'outputs').is_dir():
            candidates.extend(p for p in (dataset / 'outputs').iterdir() if p.is_dir())
        files = []
        for folder in candidates:
            cfg = folder / 'config.json'
            if cfg.is_file() and state.get('dataset'):
                try:
                    data = json.loads(cfg.read_text(encoding='utf8'))
                    if Path(data.get('data', '')).resolve() != dataset.resolve():
                        continue
                except (OSError, ValueError):
                    continue
            files.extend(folder.glob('step-*.ckpt/splat.ply'))
        if not files:
            raise RuntimeError('Aucun checkpoint enregistré pour cet entraînement. Enregistrer le modèle dans Spirula avant de l’envoyer.')
        return max(files, key=lambda p: p.stat().st_mtime_ns)

    def export_copy(self, on_complete=None):
        if self._exporting:
            return
        self._exporting = True
        self._export_callback = on_complete
        self.last_import = None
        self.message.emit('Copie du modèle édité vers Houdini…')
        target = self.folder / ('houdini_' + uuid.uuid4().hex[:10] + '.ply')
        def work():
            state = self.request('state')
            if state.get('busy') or state.get('dialog_open'):
                raise RuntimeError('Terminer le calcul ou fermer le dialogue Spirula avant l’envoi.')
            if state.get('screen') == 'train' and state.get('train_phase') == 'done':
                source = self.trained_checkpoint(state)
                shutil.copy2(source, target)
                return target
            items = self.request('tree')['items']
            if not any(i['id'] == 'leave_edit' for i in items):
                self._wait_item('enter_edit')
                self.request('click', id='enter_edit')
                self._wait_item('leave_edit')
            self.request('key', keys='Ctrl+S')
            copies = self._wait_item('save_copy')
            self.request('click', id='save_copy', index=len(copies)-1)
            self._wait_item('##path')
            self.request('text', id='##path', value=str(target), enter='1')
            self._wait_item('fd_save_here')
            self.request('click', id='fd_save_here')
            stable = None
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if target.exists():
                    current = (target.stat().st_size, target.stat().st_mtime_ns)
                    if current == stable and current[0] > 100:
                        with target.open('rb') as f:
                            if f.read(3) != b'ply':
                                raise RuntimeError('La sortie Spirula n’est pas un fichier PLY.')
                        expected = expected_ply_size(target)
                        if expected is None or current[0] >= expected:
                            return target
                    stable = current
                time.sleep(.5)
            raise RuntimeError('Spirula n’a pas terminé l’export. Consulter son journal.')
        self.submit('export', work)

    def close_studio(self):
        if self.hwnd:
            self.win32.api.PostMessageW(self.hwnd, 0x0010, 0, 0)


def release_all():
    for session in SESSIONS:
        if session.process.poll() is None and session.hwnd and session.styles:
            try:
                session.win32.restore(session.hwnd, session.styles, show=True)
            except Exception:
                pass


atexit.register(release_all)
