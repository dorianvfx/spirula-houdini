"""Spirula Polish - whole-scene learned refinement of an existing splat.

Takes a trained splat (PLY) + the photos/poses it came from, and continues training
at native photo resolution with densification enabled (so detail can be ADDED, not
just pruned). Output is a new PLY; the source is never modified.

Core is Houdini-free: usable from the CLI, from a Houdini node or from a farm.

    python spirula_polish.py --dataset D --ply start.ply --out OUTDIR [--iterations 8000]

What it can and cannot do (be honest in the UI):
  + recovers sharpness the first (faster/coarser) training did not reach
  + replaces blurry / under-fitted regions where photos show more detail
  - cannot invent detail that no photo contains
  - quality is measured on held-out photos only when `holdout` is on
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PLACEMENT_KEYS = {  # config.json key -> engine flag
    'orientation_method': '--orientation-method',
    'center_method': '--center-method',
    'auto_scale_poses': '--auto-scale-poses',
    'scene_center': '--scene-center',
}
PRESETS = {
    # name: (iterations, cap_max, quality, resolution_divisor)
    'rapide': (3000, 1_500_000, 'medium', 2),
    'standard': (8000, 3_000_000, 'high', 1),
    'maximum': (20000, 6_000_000, 'ultra', 1),
}


def find_engine():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import spirula_runtime
    try:
        return str(spirula_runtime.candidate_engine())
    except FileNotFoundError:
        return str(spirula_runtime.stable_engine())


def source_run_config(ply):
    """If the PLY sits in a Spirula run folder, return that run's config.json (dict)."""
    ply = Path(ply).resolve()
    for folder in (ply.parent, ply.parent.parent):
        cfg = folder / 'config.json'
        if cfg.is_file():
            try:
                return json.loads(cfg.read_text(encoding='utf8'))
            except ValueError:
                return None
    return None


