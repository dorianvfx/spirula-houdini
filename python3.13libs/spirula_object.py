"""Deterministic, textured surface-to-Gaussian conversion for arbitrary polygon SOPs."""
from io import BytesIO
import json
import math
import os
from pathlib import Path
import time
import uuid
import numpy as np


def sop(node):
    import hou
    if isinstance(node, hou.ObjNode):
        node = node.displayNode()
    if not isinstance(node, hou.SopNode):
        raise ValueError('Choisir un objet géométrique ou un SOP polygonal.')
    return node


def srgb_to_linear(c):
    return np.where(c <= .04045, c/12.92, ((c+.055)/1.055)**2.4)


def linear_to_srgb(c):
    c = np.maximum(c, 0)
    return np.where(c <= .0031308, c*12.92, 1.055*c**(1/2.4)-.055)


def texture(path):
    import hou
    from PIL import Image
    image = Image.open(BytesIO(hou.readBinaryFile(hou.expandString(path)))).convert('RGB')
    return np.asarray(image, dtype=np.float32)/255.


def material(path, fallback, warnings):
    import hou
    node = hou.node(path) if path else None
    info = {'color': np.array(fallback, dtype=np.float32), 'texture': None, 'normal': None, 'name': path or 'Cd / couleur de secours'}
    if node is None:
        if path:
            warnings.append('Matériau introuvable : '+path)
        return info
    if 'principledshader' not in node.type().name() and not node.parmTuple('base_color'):
        candidates = [n for n in node.allSubChildren() if 'principledshader' in n.type().name() or n.parmTuple('base_color')]
        if candidates:
            node = candidates[0]
    for name in ('basecolor', 'base_color', 'diff_color'):
        if node.parmTuple(name):
            info['color'] = np.array(node.evalParmTuple(name), dtype=np.float32)
            break
    image_path = ''
    if node.parm('basecolor_texture') and node.evalParm('basecolor_useTexture'):
        image_path = node.evalParm('basecolor_texture')
    elif node.parmTuple('base_color'):
        try:
            idx = node.inputIndex('base_color')
            image = node.inputs()[idx]
            if image and image.parm('file'):
                image_path = image.evalParm('file')
            elif image:
                warnings.append('Réseau de couleur procédural à baker pour '+path)
        except (IndexError, hou.OperationFailed):
            pass
    if image_path:
        try:
            info['texture'] = texture(image_path)
        except Exception as exc:
            raise RuntimeError('Texture illisible pour %s : %s' % (path, image_path)) from exc
    info['texture_path'] = image_path
    return info


def sample_image(image, uv):
    h, w = image.shape[:2]
    x = np.mod(uv[:, 0], 1)*w-.5
    y = (1-np.mod(uv[:, 1], 1))*h-.5
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    fx = (x-ix)[:, None]
    fy = (y-iy)[:, None]
    a = image[iy % h, ix % w]*(1-fx)+image[iy % h, (ix+1) % w]*fx
    b = image[(iy+1) % h, ix % w]*(1-fx)+image[(iy+1) % h, (ix+1) % w]*fx
    return a*(1-fy)+b*fy


