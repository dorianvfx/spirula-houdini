"""Run inside Houdini; keep running workers and open their new monitor."""
import hou,importlib
from pathlib import Path
import spirula_render
old_poll=spirula_render.poll
jobs=dict(spirula_render.JOBS)
try:
    if getattr(old_poll,'installed',False):hou.ui.removeEventLoopCallback(old_poll)
except Exception:pass
# Keep process and log handles while refreshing the controller implementation.
importlib.reload(spirula_render);spirula_render.JOBS.update(jobs)
import spirula_monitor
try:
    for window in list(spirula_monitor.WINDOWS.values()):window.close()
except Exception:pass
importlib.reload(spirula_monitor)
import spirula_insert
importlib.reload(spirula_insert)
root=Path(hou.text.expandString('$SPIRULA_ROOT'))
job_paths={key:job['node'].path() for key,job in spirula_render.JOBS.items()}
hou.hda.reloadFile(str(root/'otls/SpirulaWorkbench.hda'))
remapped={}
for key,job in spirula_render.JOBS.items():
    try:
        current=hou.node(job_paths[key])
        if current:job['node']=current;remapped[current.sessionId()]=job
    except hou.ObjectWasDeleted:pass
spirula_render.JOBS=remapped
if remapped:
    hou.ui.addEventLoopCallback(spirula_render.poll);spirula_render.poll.installed=True
captures=[j['node'] for j in remapped.values()]
for node in hou.selectedNodes():
    capture=node.node('CAPTURE') if node.type().name()=='spirula::insert_asset::1.0' else node if node.type().name()=='spirula::render_splat::1.0' else None
    if capture and capture not in captures:captures.append(capture)
if not captures:
    captures=[n.node('CAPTURE') for n in hou.node('/obj').allSubChildren() if n.type().name()=='spirula::insert_asset::1.0'][:1]
for capture in captures:spirula_monitor.show(capture)
print('Suivi Spirula actualisé. Les workers déjà actifs sont conservés.')