def validate(dataset, ply):
    dataset = Path(dataset)
    if not dataset.is_dir():
        raise ValueError('Dossier photos introuvable : %s' % dataset)
    has_poses = (dataset / 'transforms.json').is_file() or (dataset / 'sparse').is_dir() or (dataset / 'images.txt').is_file()
    if not has_poses:
        raise ValueError('Aucune pose de caméra (transforms.json ou sparse/0) dans %s.' % dataset)
    images = [p for p in (dataset / 'images').glob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png')] if (dataset / 'images').is_dir() else []
    if len(images) < 3 and not (dataset / 'transforms.json').is_file():
        raise ValueError('Moins de 3 photos dans %s/images.' % dataset)
    ply = Path(ply)
    if not ply.is_file():
        raise ValueError('PLY de départ introuvable : %s' % ply)
    with ply.open('rb') as f:
        head = f.read(4096)
    if not head.startswith(b'ply') or b'f_dc_0' not in head or b'opacity' not in head:
        raise ValueError('Ce PLY n\'est pas un splat 3DGS standard.')
    return len(images)


def build_command(engine, dataset, ply, run_dir, iterations=8000, cap_max=3_000_000, quality='high',
                  resolution_divisor=1, holdout=True, placement=None, shape_lr_scale=0.1, extra=()):
    """Engine command line. `placement` = source run config (keeps the same scene frame)."""
    run_dir = Path(run_dir)
    cmd = [engine, 'train', '3dgs', '--data', str(dataset), '--init-ply', str(ply),
           '--output-dir-prefix', str(run_dir), '--output-dir-name', 'run',
           '--num-iterations', str(int(iterations)), '--cap-max', str(int(cap_max)), '--quality', quality,
           '--primitive', '3dgs', '--sh-degree', '3', '--train-resolution-divisor', str(int(resolution_divisor)),
           '--progressive-resolution', '0', '--disable-viewer', '1', '--keep-viewer-alive', '0',
           '--save-full-checkpoint', '1', '--device', 'auto', '--eval-lpips', '0',
           # Start from the existing shape: small position/scale steps, no random walk.
           '--noise-lr', '0', '--noise-lr-final', '0',
           '--means-lr', '%g' % (0.000256 * shape_lr_scale), '--means-lr-final', '%g' % (3.2e-06 * shape_lr_scale),
           '--background-noise-warmup', '0']
    if holdout:
        cmd += ['--eval-mode', 'interval', '--eval-interval', '8']
    else:
        cmd += ['--eval-mode', 'all']
    if placement:
        for key, flag in PLACEMENT_KEYS.items():
            if key in placement and placement[key] is not None:
                value = placement[key]
                cmd += [flag, ('1' if value else '0') if isinstance(value, bool) else str(value)]
    else:
        cmd += ['--orientation-method', 'none', '--center-method', 'none', '--auto-scale-poses', '0', '--scene-center', 'none']
    return cmd + list(extra)


PROGRESS = re.compile(r'(?:step|étape|etape|iter\w*)\D{0,12}(\d+)\s*/\s*(\d+)', re.I)


def tail(path, size=40000):
    path = Path(path)
    if not path.is_file():
        return ''
    with path.open('rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - size))
        return f.read().decode('utf8', 'replace')


def progress(log):
    hits = PROGRESS.findall(tail(log))
    return (int(hits[-1][0]), int(hits[-1][1])) if hits else None


def result_ply(run_dir):
    files = list((Path(run_dir) / 'run').glob('step-*.ckpt/splat.ply'))
    return max(files, key=lambda p: p.stat().st_mtime_ns) if files else None


def start(dataset, ply, work, **options):
    """Launch in the background; returns the job folder. Poll with status()."""
    options_copy = dict(options)
    preset = options_copy.pop('preset', None)
    if preset:
        iterations, cap, quality, div = PRESETS[preset]
        options_copy.setdefault('iterations', iterations)
        options_copy.setdefault('cap_max', cap)
        options_copy.setdefault('quality', quality)
        options_copy.setdefault('resolution_divisor', div)
    n = validate(dataset, ply)
    job = Path(work) / ('polish_' + time.strftime('%Y%m%d_%H%M%S'))
    job.mkdir(parents=True, exist_ok=False)
    placement = source_run_config(ply)
    cmd = build_command(options_copy.pop('engine', None) or find_engine(), dataset, ply, job, placement=placement, **options_copy)
    (job / 'job.json').write_text(json.dumps(dict(dataset=str(dataset), source_ply=str(ply), images=n,
        placement_from_source_run=bool(placement), command=cmd, started=time.time()), indent=2), encoding='utf8')
    env = os.environ.copy()
    env['SS_NO_AUTO_FETCH'] = '1'
    log = (job / 'training.log').open('ab', buffering=0)
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, creationflags=flags)
    (job / 'pid').write_text(str(process.pid))
    return job


def pid_alive(pid):
    try:
        out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid, '/NH'], capture_output=True, text=True).stdout
        return str(pid) in out
    except OSError:
        return False


def status(job):
    job = Path(job)
    pid = int((job / 'pid').read_text()) if (job / 'pid').is_file() else 0
    alive = bool(pid) and pid_alive(pid)
    prog = progress(job / 'training.log')
    out = result_ply(job)
    if alive:
        state = 'running'
    elif (job / 'cancelled').exists():
        state = 'cancelled'
    elif out is not None and prog and prog[0] >= prog[1]:
        state = 'done'
    elif out is not None:
        state = 'done'
    else:
        state = 'failed'
    return dict(state=state, progress=prog, result=str(out) if out else None, log=str(job / 'training.log'))


def stop(job):
    job = Path(job)
    (job / 'cancelled').write_text('1')
    if (job / 'pid').is_file():
        subprocess.run(['taskkill', '/PID', (job / 'pid').read_text(), '/T', '/F'], capture_output=True)


# ---------------------------------------------------------------- Houdini node glue
def _parm(node, name):
    return node.evalParm(name)


