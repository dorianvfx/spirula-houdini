"""Spirula Studio process bridge and native Houdini GSplat workflow."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import atexit

ROOT = Path(__file__).resolve().parents[1]
JOBS = {}


def shutdown():
    for job in list(JOBS.values()):
        if job['process'].poll() is None:
            job['process'].terminate()
        job['log'].close()


atexit.register(shutdown)


def value(node, name):
    p = node.parm(name)
    return p.evalAsString() if p.parmTemplate().type().name() == 'Menu' else p.eval()


def executable(node):
    if node.parm('engine_release') and node.parm('engine_release').evalAsString()=='candidate':
        return __import__('spirula_train_profiles').engine_path(node)
    path = Path(value(node, 'executable'))
    if not path.is_file():
        raise RuntimeError('Exécutable Spirula introuvable : ' + str(path))
    return str(path)


def workspace(node):
    p = Path(value(node, 'workspace'))
    p.mkdir(parents=True, exist_ok=True)
    return p


def status(node, text):
    node.parm('status').set(text)


def plan(node, action):
    w = workspace(node)
    images = Path(value(node, 'images'))
    data = w / 'dataset'
    run = w / 'runs' / time.strftime('%Y%m%d_%H%M%S')
    run = run.with_name(run.name + '_' + uuid.uuid4().hex[:6])
    exe = executable(node)
    device = str(value(node, 'device'))
    common = ['--device', device]
    if action == 'advanced':
        args = json.loads(str(value(node, 'advanced_args')))
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError('Les arguments avancés doivent être une liste JSON de chaînes.')
        return [[exe, str(value(node, 'advanced_command'))] + args], None
    sfm = [exe, 'sfm', 'auto', str(images), '-o', str(data),
           '--quality', str(value(node, 'quality'))] + common
    train = [exe, 'train', str(value(node, 'preset')), '--data', str(data),
             '--image-dir', str(images), '--output-dir-prefix', str(run.parent),
             '--output-dir-name', run.name, '--num-iterations', str(value(node, 'iterations')),
             '--viewer-port', str(value(node, 'port')), '--keep-viewer-alive', '0',
             '--save-full-checkpoint', '1'] + common
    extract = [exe, 'sam', 'extract', str(value(node, 'video')), '-o', str(images),
               '--skip', str(value(node, 'skip'))] + common
    if action in ('sfm', 'pipeline') and not images.is_dir():
        raise RuntimeError('Choisir un dossier de photos existant, ou extraire la vidéo avant.')
    if action == 'extract' and not Path(value(node, 'video')).is_file():
        raise RuntimeError('Choisir une vidéo existante.')
    if action == 'train' and not (data / 'sparse').exists() and not (data / 'transforms.json').exists():
        raise RuntimeError('Reconstruire les caméras avant de lancer l’entraînement.')
    if action == 'pipeline':
        return [sfm, train], run
    if action == 'sfm':
        return [sfm], None
    if action == 'train':
        return [train], run
    if action == 'extract':
        images.mkdir(parents=True, exist_ok=True)
        return [extract], None
    if action == 'mesh':
        source = Path(value(node, 'splatfile'))
        if not source.is_file():
            raise RuntimeError('Importer un splat avant le maillage.')
        target = w / 'meshes' / ('mesh_' + uuid.uuid4().hex[:8])
        target.parent.mkdir(parents=True, exist_ok=True)
        run_dir = next((p for p in (source.parent, source.parent.parent) if (p / 'config.json').is_file()), None)
        args = [exe, 'mesh', str(run_dir or source), '--output', str(target), '--format', 'ply',
                '--color', 'vertex', '--max-grid-res', str(value(node, 'mesh_resolution'))] + common
        if run_dir is None:
            args += ['--no-data']
        return [args], target.with_suffix('.ply')
    raise ValueError(action)


def _spawn(job):
    command = job['commands'].pop(0)
    job['log'].write(('\n' + subprocess.list2cmdline(command) + '\n').encode('utf8'))
    job['log'].flush()
    env = os.environ.copy()
    env['SS_NO_AUTO_FETCH'] = '1'
    env['SS_LANG'] = 'fr'
    job['process'] = subprocess.Popen(command, stdout=job['log'], stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, env=env,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def start(node, action):
    import hou
    key = node.sessionId()
    if key in JOBS:
        raise RuntimeError('Un calcul est déjà actif sur ce nœud.')
    commands, result = plan(node, action)
    logs = workspace(node) / 'logs'
    logs.mkdir(exist_ok=True)
    path = logs / (time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6] + '.log')
    job = dict(node=node, commands=commands, result=result, action=action,
               log=open(path, 'ab', buffering=0), path=str(path))
    try:
        _spawn(job)
    except Exception:
        job['log'].close()
        raise
    JOBS[key] = job
    node.parm('logfile').set(str(path))
    status(node, 'En cours : ' + action)
    if hou.isUIAvailable():
        if not getattr(poll, 'installed', False):
            hou.ui.addEventLoopCallback(poll)
            poll.installed = True


def poll():
    import hou
    for key, job in list(JOBS.items()):
        node = job['node']
        try:
            code = job['process'].poll()
            if code is None:
                continue
            if code == 0 and job['commands']:
                _spawn(job)
                continue
            job['log'].close()
            del JOBS[key]
            if code:
                status(node, 'Échec (code %s) — consulter le journal' % code)
                continue
            if job['action'] in ('train', 'pipeline'):
                files = list(job['result'].rglob('splat.ply'))
                if not files:
                    status(node, 'Calcul terminé, aucun splat.ply trouvé : consulter le journal')
                    continue
                node.parm('splatfile').set(str(max(files, key=lambda p: p.stat().st_mtime)))
                reload_splat(node)
            elif job['action'] == 'mesh':
                if not job['result'].exists():
                    status(node, 'Mesh introuvable : consulter le journal')
                    continue
                node.parm('meshfile').set(str(job['result']))
                import_mesh(node)
            status(node, 'Terminé : ' + job['action'])
        except hou.ObjectWasDeleted:
            job['process'].terminate()
            job['log'].close()
            JOBS.pop(key, None)
        except Exception as exc:
            if job['process'].poll() is None:
                job['process'].terminate()
            job['log'].close()
            JOBS.pop(key, None)
            status(node, 'Erreur : ' + str(exc))
    if not JOBS and getattr(poll, 'installed', False):
        hou.ui.removeEventLoopCallback(poll)
        poll.installed = False


def stop(node):
    job = JOBS.pop(node.sessionId(), None)
    if job:
        job['process'].terminate()
        job['process'].wait(timeout=10)
        job['log'].close()
        status(node, 'Arrêt forcé — seul le dernier checkpoint enregistré est conservé')


def reload_splat(node):
    node.node('read_splat').parm('reload').pressButton()
    node.cook(force=True)


def receive_model(path, node_path):
    """Commit a handoff on Houdini's main thread, independently of panel visibility."""
    import hou
    n = hou.node(node_path)
    if n is None:
        n = create()
    probe = hou.Geometry()
    probe.loadFromFile(path)
    count = probe.intrinsicValue('pointcount')
    if count < 1:
        raise RuntimeError('Le fichier exporté ne contient aucun point.')
    if n.userData('spirula_chain_root') and not (probe.findPointAttrib('f_dc_0') or probe.findPointAttrib('f_dc')):
        raise RuntimeError('01 attend un Gaussian splat : envoyer le splat du Studio, et non son export mesh ou nuage de points.')
    if probe.findPointAttrib('f_dc_0') or probe.findPointAttrib('f_dc'):
        n.parm('splatfile').set(path)
        n.parmTuple('t').set((0, 0, 0))
        n.parmTuple('r').set((0, 0, 0))
        n.parm('scale').set(1)
        reload_splat(n)
        n.setDisplayFlag(True)
        n.setRenderFlag(True)
        obj = n.creator()
        obj.setDisplayFlag(True)
        if n.geometry().intrinsicValue('pointcount') != count:
            raise RuntimeError('Le nombre de gaussiennes importées est incorrect.')
        target = n
    elif probe.intrinsicValue('primitivecount'):
        n.parm('meshfile').set(path)
        target = import_mesh(n, apply_placement=False)
    else:
        obj = hou.node('/obj').createNode('geo', 'spirula_points')
        target = obj.createNode('file', 'POINTS_STUDIO')
        target.parm('file').set(path)
    status(n, '%s points reçus du Studio : %s' % (count, path))
    chain_root=n.userData('spirula_chain_root')
    if chain_root:
        import spirula_chain,json
        container=n.creator();chain_root=container.path();container.setUserData('spirula_chain_auto_studio','0');target=hou.node(spirula_chain.config(n)['scan']);target.setDisplayFlag(True);target.setRenderFlag(True);spirula_chain.status(target,'Scan reçu de Spirula. Aligner ici, puis passer en 03.')
        if hou.isUIAvailable():spirula_chain.focus(container)
    if hou.isUIAvailable():
        target.setCurrent(True, clear_all_selected=True)
        scene = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if scene:
            scene.setPwd(hou.node(chain_root) if chain_root else hou.node('/obj'))
            from spirula_transform import bounding_box
            bbox = bounding_box(target.geometry(), target.creator().worldTransform())
            scene.curViewport().frameBoundingBox(bbox)
            scene.setIsCurrentTab()
    return {'node': target.path(), 'points': count, 'file': path}


