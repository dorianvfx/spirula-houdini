"""Local post-export refinement. Known-mesh radiance or native 3DGS fine-tuning.

This is not an implementation of SuGaR, MILo or 2DGS. Source images supply detail;
new Gaussians alone cannot recover unobserved information.
"""
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import numpy as np

VERSION='7.3.0'
ROLES=('refine_zone','refine_renders','refine_apply','refine_check')
SETTINGS=('method','mesh','lop_source','dataset','photo_transform','units','center','size','feather_m','pixel_m','axis','width','height','samples','max_views','patch_cap','iterations','split','workspace')


def nodes(node):
    if not node.userData('spirula_refine_id'):raise ValueError('Créer le parcours avec Spirula Raffinement local sur la sortie SOP du splat.')
    return {n.userData('spirula_refine_role'):n for n in node.parent().children() if n.userData('spirula_refine_id')==node.userData('spirula_refine_id') and n.userData('spirula_refine_role')}


def state(node):return json.loads(node.userData('spirula_refine_state') or '{}')


def remember(node,**values):
    value=state(node);value.update(values);node.setUserData('spirula_refine_state',json.dumps(value));return value


def settings(node):
    z=nodes(node)['refine_zone'];d={}
    for key in SETTINGS:
        p=z.parmTuple(key)
        d[key]=list(p.eval()) if len(p)>1 else p[0].eval()
    if d['method']==0:d.pop('photo_transform',None)
    if not np.isfinite(d['center']+d['size']).all() or min(d['size'])<=0:raise ValueError('La zone doit avoir trois dimensions strictement positives et finies.')
    for key in ('units','pixel_m'):
        if not np.isfinite(d[key]) or d[key]<=0:raise ValueError('Unités et précision doivent être positives.')
    if not np.isfinite(d['feather_m']) or d['feather_m']<0:raise ValueError('Transition invalide.')
    if min(d['width'],d['height'])<32 or max(d['width'],d['height'])>8192 or not 1<=d['samples']<=64:raise ValueError('Résolution ou échantillonnage hors limites.')
    if not 100<=d['patch_cap']<=12000000 or d['max_views']<1 or d['iterations']<1:raise ValueError('Budget de calcul invalide.')
    return d


def source(node):
    s=nodes(node)['refine_zone'].inputs()
    if not s or s[0] is None:raise ValueError('Brancher le splat de départ sur le node Zone de détail.')
    s=s[0]
    geometry=s.geometry()
    if geometry is None:raise ValueError('Le splat source ne peut pas cuire : '+'; '.join(s.errors()))
    if not geometry.findPointAttrib('GS_Alpha'):raise ValueError('L’entrée doit être un splat Houdini, pas un mesh.')
    import hou
    if not np.allclose(np.array(s.creator().worldTransform().asTuple()).reshape(4,4),np.eye(4)):
        raise ValueError('Le Geo de pilotage doit être à identité. Placer le splat avec un Transform SOP avant la zone.')
    return s


def signature(node,kind='all'):
    import hou
    d=settings(node);s=source(node);g=s.geometry();d.pop('workspace',None)
    if kind=='renders':
        for key in ('patch_cap','iterations','split'):d.pop(key,None)
    h=hashlib.sha256((VERSION+json.dumps(d,sort_keys=True)).encode())
    for key in ('P','Cd','GS_Alpha','scale','pscale','orient','restorient','GS_SPH_R','GS_SPH_G','GS_SPH_B'):
        if g.findPointAttrib(key):h.update(g.pointFloatAttribValuesAsString(key))
    h.update(str(hou.frame()).encode())
    if d['method']==0:
        lop=hou.node(d['lop_source']);mesh=hou.node(d['mesh'])
        if lop is None or mesh is None:raise ValueError('Choisir le LOP éclairé et le mesh SOP de référence.')
        stage=lop.stage()
        if stage is None:raise ValueError('Le stage Solaris ne peut pas cuire.')
        from spirula_quality import file_signature
        from pxr import Sdf,Usd
        layer=stage.Flatten();snapshot=Usd.Stage.Open(layer);snapshot.RemovePrim('/HoudiniLayerInfo');layer.documentation=''
        h.update(layer.ExportToString().encode())
        for prim in stage.Traverse():
            for attr in prim.GetAttributes():
                if attr.GetTypeName()==Sdf.ValueTypeNames.Asset:
                    a=attr.Get(hou.frame())
                    if a and a.path:h.update(file_signature(a.resolvedPath or a.path).encode())
        # SOP topology/positions and placement may be independent from the LOP.
        from spirula_quality import geometry_signature
        h.update(geometry_signature(mesh.geometry()).encode())
        h.update(str(mesh.creator().worldTransform().asTuple()).encode())
    else:
        meta,frames=photo_dataset(d['dataset'],d.get('photo_transform'))
        h.update(json.dumps(meta,sort_keys=True).encode())
        for f in frames:
            p=Path(d['dataset'])/f['file_path'];st=p.stat();h.update(str((str(p),st.st_size,st.st_mtime_ns)).encode())
    return h.hexdigest()


def box(d,padded=False):
    c=np.array(d['center'],float);half=np.array(d['size'],float)*.5
    if padded:half+=d['feather_m']/d['units']
    return c-half,c+half


def influence(points,d):
    lo,hi=box(d);distance=np.max(np.maximum(lo-points,points-hi),axis=1);f=d['feather_m']/d['units']
    if not f:return (distance<=0).astype(float)
    t=np.clip(1-distance/f,0,1);return t*t*(3-2*t)


