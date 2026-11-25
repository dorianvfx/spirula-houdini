"""Read-only pipeline checks and dependency fingerprints. No rendering is started."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import numpy as np


def file_signature(value):
    import hou
    value=hou.expandString(value)
    if not value or value.startswith(('op:','opdef:')):return ''
    path=Path(value)
    if not path.is_absolute():path=Path(hou.expandString('$HIP'))/path
    paths=sorted(path.parent.glob(path.name.replace('<UDIM>','[0-9][0-9][0-9][0-9]'))) if '<UDIM>' in str(path) else [path]
    digest=hashlib.sha256();found=False
    for item in paths:
        if item.is_file():
            found=True
            digest.update(str(item).encode('utf8'))
            with item.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest() if found else ''


def geometry_signature(geo):
    """Include topology and assignment changes even when P is unchanged."""
    import hou
    digest=hashlib.sha256()
    for kind,attrs,getter in [('p',geo.pointAttribs(),'point'),('v',geo.vertexAttribs(),'vertex'),('r',geo.primAttribs(),'prim')]:
        for attr in sorted(attrs,key=lambda a:a.name()):
            digest.update((kind+attr.name()+str(attr.size())).encode())
            if attr.dataType()==hou.attribData.Float:
                digest.update(getattr(geo,getter+'FloatAttribValuesAsString')(attr.name()))
            elif attr.dataType()==hou.attribData.Int:
                digest.update(np.asarray(getattr(geo,getter+'IntAttribValues')(attr.name()),dtype=np.int64).tobytes())
            elif attr.dataType()==hou.attribData.String:
                digest.update(json.dumps(getattr(geo,getter+'StringAttribValues')(attr.name())).encode('utf8'))
    for prim in geo.prims():
        digest.update(str(prim.type()).encode())
        digest.update(np.asarray([v.point().number() for v in prim.vertices()],dtype=np.int64).tobytes())
    return digest.hexdigest()


def audit(node):
    import hou,spirula_chain as chain
    root=chain.rig(node);config=chain.config(root);issues=[];metrics={};branches=[]
    def issue(level,stage,message):issues.append(dict(level=level,stage=stage,message=message))
    studio=hou.node(config['studio']);scan=hou.node(config['scan'])
    try:
        geo=scan.geometry();count=geo.intrinsicValue('pointcount');metrics['scan_gaussians']=count
        if not count:issue('error','01','Aucun scan importé.')
        elif not geo.findPointAttrib('GS_Alpha'):issue('error','02','Le scan ne contient pas les attributs Gaussian Splats.')
        else:
            for name in ('P','Cd','scale','orient','GS_Alpha'):
                if geo.findPointAttrib(name):
                    values=np.frombuffer(geo.pointFloatAttribValuesAsString(name),dtype=np.float32)
                    if not np.isfinite(values).all():issue('error','02','Valeurs non finies : '+name)
                    if name=='scale' and np.any(values<=0):issue('error','02','Tailles de gaussiennes nulles ou négatives.')
            metrics['raw_ply_mib_estimate']=round(count*62*4/2**20,1)
    except Exception as exc:issue('error','02',str(exc))
    workspace=Path(studio.evalParm('workspace'));existing=workspace
    while not existing.exists() and existing!=existing.parent:existing=existing.parent
    metrics['disk_free_gib']=round(shutil.disk_usage(existing).free/2**30,2)
    for index,entry in enumerate(config['branches']):
        stage=hou.node(entry['mesh']);ns=chain.nodes(stage);record={'object':index+1}
        try:
            mesh=ns['place'].geometry()
            if not mesh.intrinsicValue('primitivecount'):raise ValueError('Charger un mesh polygonal en 03.')
            record['mesh_points']=mesh.intrinsicValue('pointcount')
            views=chain.camera_plan(stage);record['views']=len(views)
            record['megapixels']=round(sum(v['w']*v['h'] for v in views)/1e6,1)
            # Explicitly a storage bound, not a render-time prediction.
            record['uncompressed_rgba_exr_gib']=round(record['megapixels']*1e6*16/2**30,2)
            if record['uncompressed_rgba_exr_gib']>metrics['disk_free_gib']*.7:issue('warning','07','Objet %s : budget de rendus important face à l’espace disque libre.'%(index+1))
            if ns['cameras'].evalParm('mode')==0:
                elevations=[float(v) for v in ns['cameras'].evalParm('elevations').split()]
                if not elevations or min(elevations)>-40:issue('warning','06','Objet %s : dessous peu couvert ; vérifier les parties visibles pendant la visite.'%(index+1))
            if ns['train'].evalParm('iterations')<1000:issue('warning','08','Objet %s : apprentissage court de validation, pas une preuve de qualité finale.'%(index+1))
            record['training_ready']=bool(chain.state(ns['render']).get('dataset_signature')==chain.dataset_signature(stage))
            if mesh.findPrimAttrib('shop_materialpath'):
                for path in set(mesh.primStringAttribValues('shop_materialpath')):
                    mat=hou.node(path)
                    if path and mat is None:issue('error','03','Matériau introuvable : '+path)
                    if mat:
                        for child in (mat,)+mat.allSubChildren():
                            for parm in child.parms():
                                template=parm.parmTemplate()
                                if isinstance(template,hou.StringParmTemplate) and template.stringType()==hou.stringParmType.FileReference:
                                    value=parm.evalAsString()
                                    if value and not value.startswith(('op:','opdef:')) and not file_signature(value):issue('error','03','Fichier matériau manquant : '+value)
        except Exception as exc:issue('error','03–08','Objet %s : %s'%(index+1,exc))
        branches.append(record)
    issue('info','Qualité','Ce contrôle ne mesure ni la qualité perceptuelle, ni les ombres de contact, ni la fluidité du viewer web.')
    report=dict(schema=1,metrics=metrics,branches=branches,issues=issues,ready=not any(i['level']=='error' for i in issues))
    workspace.mkdir(parents=True,exist_ok=True);path=workspace/'diagnostic_pipeline.json';path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    if hou.isUIAvailable():
        text='\n'.join('%s · %s · %s'%(i['level'].upper(),i['stage'],i['message']) for i in issues)
        hou.ui.displayMessage(('Contrôle prêt' if report['ready'] else 'Points à corriger')+'\n'+text+'\n\nRapport : '+str(path))
    return report