def capture(source, fallback=(.5,.5,.5)):
    import hou
    source = sop(source)
    original = source.geometry()
    if original.findPointAttrib('GS_Alpha') or original.findPointAttrib('f_dc_0'):
        raise ValueError('La source est déjà un splat. Choisir un mesh polygonal à convertir.')
    unpack = hou.sopNodeTypeCategory().nodeVerb('unpack')
    unpack.setParms({'iterations': 8, 'convertpolysoup': 1, 'transfer_attributes': '*'})
    expanded = hou.Geometry()
    unpack.execute(expanded, [original])
    divide = hou.sopNodeTypeCategory().nodeVerb('divide')
    divide.setParms({'usemaxsides': 1, 'numsides': 3, 'convex': 1})
    geo = hou.Geometry()
    divide.execute(geo, [expanded])
    prims = geo.prims()
    if not prims or any(p.type() != hou.primType.Polygon or len(p.vertices()) != 3 for p in prims):
        raise ValueError('La conversion nécessite une surface polygonale triangulable (pas un volume ou des courbes).')
    points = np.frombuffer(geo.pointFloatAttribValuesAsString('P'), dtype=np.float32).reshape(-1,3)
    vertices = [v for p in prims for v in p.vertices()]
    indices = np.fromiter((v.point().number() for v in vertices), dtype=np.int64).reshape(-1,3)
    vertex_ids = np.fromiter((v.linearNumber() for v in vertices),dtype=np.int64)
    record = np.zeros((len(prims),3,12), dtype=np.float32)
    record[:,:,:3] = points[indices]
    warnings = []
    for name, start, default in [('uv',3,0), ('N',6,0), ('Cd',9,1)]:
        attr = geo.findVertexAttrib(name)
        if attr:
            values = np.frombuffer(geo.vertexFloatAttribValuesAsString(name),dtype=np.float32).reshape(-1,attr.size())
            record[:,:,start:start+min(3,attr.size())] = values[vertex_ids,:3].reshape(len(prims),3,-1)
        elif geo.findPointAttrib(name):
            attr = geo.findPointAttrib(name)
            values = np.frombuffer(geo.pointFloatAttribValuesAsString(name),dtype=np.float32).reshape(-1,attr.size())
            record[:,:,start:start+min(3,attr.size())] = values[indices,:3]
        else:
            record[:,:,start:start+3] = default
    cross = np.cross(record[:,1,:3]-record[:,0,:3],record[:,2,:3]-record[:,0,:3])
    area = np.linalg.norm(cross,axis=1)*.5
    valid = area > 1e-16
    if not valid.any():
        raise ValueError('La surface ne contient aucun triangle de surface non nulle.')
    if not (geo.findPointAttrib('N') or geo.findVertexAttrib('N')):
        normal = cross/np.maximum(np.linalg.norm(cross,axis=1)[:,None],1e-20)
        record[:,:,6:9] = normal[:,None,:]
    paths = list(geo.primStringAttribValues('shop_materialpath')) if geo.findPrimAttrib('shop_materialpath') else ['']*len(prims)
    object_material = source.creator().evalParm('shop_materialpath') if source.creator().parm('shop_materialpath') else ''
    paths = [p or object_material for p in paths]
    names = sorted(set(paths))
    materials = [material(p,fallback,warnings) for p in names]
    if any(m['texture'] is not None for m in materials) and not (geo.findPointAttrib('uv') or geo.findVertexAttrib('uv')):
        raise ValueError('Les matériaux utilisent des textures mais la source ne contient pas de coordonnées uv.')
    mapping = {p:i for i,p in enumerate(names)}
    ids = np.array([mapping[p] for p in paths],dtype=np.int32)
    return {'triangles':record[valid], 'materials':materials, 'ids':ids[valid],
            'area':float(area[valid].sum()), 'source':source.path(), 'warnings':warnings}


def subdivide(record, ids, spacing, limit, progress=None):
    done, done_ids = [], []
    total = 0
    for depth in range(32):
        p=record[:,:,:3]
        lengths=np.stack([np.sum((p[:,1]-p[:,0])**2,axis=1), np.sum((p[:,2]-p[:,1])**2,axis=1), np.sum((p[:,0]-p[:,2])**2,axis=1)],axis=1)
        edge=lengths.argmax(axis=1)
        split=lengths.max(axis=1)>spacing*spacing
        if (~split).any():
            done.append(record[~split]); done_ids.append(ids[~split]); total+=int((~split).sum())
        if not split.any():
            return np.concatenate(done),np.concatenate(done_ids)
        if total+2*int(split.sum())>limit:
            raise ValueError('La précision demandée dépasse la limite de %s gaussiennes. Augmenter la limite ou l’espacement.'%limit)
        selected=record[split]; e=edge[split]; selected_ids=ids[split]
        order=np.stack([e,(e+1)%3,(e+2)%3],axis=1)
        selected=np.take_along_axis(selected,order[:,:,None],axis=1)
        mid=(selected[:,0]+selected[:,1])*.5
        left=np.stack([selected[:,0],mid,selected[:,2]],axis=1)
        right=np.stack([mid,selected[:,1],selected[:,2]],axis=1)
        record=np.concatenate([left,right]);ids=np.concatenate([selected_ids,selected_ids])
        if progress:
            progress(min(.65,.03+depth*.045),'Subdivision : %s cellules'%(total+len(record)))
    raise ValueError('Limite de subdivision atteinte : vérifier les triangles dégénérés de la source.')