def ui_start(node):
    """Button 'Lancer' of spirula::polish: export input (or use start_ply) and train in background."""
    import hou
    cur = node.userData('polish_job')
    if cur and status(cur)['state'] == 'running':
        raise hou.NodeError('Un raffinement est déjà en cours pour ce node.')
    start_ply = _parm(node, 'start_ply').strip()
    work = Path(hou.expandString(_parm(node, 'workspace')))
    work.mkdir(parents=True, exist_ok=True)
    if not start_ply:
        sources = node.inputs()
        if not sources or sources[0] is None:
            raise hou.NodeError('Brancher un splat en entrée, ou renseigner « PLY de départ ».')
        from spirula_ply import write_geometry
        start_ply = str(work / ('depart_%s.ply' % time.strftime('%Y%m%d_%H%M%S')))
        write_geometry(sources[0].geometry(), start_ply, linearized=True)
    else:
        start_ply = hou.expandString(start_ply)
    preset = ('rapide', 'standard', 'maximum')[_parm(node, 'preset')]
    opts = dict(preset=preset, holdout=bool(_parm(node, 'holdout')))
    if _parm(node, 'iterations') > 0:
        opts['iterations'] = _parm(node, 'iterations')
    job = start(hou.expandString(_parm(node, 'dataset')), start_ply, work, **opts)
    node.setUserData('polish_job', str(job))
    node.parm('result').set('')
    node.parm('status').set('Lancé. Cliquer Actualiser pour suivre la progression.')


def ui_refresh(node):
    import hou
    job = node.userData('polish_job')
    if not job:
        node.parm('status').set('Aucun calcul lancé.')
        return
    s = status(job)
    p = s['progress']
    text = {'running': 'En cours', 'done': 'Terminé', 'failed': 'Échec (voir training.log)', 'cancelled': 'Arrêté'}[s['state']]
    if p:
        text += ' · étape %d / %d (%d %%)' % (p[0], p[1], 100 * p[0] // max(p[1], 1))
    node.parm('status').set(text)
    if s['state'] == 'done' and s['result']:
        node.parm('result').set(s['result'])
        node.parm('show').set(1)
        node.parm('status').set(text + ' · résultat chargé (Avant/Après : paramètre « Afficher »).')


def ui_stop(node):
    job = node.userData('polish_job')
    if job:
        stop(job)
        node.parm('status').set('Arrêt demandé.')


def create(selected=None):
    """Shelf tool: insert 'Raffiner par apprentissage' after the selected splat SOP."""
    import hou
    selected = selected or next(iter(hou.selectedNodes()), None)
    if selected is None or not isinstance(selected, hou.SopNode):
        raise ValueError('Sélectionner la sortie SOP du splat à raffiner.')
    node = selected.parent().createNode('spirula::polish::1.0', 'RAFFINER_PAR_APPRENTISSAGE')
    node.setInput(0, selected)
    node.setPosition(selected.position() + hou.Vector2(0, -1.5))
    node.setColor(hou.Color((.52, .36, .68)))
    node.setDisplayFlag(True)
    node.setCurrent(True, clear_all_selected=True)
    return node


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Raffiner un splat avec ses photos (apprentissage).')
    ap.add_argument('--dataset', required=True)
    ap.add_argument('--ply', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--preset', choices=sorted(PRESETS), default='standard')
    ap.add_argument('--iterations', type=int)
    ap.add_argument('--cap-max', type=int)
    ap.add_argument('--no-holdout', action='store_true')
    a = ap.parse_args(argv)
    opts = dict(preset=a.preset, holdout=not a.no_holdout)
    if a.iterations: opts['iterations'] = a.iterations
    if a.cap_max: opts['cap_max'] = a.cap_max
    job = start(a.dataset, a.ply, a.out, **opts)
    print('Job :', job)
    while True:
        s = status(job)
        print(s['state'], s['progress'], flush=True)
        if s['state'] != 'running':
            print(json.dumps(s, indent=2))
            return 0 if s['state'] == 'done' else 1
        time.sleep(30)


if __name__ == '__main__':
    sys.exit(main())
