"""Training primitives exposed by the installed cross-vendor Spirula engine."""
PRIMITIVES=('3dgs','mip','3dgut')

def selected(node):
    parm=node.parm('primitive');value=parm.evalAsString() if parm else '3dgs'
    if value not in PRIMITIVES:raise ValueError('Primitive Spirula non prise en charge : '+value)
    return value

def compatible(data,primitive):return data.get('primitive','3dgs')==primitive

def arguments(data):
    value=data.get('primitive','3dgs')
    if value not in PRIMITIVES:raise ValueError('Primitive Spirula non prise en charge : '+str(value))
    return ['--primitive',value]


def engine_path(node):
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];p=node.parm('engine_release');candidate=p and p.evalAsString()=='candidate'
    import spirula_runtime
    try:file=spirula_runtime.candidate_engine(root/'runtime') if candidate else spirula_runtime.stable_engine(root/'runtime')
    except FileNotFoundError as exc:raise ValueError('Version Spirula absente : '+str(exc))
    return str(file)

def engine_matches(data,node):
    from pathlib import Path
    return Path(data.get('executable','')).resolve()==Path(engine_path(node)).resolve()


def apply_to_capture(source,capture):
    if capture.parm('primitive'):capture.parm('primitive').set(PRIMITIVES.index(selected(source)))
    if capture.parm('engine_release'):capture.parm('engine_release').set(source.evalParm('engine_release') if source.parm('engine_release') else 0)