def quaternion_from_matrix(m):
    q=np.zeros((len(m),4),dtype=np.float64)
    trace=np.trace(m,axis1=1,axis2=2)
    masks=[trace>0]
    masks.extend([(trace<=0)&(np.argmax(np.diagonal(m,axis1=1,axis2=2),axis=1)==k) for k in range(3)])
    for k,mask in enumerate(masks):
        a=m[mask]
        if not len(a):continue
        if k==0:
            s=np.sqrt(np.maximum(1+np.trace(a,axis1=1,axis2=2),1e-20))*2
            q[mask]=np.stack([(a[:,2,1]-a[:,1,2])/s,(a[:,0,2]-a[:,2,0])/s,(a[:,1,0]-a[:,0,1])/s,s/4],axis=1)
        else:
            i=k-1;j=(i+1)%3;l=(i+2)%3
            s=np.sqrt(np.maximum(1+a[:,i,i]-a[:,j,j]-a[:,l,l],1e-20))*2
            v=np.zeros((len(a),4));v[:,i]=s/4;v[:,j]=(a[:,j,i]+a[:,i,j])/s;v[:,l]=(a[:,l,i]+a[:,i,l])/s;v[:,3]=(a[:,l,j]-a[:,j,l])/s;q[mask]=v
    return q/np.maximum(np.linalg.norm(q,axis=1)[:,None],1e-20)


FIELDS=['x','y','z','nx','ny','nz']+['f_dc_'+str(i) for i in range(3)]+['f_rest_'+str(i) for i in range(45)]+['opacity']+['scale_'+str(i) for i in range(3)]+['rot_'+str(i) for i in range(4)]