def write_ply(path,names,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if not len(rows) or not np.isfinite(rows).all():raise ValueError('Splat vide ou non fini ; écriture refusée.')
    header='ply\nformat binary_little_endian 1.0\ncomment Spirula local refinement\nelement vertex %d\n'%len(rows)
    header+=''.join('property float '+n+'\n' for n in names)+'end_header\n'
    temp=path.with_name('.partial_'+uuid.uuid4().hex[:8]+'_'+path.name)
    try:
        with temp.open('wb') as f:f.write(header.encode('ascii'));np.asarray(rows,dtype='<f4').tofile(f)
        temp.replace(path)
    finally:
        if temp.exists():temp.unlink()


def read_ply(path):
    with Path(path).open('rb') as f:
        names=[];count=None
        for _ in range(512):
            line=f.readline()
            if not line:raise ValueError('En-tête PLY tronqué.')
            t=line.decode('ascii').strip().split()
            if t[:2]==['format','binary_little_endian']:pass
            elif t[:1]==['format']:raise ValueError('Le raffinement nécessite un PLY 3DGS binaire little-endian.')
            elif t[:2]==['element','vertex']:count=int(t[2])
            elif t[:1]==['property']:
                if len(t)!=3 or t[1]!='float':raise ValueError('Schéma PLY : propriétés float requises.')
                names.append(t[2])
            elif t==['end_header']:break
        else:raise ValueError('En-tête PLY invalide.')
        if count is None or count<1 or len(names)!=len(set(names)):raise ValueError('Schéma PLY invalide.')
        rows=np.fromfile(f,dtype='<f4',count=count*len(names))
        if rows.size!=count*len(names) or not np.isfinite(rows).all():raise ValueError('Corps PLY tronqué ou non fini.')
        rows=rows.reshape(count,len(names))
    required=['x','y','z','opacity']+['scale_'+str(i) for i in range(3)]+['rot_'+str(i) for i in range(4)]+['f_dc_'+str(i) for i in range(3)]
    if any(n not in names for n in required):raise ValueError('Ce PLY ne contient pas tous les paramètres 3DGS.')
    return names,rows


def clip_triangles(records,lo,hi):
    """Clip polygons with interpolated attributes, rather than discard crossing faces."""
    p=records[:,:,:3];candidate=(p.max(axis=1)>=lo).all(axis=1)&(p.min(axis=1)<=hi).all(axis=1)
    result=[]
    for tri in records[candidate]:
        polygon=list(tri.astype(float))
        for axis in range(3):
            for bound,sign in ((lo[axis],1),(hi[axis],-1)):
                new=[]
                for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                    ia=(a[axis]-bound)*sign>=-1e-10;ib=(b[axis]-bound)*sign>=-1e-10
                    if ia:new.append(a)
                    if ia!=ib:new.append(a+(b-a)*((bound-a[axis])/(b[axis]-a[axis])))
                polygon=new
                if not polygon:break
            if not polygon:break
        for i in range(1,len(polygon)-1):result.append([polygon[0],polygon[i],polygon[i+1]])
    out=np.array(result,dtype=np.float32).reshape(-1,3,records.shape[2])
    if len(out):out=out[np.linalg.norm(np.cross(out[:,1,:3]-out[:,0,:3],out[:,2,:3]-out[:,0,:3]),axis=1)>1e-14]
    return out


def plan(d):
    from spirula_arch import pose
    from spirula_render import entry
    lo,hi=box(d,True);axis,sign=[(2,-1),(2,1),(0,-1),(0,1),(1,1),(1,-1)][d['axis']]
    other=[a for a in range(3) if a!=axis]
    if axis!=1:other=[a for a in other if a!=1]+[1]
    span=np.array([d['width'],d['height']])*d['pixel_m']/d['units'];dims=np.maximum(1,np.ceil((hi-lo)[other]/(span*.7)).astype(int))
    count=int(np.prod(dims))*5
    if count>d['max_views']:raise ValueError('%s vues de détail prévues, limite %s. Réduire la zone ou augmenter mètres/pixel.'%(count,d['max_views']))
    distance=span[0]/(2*math.tan(math.radians(55)/2));result=[]
    for i,j in itertools.product(range(dims[0]),range(dims[1])):
        target=(lo+hi)*.5;target[axis]=lo[axis] if sign<0 else hi[axis]
        target[other]=lo[other]+(hi-lo)[other]*(np.array([i,j])+.5)/dims
        for dx,dy in ((0,0),(-.16,0),(.16,0),(0,-.12),(0,.12)):
            pos=target.copy();pos[axis]+=sign*distance;pos[other]+=np.array([dx,dy])*distance
            v=entry(pose(pos,target,1 if axis!=1 else 2),d['width'],d['height'],55)
            v['file_path']='images/%05d.png'%len(result);result.append(v)
    return result


def photo_dataset(directory,transform=None):
    from PIL import Image
    root=Path(directory);p=root/'transforms.json'
    if p.is_file():meta=json.loads(p.read_text(encoding='utf-8'))
    else:
        from spirula_refine_colmap import read
        meta=read(root)
    frames=[]
    transform=json.loads(transform) if isinstance(transform,str) else transform
    matrix=np.array(transform,float).reshape(4,4).T if transform else np.eye(4)
    scale=float(np.linalg.norm(matrix[:3,0]));rot=matrix[:3,:3]/max(scale,1e-20)
    if not np.isfinite(matrix).all() or scale<=0 or not np.allclose(rot.T@rot,np.eye(3),atol=1e-5) or np.linalg.det(rot)<0 or not np.allclose(matrix[3],[0,0,0,1]):raise ValueError('La transformation du dataset doit être une similitude positive (pas de cisaillement).')
    if meta.get('applied_transform') is not None or meta.get('applied_scale',1)!=1:raise ValueError('Exporter les caméras dans le repère du PLY, sans applied_transform/applied_scale.')
    if meta.get('camera_model','OPENCV') not in ('OPENCV','PINHOLE'):raise ValueError('Des images perspective dédistordues sont requises.')
    for raw in meta.get('frames',[]):
        f={**{k:v for k,v in meta.items() if k!='frames'},**raw}
        if any(not np.isfinite(float(f.get(k,0))) for k in ('k1','k2','k3','k4','p1','p2')):raise ValueError('Distorsion caméra non finie.')
        m=np.array(f['transform_matrix'],float)
        if m.shape!=(4,4) or not np.isfinite(m).all() or not np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=1e-4) or not np.allclose(m[3],[0,0,0,1]):raise ValueError('Pose caméra non rigide ou invalide.')
        m[:3,3]=matrix[:3,:3]@m[:3,3]+matrix[:3,3];m[:3,:3]=rot@m[:3,:3]
        path=(root/f['file_path']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Les images doivent rester dans le dataset.')
        with Image.open(path) as image:
            w,h=image.size
        if w!=int(f.get('w',w)) or h!=int(f.get('h',h)):raise ValueError('Dimensions photo et intrinsèques différentes : '+str(path))
        fx=f.get('fl_x');fy=f.get('fl_y',fx)
        if fx is None or fy is None or min(fx,fy)<=0:raise ValueError('Intrinsèques fl_x/fl_y manquants.')
        frames.append(dict(file_path=f['file_path'],w=w,h=h,fl_x=fx,fl_y=fy,cx=f.get('cx',w/2),cy=f.get('cy',h/2),transform_matrix=m.tolist(),**{k:f[k] for k in ('k1','k2','k3','k4','p1','p2') if k in f}))
    if len(frames)<3:raise ValueError('Prévoir au moins trois photos avec leurs poses exactes.')
    return meta,frames


def cell_supported(old,new,spacing):
    """Conservative occupied-cell support; retain old splats in unobserved regions."""
    origin=np.min(new,axis=0);size=max(spacing*1.5,1e-10)
    a=np.floor((old-origin)/size).astype(np.int64);b=np.floor((new-origin)/size).astype(np.int64)
    dtype=np.dtype([('x','<i8'),('y','<i8'),('z','<i8')]);keys=np.unique(np.ascontiguousarray(b).view(dtype).ravel());keep=np.zeros(len(a),bool)
    for offset in itertools.product((-1,0,1),repeat=3):
        q=np.ascontiguousarray(a+offset).view(dtype).ravel();keep|=np.isin(q,keys)
    return keep


def photo_overlap(geometry,frames,d):
    p=np.frombuffer(geometry.pointFloatAttribValuesAsString('P'),dtype=np.float32).reshape(-1,3);p=p[influence(p,d)>0]
    if not len(p):raise ValueError('La zone ne contient aucun splat. Déplacer ou agrandir la boîte.')
    p=p[np.linspace(0,len(p)-1,min(len(p),4096),dtype=int)];visible=[]
    for f in frames:
        m=np.array(f['transform_matrix']);q=(p-m[:3,3])@m[:3,:3];z=-q[:,2];u=f['fl_x']*q[:,0]/np.maximum(z,1e-9)+f['cx'];v=-f['fl_y']*q[:,1]/np.maximum(z,1e-9)+f['cy'];visible.append(int(((z>0)&(u>=0)&(u<f['w'])&(v>=0)&(v<f['h'])).sum()))
    if sum(n>=min(4,len(p)) for n in visible)<3:raise ValueError('Moins de trois photos voient la zone. Vérifier les poses, le repère dataset → splat ou ajouter des vues.')
    return visible


def merge(base,patch,target,d,spacing,progress=lambda s:None,cancel=None):
    if cancel and Path(cancel).exists():raise InterruptedError('Raffinement arrêté avant assemblage.')
    names,old=read_ply(base);pn,new=read_ply(patch)
    extra=[n for n in pn if n not in names];allnames=names+extra
    def align(ns,rs):
        out=np.zeros((len(rs),len(allnames)),dtype=np.float32)
        for i,n in enumerate(ns):out[:,allnames.index(n)]=rs[:,i]
        return out
    old=align(names,old);new=align(pn,new);xyz=[allnames.index(k) for k in ('x','y','z')];alpha=allnames.index('opacity')
    ow=influence(old[:,xyz],d);nw=influence(new[:,xyz],d);new=new[nw>0];nw=nw[nw>0]
    if not len(new):raise ValueError('Aucune nouvelle gaussienne dans la zone ; résultat original conservé.')
    affected=np.flatnonzero(ow>0);supported=cell_supported(old[affected][:,xyz],new[:,xyz],spacing)
    keep_old=np.ones(len(old),bool);weights=np.ones(len(old));weights[affected[supported]]=1-ow[affected[supported]];keep_old=weights>1e-7
    untouched=ow==0
    def attenuate(rows,w):
        rows=rows.copy();a=1/(1+np.exp(-np.clip(rows[:,alpha],-30,30)));a=-np.expm1(w*np.log1p(-np.minimum(a,1-1e-7)));rows[:,alpha]=np.log(np.maximum(a,1e-12))-np.log1p(-np.minimum(a,1-1e-7));return rows
    # Do not even round-trip opacity for unchanged rows: byte-for-byte preservation.
    changed=(weights<1)&keep_old
    old[changed]=attenuate(old[changed],weights[changed]);new=attenuate(new,nw)
    merged=np.concatenate([old[keep_old],new]);progress('Assemblage : %s originales conservées + %s nouvelles'%(int(keep_old.sum()),len(new)))
    if cancel and Path(cancel).exists():raise InterruptedError('Raffinement arrêté avant publication.')
    write_ply(target,allnames,merged)
    return dict(original_count=len(old),output_count=len(merged),new_patch_count=len(new),removed_original_count=int((~keep_old).sum()),outside_region_unchanged=int(untouched.sum()),unobserved_original_retained=int((~supported).sum()),feather_m=d['feather_m'],method='Local replacement; original exterior unchanged; unobserved originals retained; optical-opacity feather')


def split_init(base,target,d):
    from spirula_ply import rotation
    names,rows=read_ply(base);xyz=[names.index(n) for n in ('x','y','z')];ss=[names.index('scale_'+str(i)) for i in range(3)];qq=[names.index('rot_'+str(i)) for i in range(4)]
    mask=influence(rows[:,xyz],d)>.999
    if not mask.any():raise ValueError('La zone ne contient aucune gaussienne à raffiner.')
    selected=rows[mask];factor=4 if d['split'] else 1
    if len(rows)+len(selected)*(factor-1)>d['patch_cap']:raise ValueError('Le budget total photo doit contenir le splat initial et les subdivisions de la zone.')
    if factor==1:write_ply(target,names,rows);return dict(split_parents=0,initial_count=len(rows))
    q=selected[:,qq][:,[1,2,3,0]];r=rotation(q);sc=np.exp(selected[:,ss]);tangent=np.argsort(sc,axis=1)[:,-2:];children=[]
    for a,b in itertools.product((-.45,.45),repeat=2):
        child=selected.copy();ids=np.arange(len(child));offset=a*r[ids,:,tangent[:,0]]*sc[ids,tangent[:,0],None]+b*r[ids,:,tangent[:,1]]*sc[ids,tangent[:,1],None]
        child[:,xyz]+=offset
        for k in range(2):child[ids,np.array(ss)[tangent[:,k]]]-=math.log(1.6)
        children.append(child)
    out=np.concatenate([rows[~mask]]+children);write_ply(target,names,out);return dict(split_parents=int(mask.sum()),initial_count=len(out),split_factor=factor)


def cancelled(folder):
    if (Path(folder)/'cancel.request').exists():raise InterruptedError('Raffinement arrêté ; source et rendus conservés.')


def visible_triangles(triangles,geo,views,origin,folder,status):
    """Discard wholly hidden faces before dense sampling. Final bake still tests
    every sample against the complete mesh; unsupported original splats survive.
    """
    import hou
    p=triangles[:,:,:3];center=p.mean(axis=1);samples=np.concatenate([center[:,None,:],p*.8+center[:,None,:]*.2],axis=1).reshape(-1,3);seen=np.zeros(len(samples),bool)
    ray=hou.sopNodeTypeCategory().nodeVerb('ray');ray.setParms({'method':1,'dirmethod':2,'dotrans':1,'newgrp':1,'hitgrp':'hits','rtolerance':1e-6});tolerance=max(1e-5,float(np.linalg.norm(np.ptp(p.reshape(-1,3),axis=0)))*1e-5)
    for i,v in enumerate(views):
        cancelled(folder);m=np.array(v['transform_matrix']);camera=m[:3,3]-origin;q=(samples-camera)@m[:3,:3];z=-q[:,2];u=v['fl_x']*q[:,0]/np.maximum(z,1e-9)+v['cx'];y=-v['fl_y']*q[:,1]/np.maximum(z,1e-9)+v['cy'];ids=np.flatnonzero((~seen)&(z>0)&(u>=0)&(u<v['w'])&(y>=0)&(y<v['h']))
        if len(ids):
            direction=samples[ids]-camera;direction/=np.maximum(np.linalg.norm(direction,axis=1)[:,None],1e-15);rays=hou.Geometry();rays.createPoints(np.repeat(camera[None],len(ids),axis=0).tolist());rays.addAttrib(hou.attribType.Point,'N',(0.,0.,-1.));rays.setPointFloatAttribValuesFromString('N',direction.astype(np.float32).tobytes());out=hou.Geometry();ray.execute(out,[rays,geo]);hit=np.array(out.pointFloatAttribValues('P')).reshape(-1,3);seen[ids]=np.linalg.norm(hit-samples[ids],axis=1)<tolerance
        status('training','Préparation des surfaces visibles : %s / %s'%(i+1,len(views)),step=i+1,steps=len(views))
    return seen.reshape(-1,4).any(axis=1)


def sample_surface(triangles,spacing,limit,target,progress=lambda m:None):
    """World-aligned face lattices plus edge coverage. Density depends on area,
    without exploding recursive subdivision on long, very thin triangles.
    """
    from spirula_object import FIELDS,quaternion_from_matrix
    points=[];normals=[];total=0
    for i,record in enumerate(triangles):
        p=record[:,:3].astype(float);n=np.cross(p[1]-p[0],p[2]-p[0]);length=np.linalg.norm(n)
        if length<1e-16:continue
        n/=length;drop=int(np.argmax(np.abs(n)));axes=[a for a in range(3) if a!=drop];uv=p[:,axes];step=spacing*math.sqrt(abs(n[drop]));lo=np.ceil(uv.min(0)/step).astype(int);hi=np.floor(uv.max(0)/step).astype(int);dim=np.maximum(0,hi-lo+1)
        if int(np.prod(dim))>limit*8:raise ValueError('Une face dépasse le budget du patch ; augmenter mètres/pixel ou réduire la zone.')
        pieces=[]
        if min(dim)>0:
            u,v=np.meshgrid(np.arange(lo[0],hi[0]+1)*step,np.arange(lo[1],hi[1]+1)*step);q=np.stack([u.ravel(),v.ravel()],axis=1);a=uv[1]-uv[0];b=uv[2]-uv[0];det=a[0]*b[1]-a[1]*b[0];delta=q-uv[0];s=(delta[:,0]*b[1]-delta[:,1]*b[0])/det;t=(a[0]*delta[:,1]-a[1]*delta[:,0])/det;keep=(s>=-1e-8)&(t>=-1e-8)&(s+t<=1+1e-8);q=q[keep];p3=np.empty((len(q),3));p3[:,axes]=q;p3[:,drop]=p[0,drop]-((q-p[0,axes])@n[axes])/n[drop];pieces.append(p3)
        # A lattice can miss narrow mouldings entirely; follow their edges too.
        center=p.mean(0)
        for a,b in ((p[0],p[1]),(p[1],p[2]),(p[2],p[0])):
            count=max(1,int(math.ceil(np.linalg.norm(b-a)/spacing)));t=(np.arange(count)+.5)/count;q=a+(b-a)*t[:,None];pieces.append(q*.98+center*.02)
        pieces.append(center[None]);sample=np.concatenate(pieces);points.append(sample);normals.append(np.broadcast_to(n,sample.shape).copy());total+=len(sample)
        if total>limit*8:raise ValueError('Surface trop dense pour ce budget. Augmenter mètres/pixel ou réduire la zone.')
        if i%100==0:progress('Échantillonnage visible : face %s / %s'%(i+1,len(triangles)))
    if not points:raise ValueError('Aucune surface échantillonnable.')
    points=np.concatenate(points);normals=np.concatenate(normals)
    # Deduplicate shared triangle edges, retaining distinct opposite surfaces.
    keys=np.concatenate([np.round(points/(spacing*.3)).astype(np.int64),np.round(normals*1000).astype(np.int64)],axis=1);_,ids=np.unique(keys,axis=0,return_index=True);ids=np.sort(ids);points=points[ids];normals=normals[ids]
    if len(points)>limit:raise ValueError('%s gaussiennes nécessaires, budget %s. Augmenter le budget ou mètres/pixel.'%(len(points),limit))
    reference=np.eye(3)[np.argmin(np.abs(normals),axis=1)];tangent=np.cross(reference,normals);tangent/=np.linalg.norm(tangent,axis=1)[:,None];bitangent=np.cross(normals,tangent);frames=np.stack([tangent,bitangent,normals],axis=2)
    rows=np.zeros((len(points),len(FIELDS)),np.float32);rows[:,:3]=points;rows[:,3:6]=normals;rows[:,54]=math.log(.995/.005);rows[:,55:58]=np.log([spacing*.7,spacing*.7,spacing*.02]);rows[:,58:62]=quaternion_from_matrix(frames)[:,[3,0,1,2]];write_ply(target,FIELDS,rows)
    return dict(gaussians=len(points),source_triangles=len(triangles),spacing_world=spacing,method='Projected face lattices, narrow-edge coverage, shared-edge deduplication')


def surface_worker(data,folder,status):
    import hou
    import spirula_object as obj
    from spirula_surface_bake import bake
    d=data['refine_settings'];source_node=hou.node(d['mesh']);captured=obj.capture(source_node)
    world=np.array(source_node.creator().worldTransform().asTuple()).reshape(4,4);captured['triangles'][:,:,:3]=captured['triangles'][:,:,:3]@world[:3,:3]+world[3,:3]
    lo,hi=box(d,True);captured['triangles']=clip_triangles(captured['triangles'],lo,hi)
    if not len(captured['triangles']):raise ValueError('La zone ne coupe aucune surface du mesh de référence.')
    captured['triangles'][:,:,:3]-=np.array(data['training_origin'])
    geo=hou.Geometry();geo.merge(source_node.geometry());geo.transform(source_node.creator().worldTransform()*hou.hmath.buildTranslate(tuple(-np.array(data['training_origin']))))
    before=len(captured['triangles']);visible=visible_triangles(captured['triangles'],geo,data['views'],np.array(data['training_origin']),folder,status);captured['triangles']=captured['triangles'][visible]
    if not len(captured['triangles']):raise ValueError('Aucune surface de la zone n’est visible depuis les nouvelles caméras.')
    tri=captured['triangles'];captured['area']=float(np.linalg.norm(np.cross(tri[:,1,:3]-tri[:,0,:3],tri[:,2,:3]-tri[:,0,:3]),axis=1).sum()/2);captured['ids']=np.zeros(len(tri),np.int32)
    captured['materials']=[{'color':np.ones(3),'texture':None,'name':'Karma radiance'}]
    spacing=2*d['pixel_m']/d['units'];init=folder/'patch_initial.ply'
    (folder/'sampling_plan.json').write_text(json.dumps(dict(clipped_triangles=before,visible_triangles=len(tri),visible_area=captured['area'],spacing=spacing,budget=d['patch_cap']),indent=2))
    cancelled(folder);status('training','Subdivision locale du mesh…',step=0,steps=len(data['views']))
    sampling=sample_surface(captured['triangles'],spacing,d['patch_cap'],init,progress=lambda m:(cancelled(folder),status('training',m,step=0,steps=len(data['views']))))
    transforms=json.loads((folder/'transforms.json').read_text());patch=folder/'patch.ply';step=0
    def progress(message):
        nonlocal step
        cancelled(folder);step+=1;status('training',message,step=step,steps=len(transforms['frames']),rendered=len(transforms['frames']),total=len(transforms['frames']))
    report=bake(init,geo,transforms,folder,patch,progress,use_exr=True,color_metadata=data)
    names,rows=read_ply(patch);rows[:,:3]+=np.array(data['training_origin']);write_ply(patch,names,rows)
    report.update(sampling=sampling,requested_spacing_world=spacing,source='New close-up Karma EXRs + known geometry',not_sugar_milo_or_2dgs=True,pre_visibility=dict(before=before,after=int(visible.sum())))
    return patch,spacing,report


def photo_worker(data,folder,status):
    from PIL import Image
    d=data['refine_settings'];_,frames=photo_dataset(d['dataset'],d.get('photo_transform'));images=folder/'images';images.mkdir(exist_ok=True);output_frames=[]
    # Keep full image context for correct occlusion. Only the merged ROI is published.
    for i,f in enumerate(frames):
        cancelled(folder);src=Path(d['dataset'])/f['file_path'];dst=images/('%05d'%i+src.suffix.lower())
        if not dst.exists():shutil.copy2(src,dst)
        output_frames.append(dict(f,file_path='images/'+dst.name))
    (folder/'transforms.json').write_text(json.dumps({'camera_model':'OPENCV','frames':output_frames}),encoding='utf-8')
    init=folder/'refine_initial.ply';split=split_init(data['base_ply'],init,d);run=folder/'training'/'run'
    # The engine builds ROI pixel masks from dataset seed points, even when
    # --init-ply supplies the actual Gaussians. Never let it use random seeds.
    names,seedrows=read_ply(init);inside=np.flatnonzero(influence(seedrows[:,:3],d)>0);outside=np.flatnonzero(influence(seedrows[:,:3],d)==0)
    def sample(ids,n):return ids[np.linspace(0,len(ids)-1,min(len(ids),n),dtype=int)] if len(ids) else ids
    chosen=np.concatenate([sample(inside,50000),sample(outside,50000)]);seedrows=seedrows[chosen]
    seed=folder/'roi_seed.ply';seeddata=np.zeros(len(seedrows),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
    for k in ('x','y','z'):seeddata[k]=seedrows[:,names.index(k)]
    for i,k in enumerate(('red','green','blue')):seeddata[k]=np.clip((.5+.28209479177387814*seedrows[:,names.index('f_dc_'+str(i))])*255,0,255).astype(np.uint8)
    seed.write_bytes(('ply\nformat binary_little_endian 1.0\nelement vertex %d\n'%len(seeddata)+''.join('property float '+k+'\n' for k in ('x','y','z'))+''.join('property uchar '+k+'\n' for k in ('red','green','blue'))+'end_header\n').encode()+seeddata.tobytes())
    cmd=[data['executable'],'train','synthetic','--data',str(folder),'--data-format','nerfstudio','--output-dir-prefix',str(run.parent),'--output-dir-name','run','--init-ply',str(init),'--num-iterations',str(d['iterations']),'--cap-max',str(d['patch_cap']),'--primitive','3dgs','--sh-degree','3','--train-resolution-divisor','1','--progressive-resolution','0','--disable-viewer','1','--keep-viewer-alive','0','--save-full-checkpoint','1','--orientation-method','none','--center-method','none','--auto-scale-poses','0','--scene-center','none','--device','auto','--eval-lpips','0','--eval-mode','all']
    lo,hi=box(d,True);roi=folder/'roi.json';roi.write_text(json.dumps(dict(type='box',center=((lo+hi)/2).tolist(),half=((hi-lo)/2).tolist())),encoding='utf-8')
    cmd+=['--seed-pointcloud',str(seed),'--roi-region',str(roi),'--roi-outside-weight','0.0001','--roi-outside-opacity-decay','1','--roi-mask-pixels','1']
    # Appearance refinement starts from an existing shape: the reconstruction
    # preset's large random MCMC motion can turn a flat detailed patch into fog.
    cmd+=['--noise-lr','0','--noise-lr-final','0','--means-lr','0.00002','--means-lr-final','0.000001','--background-noise-warmup','0','--warp-to-pinhole','1']
    (folder/'training_command.json').write_text(json.dumps(cmd,indent=2))
    env=os.environ.copy();env['SS_NO_AUTO_FETCH']='1';status('training','Réapprentissage depuis le PLY, photos à résolution native…',step=0,steps=d['iterations'])
    with (folder/'training.log').open('ab',buffering=0) as log:
        process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            while process.poll() is None:
                cancelled(folder)
                import re
                from spirula_monitor import tail
                logtext=tail(folder/'training.log');steps=re.findall(r'(?:step|étape)\s+(\d+)\s*/\s*(\d+)',logtext,re.I)
                if ('100 % des pixels écartés' in logtext or '100% of pixels' in logtext):raise ValueError('Le masque de zone exclut toutes les images. Vérifier alignement et profondeur de la zone.')
                if steps:status('training','Raffinement photo : %s / %s'%steps[-1],step=int(steps[-1][0]),steps=int(steps[-1][1]))
                time.sleep(.5)
            if process.returncode:raise RuntimeError('Raffinement Spirula en échec ; voir training.log (code %s).'%process.returncode)
        finally:
            if process.poll() is None:process.terminate();process.wait()
    outputs=list(run.glob('step-*.ckpt/splat.ply'))
    if not outputs:raise RuntimeError('Le trainer n’a pas produit de PLY.')
    result=max(outputs,key=lambda p:p.stat().st_mtime_ns);names,rows=read_ply(result);mask=influence(rows[:,:3],d)>0;patch=folder/'patch.ply';write_ply(patch,names,rows[mask])
    # Match the spatial support to the trained local Gaussian footprint.
    spacing=float(np.median(np.exp(rows[mask][:,[names.index('scale_'+str(i)) for i in range(3)]]).max(axis=1)))
    return patch,max(spacing,1e-8),dict(method='Native Spirula --init-ply, local initial subdivision, original-resolution photos, native ROI loss mask; final ROI replacement',split=split,frames=len(frames),quality_guaranteed=False)


def worker(data,folder,status):
    folder=Path(folder)
    try:
        cancelled(folder)
        patch,spacing,report=surface_worker(data,folder,status) if data['refine_settings']['method']==0 else photo_worker(data,folder,status)
        result=folder/'refined.ply';status('training','Assemblage local ; conservation du reste du splat…',step=0,steps=1)
        report['merge']=merge(data['base_ply'],patch,result,data['refine_settings'],spacing,cancel=folder/'cancel.request')
        report.update(version=VERSION,base_ply=data['base_ply'],output=str(result),settings=data['refine_settings'],signature=data['refinement']['signature'],automatic_quality_approval=False)
        (folder/'refinement_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        status('done','Candidat chargé. Comparer Avant / Après avant de valider.',result=str(result),rendered=len(data['views']),total=len(data['views']))
    except InterruptedError as exc:status('cancelled',str(exc))


def request(node,kind):
    import hou
    import PyOpenColorIO as ocio
    import spirula_render as render
    ns=nodes(node);z=ns['refine_zone'];d=settings(node);sig=signature(node,'renders' if kind=='renders' else 'all');cap=ns['refine_renders' if kind=='renders' else 'refine_apply'].node('CAPTURE')
    if kind=='renders' and d['method']==1:
        meta,frames=photo_dataset(d['dataset'],d.get('photo_transform'));photo_overlap(source(node).geometry(),frames,d);remember(ns['refine_renders'],signature=sig,photos_verified=True);message='%s photos et métadonnées vérifiées. Contrôler leur alignement au PLY avant raffinement.'%len(frames);ns['refine_renders'].parm('status').set(message)
        from spirula_monitor import OVERRIDES,update_node
        done=dict(phase='done',message=message,started=time.time(),finished=time.time(),active=False);OVERRIDES[cap.sessionId()]=done;update_node(cap,done);return None
    if kind=='apply':
        old=state(ns['refine_renders'])
        if old.get('signature')!=signature(node,'renders'):raise ValueError('Produire ou vérifier les images de détail avec les réglages actuels avant de raffiner.')
    folder=Path(d['workspace'])/(('detail_' if kind=='renders' else 'refine_')+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True,exist_ok=True)
    snapshot=folder/'scene_snapshot.hip';original=hou.hipFile.name();hip=hou.getenv('HIP')
    try:hou.hipFile.save(str(snapshot),save_to_recent_files=False)
    finally:hou.hipFile.setName(original);hou.putenv('HIP',hip)
    from spirula_ply import write_geometry
    base=folder/'original.ply';write_geometry(source(node).geometry(),base,linearized=True)
    config=ocio.GetCurrentConfig();origin=np.array(d['center']);views=plan(d) if d['method']==0 else photo_dataset(d['dataset'],d.get('photo_transform'))[1]
    data=dict(schema=1,folder=str(folder.resolve()),snapshot=str(snapshot.resolve()),original_hip=hip,original_scene_name=original,frame=hou.frame(),views=views,source=d['mesh'] if d['method']==0 else '',objects='*',isolate=False,backend=3,lop_source=d['lop_source'],render_settings='',studio_lights=False,width=d['width'],height=d['height'],samples=d['samples'],exposure=0,hdr=False,iterations=d['iterations'],cap=d['patch_cap'],executable=str(__import__('spirula_runtime').candidate_engine()),primitive='3dgs',train=False,training_seed=d['mesh'],device='auto',ocio=hou.getenv('OCIO'),working_space=config.getRoleColorSpace(ocio.ROLE_SCENE_LINEAR),display=config.getDefaultDisplay(),view=config.getDefaultView(config.getDefaultDisplay()),training_origin=origin.tolist(),output_transform=[],rebase_usd=True,clip_range=[max(1e-7,d['pixel_m']/d['units']*.001),max(100,float(np.linalg.norm(d['size']))*100)],base_ply=str(base.resolve()),refine_settings=d,refinement=dict(stage=node.path(),kind=kind,signature=sig))
    if kind=='apply':
        data['refinement_worker']=True
        if d['method']==0:
            job=Path(state(ns['refine_renders'])['job']);previous=json.loads(job.read_text());data.update(training_origin=previous['training_origin'],views=previous['views'])
            shutil.copy2(job.parent/'transforms.json',folder/'transforms.json')
            for directory in ('images','renders'):
                (folder/directory).mkdir()
                for p in (job.parent/directory).iterdir():
                    if p.is_file():
                        try:os.link(p,folder/directory/p.name)
                        except OSError:shutil.copy2(p,folder/directory/p.name)
    path=folder/'job.json';render.atomic_json(path,data);cap.parm('jobfile').set(str(path));cap.setUserData('spirula_refine_owner',node.path());remember(node,job=str(path),pending_signature=sig)
    if kind=='apply':remember(node,candidate=None,accepted=False)
    return render.start(cap,train=False,resume=True)


def completed(capture,result,data):
    import hou
    item=data['refinement'];node=hou.node(item['stage'])
    if node is None:return
    remember(node,job=str(Path(data['folder'])/'job.json'),signature=item['signature'])
    if item['kind']=='apply':
        remember(node,candidate=result['result'],accepted=False);ns=nodes(node);ns['refine_check'].parm('compare').set(1);ns['refine_check'].cook(force=True);ns['refine_check'].setDisplayFlag(True);ns['refine_check'].setRenderFlag(True)
        node.parm('status').set('Candidat disponible. Comparer puis valider dans le node suivant.')
    else:node.parm('status').set('Vues rapprochées terminées. Continuer au raffinement.')


def geometry(node,role):
    import hou
    ns=nodes(node.parent());out=node.geometry();out.clear();src=source(node.parent())
    if role in ('refine_apply','refine_check') and state(ns['refine_apply']).get('candidate'):
        if state(ns['refine_apply']).get('signature')!=signature(node.parent()):raise hou.NodeError('Zone, source ou images modifiées : recalculer le raffinement. Le candidat précédent reste sur disque.')
        if role=='refine_apply' or ns['refine_check'].evalParm('compare')==1:out.merge(ns['refine_apply'].node('CAPTURE').geometry());return
    out.merge(src.geometry())
    if role=='refine_zone' and ns['refine_zone'].evalParm('guides'):
        d=settings(node.parent());lo,hi=box(d);pts=out.createPoints(list(itertools.product(*zip(lo,hi))))
        if not out.findPointAttrib('Cd'):out.addAttrib(hou.attribType.Point,'Cd',(1.,1.,1.))
        for p in pts:p.setAttribValue('Cd',(1.,.5,.05))
        for i in range(8):
            for bit in (1,2,4):
                j=i^bit
                if j>i:line=out.createPolygon(is_closed=False);line.addVertex(pts[i]);line.addVertex(pts[j])


def ensure_exportable(node):
    ns=nodes(node);apply=ns['refine_apply']
    if not state(apply).get('candidate'):return
    if state(apply).get('signature')!=signature(node):raise ValueError('Le raffinement ne correspond plus aux réglages actuels.')
    if ns['refine_check'].evalParm('compare')!=1:raise ValueError('Afficher Après avant d’exporter le raffinement.')
    if not state(apply).get('accepted'):raise ValueError('Comparer puis valider le candidat dans Contrôle du raffinement avant export.')


def action(node,command):
    import hou
    import spirula_render as render
    import spirula_monitor as monitor
    ns=nodes(node)
    try:
        if command in ('renders','apply'):
            if any(ns[r].node('CAPTURE').sessionId() in render.JOBS or ns[r].node('CAPTURE').sessionId() in monitor.PENDING for r in ('refine_renders','refine_apply')):raise ValueError('Un calcul de détail est déjà actif.')
            cap=ns['refine_renders' if command=='renders' else 'refine_apply'].node('CAPTURE');cap.setUserData('spirula_refine_owner',node.path());return monitor.launch(cap,lambda:request(node,command),'Préparation du raffinement local…')
        if command in ('monitor','stop'):
            cap=node.node('CAPTURE');return monitor.show(cap) if command=='monitor' else render.stop(cap)
        if command=='plan':
            d=settings(node);views=plan(d) if d['method']==0 else photo_dataset(d['dataset'],d.get('photo_transform'))[1];node.parm('status').set('%s vues · précision demandée %.3g mm/px · aucun détail inventé'%(len(views),1000*d['pixel_m']));node.setDisplayFlag(True);return views
        if command=='fit':
            p=np.array(source(node).geometry().pointFloatAttribValues('P')).reshape(-1,3);ns['refine_zone'].parmTuple('center').set(((p.min(0)+p.max(0))/2).tolist());ns['refine_zone'].parmTuple('size').set(np.maximum(np.ptp(p,axis=0),.01/settings(node)['units']).tolist());return
        if command=='select':
            viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if viewer is None:raise ValueError('Ouvrir un Scene View.')
            src=source(node);src.setDisplayFlag(True);selection=viewer.selectGeometry(prompt='Sélectionner les points de la zone à améliorer, puis Entrée',geometry_types=(hou.geometryType.Points,),use_existing_selection=False,allow_obj_sel=False)
            if selection is None:return
            positions=[]
            for path,sel in zip(selection.nodes(),selection.selections()):
                if path!=src:raise ValueError('Sélectionner les points du splat source de ce module.')
                positions.extend(tuple(p.position()) for p in sel.points(src.geometry()))
            if not positions:raise ValueError('Aucun point sélectionné.')
            p=np.array(positions);unit=settings(node)['units'];z=ns['refine_zone'];z.parmTuple('center').set(((p.min(0)+p.max(0))/2).tolist());z.parmTuple('size').set(np.maximum(np.ptp(p,axis=0),.02/unit).tolist());z.setDisplayFlag(True);return
        if command=='accept':
            a=ns['refine_apply']
            if not state(a).get('candidate') or state(a).get('signature')!=signature(node):raise ValueError('Générer le candidat actuel avant validation.')
            if ns['refine_check'].evalParm('compare')!=1:raise ValueError('Afficher Après pour valider le candidat.')
            remember(a,accepted=True);node.parm('status').set('Raffinement validé. L’export utilise le candidat affiché.');return
        if command=='export':
            ensure_exportable(node)
            from spirula_ply import write_geometry
            path=Path(node.evalParm('exportfile'));path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name('.partial_'+uuid.uuid4().hex[:8]+'_'+path.name)
            src=source(node)
            if src.parm('splatfile') and Path(src.evalParm('splatfile')).resolve()==path.resolve():raise ValueError('Choisir un autre fichier que le PLY original.')
            try:write_geometry(ns['refine_check'].geometry(),temp,linearized=True);temp.replace(path)
            finally:
                if temp.exists():temp.unlink()
            node.parm('status').set('Splat raffiné exporté : '+str(path));return str(path)
        if command=='next':
            role=node.userData('spirula_refine_role');i=ROLES.index(role)
            if i+1<len(ROLES):ns[ROLES[i+1]].setCurrent(True,clear_all_selected=True)
            elif node.outputs():node.outputs()[0].setCurrent(True,clear_all_selected=True)
            return
    except Exception as exc:
        node.parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def create(selected=None):
    import hou
    selected=selected or next(iter(hou.selectedNodes()),None)
    if selected is None or not isinstance(selected,hou.SopNode):raise ValueError('Sélectionner la sortie SOP du splat à améliorer.')
    parent=selected.parent();identifier=uuid.uuid4().hex;created={};names=('06A_ZONE_DETAIL','06B_IMAGES_DETAIL','06C_RAFFINEMENT','06D_CONTROLE_DETAIL')
    old_outputs=selected.outputs()
    existing=next((n for n in old_outputs if n.userData('spirula_refine_role')=='refine_zone'),None)
    if existing is not None:existing.setCurrent(True,clear_all_selected=True);return nodes(existing)
    for i,(role,name) in enumerate(zip(ROLES,names)):
        n=parent.createNode('spirula::'+role+'::1.0',name);n.setUserData('spirula_refine_role',role);n.setUserData('spirula_refine_id',identifier);n.setPosition(selected.position()+hou.Vector2(0,-2.5*(i+1)));n.setColor(hou.Color((.52,.36,.68)));n.setInput(0,selected if i==0 else created[ROLES[i-1]]);created[role]=n
    for output in old_outputs:
        if output.userData('spirula_arch_role')=='export':output.setInput(0,created['refine_check']);output.setPosition(created['refine_check'].position()+hou.Vector2(0,-2.5))
    zone=created['refine_zone'];zone.parm('workspace').set('$HIP/Projets/Raffinement_'+identifier[:6]);created['refine_check'].parm('exportfile').set('$HIP/splat_raffine.ply')
    if parent.userData('spirula_arch'):
        import spirula_arch as a
        from pxr import UsdGeom
        an=a.nodes(parent);zone.parm('mesh').set(an['source'].node('SEED_NATIVE').path());zone.parm('lop_source').set(an['source'].evalParm('lop_source'));zone.parm('workspace').set(an['source'].evalParm('workspace')+'/05_raffinement')
        try:zone.parm('units').set(UsdGeom.GetStageMetersPerUnit(a.scene(parent)[1]))
        except ValueError:pass
    capture=an['train'].node('CAPTURE') if parent.userData('spirula_arch') else selected
    if capture.parm('jobfile'):
        try:
            job=json.loads(Path(capture.evalParm('jobfile')).read_text());dataset=Path(job['folder'])
            if (dataset/'transforms.json').is_file():
                camera_transform=capture.evalParm('result_transform') if capture.parm('result_transform') else '[]'
                if parent.userData('spirula_arch'):camera_transform=json.dumps(job.get('output_transform',json.loads(camera_transform)))
                zone.parm('dataset').set(str(dataset));zone.parm('photo_transform').set(camera_transform)
        except (OSError,ValueError,KeyError):pass
    if capture.parm('splatfile'):
        original=Path(capture.evalParm('splatfile'))
        for output in old_outputs:
            if output.userData('spirula_arch_role')=='export':
                target=Path(output.evalParm('exportfile'))
                if original.is_file() and target.is_file() and original.samefile(target):
                    output.parm('exportfile').deleteAllKeyframes();output.parm('exportfile').set(str(target.with_name(target.stem+'_raffine'+target.suffix)))
    zone.setCurrent(True,clear_all_selected=True);zone.setDisplayFlag(True);return created