def gui(node):
    return studio(node)


def studio(node):
    global _OPENING_STUDIO
    if globals().get('_OPENING_STUDIO', False):
        return None
    _OPENING_STUDIO = True
    try:
        return _studio(node)
    finally:
        _OPENING_STUDIO = False


def _studio(node):
    import hou
    global ACTIVE_NODE
    ACTIVE_NODE = node.path()
    if not hou.isUIAvailable():
        return None
    hou.pypanel.installFile(str(ROOT / 'python_panels' / 'spirula.pypanel'))
    for pane in hou.ui.paneTabs():
        if pane.type() == hou.paneTabType.PythonPanel:
            interface = pane.activeInterface()
            if interface and interface.name() == 'spirula_studio':
                pane.setIsCurrentTab()
                widget = pane.activeInterfaceRootWidget()
                if widget and hasattr(widget, 'bind_selected'):
                    widget._node = node
                    widget.update_node_label()
                    widget.attach_window()
                return pane
    scene = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if scene and scene.pane():
        tab = scene.pane().createTab(hou.paneTabType.PythonPanel, python_panel_interface='spirula_studio')
        tab.setIsCurrentTab()  # a new tab can stay hidden behind the viewport tab otherwise
        return tab
    pane = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel)
    pane.setActiveInterface(hou.pypanel.interfaceByName('spirula_studio'))
    return pane