def convert(data,target,budget=1000000,spacing=0,limit=6000000,coverage=1.8,thickness=.035,opacity=.995,lighting=False,progress=None):
    born=time.monotonic()
    if spacing<=0:
        spacing=math.sqrt(4*data['area']/(math.sqrt(3)*max(1,budget)))
    cells,ids=subdivide(data['triangles'],data['ids'],float(spacing),int(limit),progress)
    count=len(cells);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name('.partial_'+target.name)
    header='ply\nformat binary_little_endian 1.0\ncomment Spirula Houdini textured surface Gaussians\nelement vertex %s\n'%count
    header+=''.join('property float %s\n'%f for f in FIELDS)+'end_header\n'
    try:
        with temp.open('wb') as stream:
            stream.write(header.encode('ascii'))
            for start in range(0,count,65536):
                cell=cells[start:start+65536];mid=cell.mean(axis=1);p=cell[:,:,:3];delta=p-mid[:,None,:3]
                cov=np.einsum('nki,nkj->nij',delta,delta)/12
                eig,axis=np.linalg.eigh(cov)
                major=axis[:,:,2];minor=axis[:,:,1];normal=np.cross(major,minor)
                geometric=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);flip=np.sum(normal*geometric,axis=1)<0
                minor[flip]*=-1;normal[flip]*=-1
                frames=np.stack([major,minor,normal],axis=2)
                scales=np.stack([np.sqrt(np.maximum(eig[:,2],1e-24))*coverage,np.sqrt(np.maximum(eig[:,1],1e-24))*coverage,np.sqrt(np.maximum(eig[:,1],1e-24))*thickness],axis=1)
                colors=np.ones((len(cell),3),dtype=np.float64)
                for i,mat in enumerate(data['materials']):
                    mask=ids[start:start+len(cell)]==i
                    if not mask.any():continue
                    c=np.broadcast_to(mat['color'],(int(mask.sum()),3)).copy()
                    if mat['texture'] is not None:c*=srgb_to_linear(sample_image(mat['texture'],mid[mask,3:5]))
                    colors[mask]=c*mid[mask,9:12]
                if lighting:
                    ns=mid[:,6:9];ns/=np.maximum(np.linalg.norm(ns,axis=1)[:,None],1e-20)
                    light=np.array([.4,.8,.6]);light/=np.linalg.norm(light)
                    colors*=.55+.65*np.maximum(0,ns@light)[:,None]
                rows=np.zeros((len(cell),len(FIELDS)),dtype='<f4');rows[:,:3]=mid[:,:3];rows[:,3:6]=normal
                rows[:,6:9]=(linear_to_srgb(colors)-.5)/.28209479177387814
                rows[:,54]=math.log(opacity/(1-opacity));rows[:,55:58]=np.log(np.maximum(scales,1e-12))
                rows[:,58:62]=quaternion_from_matrix(frames)[:,[3,0,1,2]]
                if not np.isfinite(rows).all():raise ValueError('Valeurs non finies dans les gaussiennes générées.')
                rows.tofile(stream)
                if progress:progress(.65+.34*(start+len(cell))/count,'Textures et gaussiennes : %s / %s'%(start+len(cell),count))
        os.replace(temp,target)
    finally:
        if temp.exists():temp.unlink()
    report={'source':data['source'],'gaussians':count,'source_triangles':len(data['triangles']),'max_cell_edge':spacing,'surface_area':data['area'],'seconds':time.monotonic()-born,'materials':[{'name':m['name'],'texture':m.get('texture_path','')} for m in data['materials']],'warnings':data['warnings'],'appearance':'base color + vertex color; fixed diffuse light' if lighting else 'base color + vertex color; unlit','limitations':'Surface sampling; no trained view-dependent reflections, transparency or procedural shader baking.'}
    target.with_suffix('.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return report


def build(node):
    import hou
    inputs=node.inputs()
    source=inputs[0] if inputs else hou.node(node.evalParm('source'))
    if source is None:raise ValueError('Brancher le mesh ou choisir un SOP source.')
    folder=Path(node.evalParm('workspace'));target=folder/('object_'+uuid.uuid4().hex[:10]+'.ply')
    with hou.InterruptableOperation('Objet → Gaussian Splats',open_interrupt_dialog=True) as operation:
        data=capture(source,node.evalParmTuple('fallback'))
        def progress(t,text):operation.updateProgress(t)
        report=convert(data,target,budget=node.evalParm('budget'),spacing=node.evalParm('spacing'),limit=node.evalParm('limit'),coverage=node.evalParm('coverage'),thickness=node.evalParm('thickness'),opacity=node.evalParm('opacity'),lighting=bool(node.evalParm('lighting')),progress=progress)
        node.parm('splatfile').set(str(target));node.node('read_splat').parm('reload').pressButton();node.cook(force=True)
        node.parm('status').set('%s gaussiennes · cellules ≤ %.6g · %s textures'%(report['gaussians'],report['max_cell_edge'],sum(bool(m['texture']) for m in report['materials'])))
        node.setDisplayFlag(True);node.setRenderFlag(True)
    return report


def callback(node):
    import hou
    try:return build(node)
    except Exception as exc:
        node.parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def create(source=None):
    import hou
    source=sop(source or (hou.selectedNodes()[0] if hou.selectedNodes() else None))
    parent=source.parent()
    if not parent.isEditable():raise ValueError('Sélectionner la sortie du mesh dans son réseau de géométrie, hors d’un asset verrouillé.')
    node=parent.createNode('spirula::object_splat::1.0','object_to_splat');node.setInput(0,source);node.setPosition(source.position()+hou.Vector2(0,-2));node.setCurrent(True,clear_all_selected=True)
    return node