def import_mesh(node, apply_placement=True):
    import hou
    path = Path(value(node, 'meshfile'))
    if not path.is_file():
        raise RuntimeError('Le mesh n’existe pas encore.')
    obj = node.parent()
    while obj.parent() and obj.parent().path() != '/obj':
        obj = obj.parent()
    container = hou.node('/obj').createNode('geo', 'spirula_collision_mesh')
    for c in container.children():
        c.destroy()
    f = container.createNode('file', 'MESH_SOURCE')
    f.parm('file').set(str(path))
    x = container.createNode('xform', 'ALIGN_WITH_SPLAT')
    x.setInput(0, f)
    if apply_placement:
        for name in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'scale']:
            x.parm(name).setExpression('ch("%s/%s")' % (node.path(), name))
    out = container.createNode('null', 'OUT_COLLISION')
    out.setInput(0, x)
    out.setDisplayFlag(True)
    out.setRenderFlag(True)
    if obj.parent() and obj.parent().path() == '/obj':
        container.setInput(0, obj)
    container.layoutChildren()
    node.parm('collisionpath').set(out.path())
    return out


def solaris(node):
    import hou
    stage = hou.node('/stage')
    n = stage.createNode('sopimport', 'spirula_splats')
    n.parm('soppath').set(node.path())
    n.parm('primpath').set('/spirula/splats')
    n.parm('pathprefix').set('/spirula/splats')
    n.setDisplayFlag(True)
    n.setCurrent(True, clear_all_selected=True)
    stage.layoutChildren()
    if hou.isUIAvailable():
        pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if pane:
            pane.setPwd(stage)
    return n


def viewer(node):
    import hou
    global ACTIVE_NODE
    ACTIVE_NODE = node.path()
    panel = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel)
    interface = hou.pypanel.interfaceByName('spirula_training_web')
    if interface is None:
        hou.pypanel.installFile(str(ROOT / 'python_panels' / 'spirula.pypanel'))
        interface = hou.pypanel.interfaceByName('spirula_training_web')
    panel.setActiveInterface(interface)


def export(node):
    import hou
    from spirula_ply import write_geometry
    target = Path(value(node, 'exportfile'))
    target.parent.mkdir(parents=True, exist_ok=True)
    override = value(node, 'export_source')
    source = hou.node(override) if override else (node.inputs()[0] if node.inputs() and node.inputs()[0] else node.node('OUT_SPLAT'))
    if source is None:
        raise RuntimeError('Le SOP à exporter est introuvable.')
    geo = source.geometry()
    temp = target.with_name('.partial_' + target.name)
    try:
        if str(target).lower().endswith(('.bgeo', '.bgeo.sc')):
            geo.saveToFile(str(temp))
        elif target.suffix.lower() == '.ply':
            write_geometry(geo, temp, bool(value(node, 'linearize')))
        else:
            raise RuntimeError('Choisir .ply ou .bgeo.sc comme extension.')
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    status(node, 'Export : ' + str(target))


def callback(node, action):
    import hou
    try:
        if action in ('pipeline', 'extract', 'sfm', 'train', 'mesh', 'advanced'):
            start(node, action)
        else:
            globals()[action](node)
    except Exception as exc:
        status(node, str(exc))
        if hou.isUIAvailable():
            hou.ui.displayMessage(str(exc), severity=hou.severityType.Error)
        else:
            raise


def create():
    import hou
    selected = hou.selectedNodes()
    parent = selected[0].parent() if selected and selected[0].parent().childTypeCategory() == hou.sopNodeTypeCategory() else None
    if parent is None:
        parent = hou.node('/obj').createNode('geo', 'spirula_studio')
        for child in parent.children():
            child.destroy()
    n = parent.createNode('spirula::studio::1.0', 'spirula')
    n.setDisplayFlag(True)
    n.setRenderFlag(True)
    n.setCurrent(True, clear_all_selected=True)
    parent.layoutChildren()
    return n
