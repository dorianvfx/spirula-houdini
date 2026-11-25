"""Local architectural surface completion. Hidden content is estimated, not recovered."""
import hashlib
import json
from pathlib import Path
import uuid
import numpy as np


def nearest(query,donors,k=4):
    """Bounded-memory numpy fallback, including installations without scipy."""
    result=[];distances=[];k=min(k,len(donors))
    if not k:raise ValueError('Aucun point de référence pour le raccord.')
    for start in range(0,len(query),128):
        d=np.sum((query[start:start+128,None,:]-donors[None,:,:])**2,axis=2)
        ids=np.argpartition(d,k-1,axis=1)[:,:k];result.append(ids);distances.append(np.take_along_axis(d,ids,axis=1))
    return np.concatenate(result),np.sqrt(np.concatenate(distances))


def fit_planes(points,threshold,max_planes=2,min_support=50):
    points=np.asarray(points,dtype=float);rng=np.random.default_rng(42);remaining=np.arange(len(points));planes=[]
    if len(points)>8000:remaining=rng.choice(remaining,8000,replace=False)
    for unused in range(max_planes):
        p=points[remaining];best=None;best_count=0
        if len(p)<min_support:break
        for trial in range(180):
            q=p[rng.choice(len(p),3,replace=False)];normal=np.cross(q[1]-q[0],q[2]-q[0]);length=np.linalg.norm(normal)
            if length<1e-12:continue
            normal/=length;mask=np.abs((p-q[0])@normal)<threshold;count=int(mask.sum())
            if count>best_count:best_count=count;best=mask
        if best is None or best_count<min_support:break
        support=p[best];center=np.median(support,axis=0);axes=np.linalg.svd(support-center,full_matrices=False)[2];normal=axes[-1]
        # Deterministic sign and plane frame.
        if normal[np.argmax(np.abs(normal))]<0:normal=-normal
        u=np.cross(normal,np.eye(3)[np.argmin(np.abs(normal))]);u/=np.linalg.norm(u);v=np.cross(normal,u)
        residual=np.abs((p-center)@normal);mask=residual<threshold
        support_ids=remaining[mask];support=points[support_ids]
        uv=(support-center)@np.stack([u,v],axis=1)
        if np.min(np.ptp(uv,axis=0))<threshold*3:remaining=remaining[~mask];continue
        planes.append(dict(center=center,u=u,v=v,normal=normal,ids=support_ids,rms=float(np.sqrt(np.mean(residual[mask]**2)))))
        remaining=remaining[~mask]
    return planes


def complete(clean,colors,removed,threshold=.02,spacing=.04,radius=1.,max_planes=2,max_cells=30000,color_mode=0,progress=None):
    if not len(removed):raise ValueError('02A : sélectionner les points de l’objet à retirer avant d’estimer le fond.')
    if threshold<=0 or spacing<=0 or radius<=0:raise ValueError('Tolérance, détail et voisinage doivent être positifs.')
    lo=removed.min(axis=0);hi=removed.max(axis=0)
    local=np.all((clean>=lo-radius)&(clean<=hi+radius),axis=1)&np.isfinite(clean).all(axis=1)&np.isfinite(colors).all(axis=1)
    local_ids=np.flatnonzero(local);p=clean[local];c=colors[local]
    planes=fit_planes(p,threshold,max_planes=max_planes)
    if not planes:raise ValueError('Aucun plan suffisamment étayé. Élargir le voisinage, ajuster la tolérance ou utiliser la surface manuelle.')
    quads=[];quad_colors=[];reports=[];used=0
    for i,plane in enumerate(planes):
        center=plane['center'];normal=plane['normal'];axes=np.stack([plane['u'],plane['v']],axis=1)
        # Project only the removed region, never a whole-room extrapolation.
        projected=(removed-center)@axes;low=projected.min(axis=0);high=projected.max(axis=0)
        if np.min(high-low)<spacing:continue
        dims=np.maximum(1,np.ceil((high-low)/spacing).astype(int))
        if int(np.prod(dims))+used>max_cells:raise ValueError('Réparation trop dense. Augmenter le pas ou réduire la sélection (limite %s cellules).'%max_cells)
        cell=(high-low)/dims;xx,yy=np.meshgrid(np.arange(dims[0]),np.arange(dims[1]),indexing='ij');uv=low+(np.stack([xx.ravel(),yy.ravel()],axis=1)+.5)*cell
        centers=center+uv@axes.T
        # Keep any captured support in place: do not overlay cells already observed.
        # Test preservation against every local point on this plane, before donor subsampling.
        all_on_plane=p[np.abs((p-center)@normal)<threshold]
        occupied_uv=(all_on_plane-center)@axes
        occupied_index=np.floor((occupied_uv-low)/cell).astype(int)
        occupied_index=occupied_index[np.all((occupied_index>=0)&(occupied_index<dims),axis=1)]
        occupied=np.zeros(tuple(dims),dtype=bool)
        if len(occupied_index):occupied[occupied_index[:,0],occupied_index[:,1]]=True
        ids=plane['ids'];donors=p[ids];donor_colors=c[ids];donor_uv=(donors-center)@axes
        if len(donors)>2000:
            chosen=np.random.default_rng(42).choice(len(donors),2000,replace=False);donors=donors[chosen];donor_colors=donor_colors[chosen];donor_uv=donor_uv[chosen]
        neighbors,distance=nearest(uv,donor_uv,4)
        keep=(np.min(distance,axis=1)>spacing*.9)&~occupied.ravel()
        # Within projected support rectangle only. Unsupported sides must be modelled manually.
        support_lo=donor_uv.min(axis=0);support_hi=donor_uv.max(axis=0)
        keep &= np.all((uv>=support_lo)&(uv<=support_hi),axis=1)
        if not keep.any():continue
        corners=np.array([[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]])*cell
        cell_uv=uv[keep,None,:]+corners[None,:,:]
        vertices=center+cell_uv@axes.T
        if color_mode==1:
            nearest_id=neighbors[np.arange(len(neighbors)),np.argmin(distance,axis=1)];color=donor_colors[nearest_id][keep]
        else:
            weights=1/np.maximum(distance,spacing*.1)**2;weights/=weights.sum(axis=1,keepdims=True)
            color=np.sum(donor_colors[neighbors]*weights[:,:,None],axis=1)[keep]
        # Constant per-cell colour preserves discontinuities better than mixing unrelated planes.
        quads.append(vertices);quad_colors.append(np.repeat(color[:,None,:],4,axis=1));used+=len(vertices)
        reports.append(dict(plane=i,support_count=len(ids),rms=plane['rms'],normal=normal.tolist(),center=center.tolist(),cells=len(vertices),max_color_extrapolation=float(distance[keep].min(axis=1).max()),captured_points_preserved=True))
        if progress:progress((i+1)/len(planes))
    if not quads:raise ValueError('Aucune zone manquante estimable dans l’emprise sélectionnée. Vérifier la sélection et les surfaces de référence.')
    return np.concatenate(quads),np.concatenate(quad_colors),dict(planes=reports,cells=used,local_support_points=len(local_ids),appearance='Interpolation de couleurs du scan, sans récupération photographique ni reflets appris.',geometry='Prolongement de plans estimés, pas une mesure des surfaces cachées.')


def fingerprint(node):
    import spirula_quality
    digest=hashlib.sha256()
    for source in node.inputs()[:2]:
        if source is None:raise ValueError('Brancher le scan nettoyé et la sélection sur 02C.')
        geo=source.geometry();digest.update(spirula_quality.geometry_signature(geo).encode())
        group=geo.findPointGroup('spirula_remove')
        if group:digest.update(np.asarray([p.number() for p in group.points()],dtype=np.int64).tobytes())
    digest.update(str([node.evalParm(p) for p in ('threshold','spacing','radius','planes','max_cells','color_mode')]).encode())
    return digest.hexdigest()


def evaluate(node):
    import hou
    out=node.geometry();out.clear();stage=node.parent();cache=stage.evalParm('cache')
    if not cache:return
    if stage.userData('repair_signature')!=fingerprint(stage):raise hou.NodeError('Réparation périmée : recalculer 02C après modification du scan, de la sélection ou des paramètres.')
    out.loadFromFile(cache)


def estimate(node):
    import hou,spirula_chain
    node.parm('status').set('Estimation en cours…')
    clean=node.inputs()[0].geometry();selection=node.inputs()[1].geometry();group=selection.findPointGroup('spirula_remove')
    removed=np.array([p.position() for p in group.points()],dtype=float) if group else np.empty((0,3))
    points=np.frombuffer(clean.pointFloatAttribValuesAsString('P'),dtype=np.float32).reshape(-1,3)
    if not clean.findPointAttrib('Cd'):raise ValueError('Le scan nettoyé doit contenir les couleurs Cd.')
    colors=np.frombuffer(clean.pointFloatAttribValuesAsString('Cd'),dtype=np.float32).reshape(-1,3)
    if clean.findPointAttrib('GS_Alpha'):
        valid=np.frombuffer(clean.pointFloatAttribValuesAsString('GS_Alpha'),dtype=np.float32)>.1;points=points[valid];colors=colors[valid]
    with hou.InterruptableOperation('Estimer le fond architectural',open_interrupt_dialog=True) as operation:
        quads,colors,report=complete(points,colors,removed,threshold=node.evalParm('threshold'),spacing=node.evalParm('spacing'),radius=node.evalParm('radius'),max_planes=node.evalParm('planes'),max_cells=node.evalParm('max_cells'),color_mode=node.evalParm('color_mode'),progress=operation.updateProgress)
        geo=hou.Geometry();geo.addAttrib(hou.attribType.Point,'Cd',(1.,1.,1.));geo.addAttrib(hou.attribType.Point,'uv',(0.,0.,0.));vertices=geo.createPoints(quads.reshape(-1,3).tolist())
        geo.setPointFloatAttribValuesFromString('Cd',colors.reshape(-1,3).astype(np.float32).tobytes())
        for i in range(len(quads)):
            poly=geo.createPolygon()
            for p in vertices[i*4:i*4+4]:poly.addVertex(p)
        geo.addAttrib(hou.attribType.Global,'spirula_estimated_background',1)
        studio=hou.node(spirula_chain.config(node.creator())['studio']);folder=Path(studio.evalParm('workspace'))/'reparation';folder.mkdir(parents=True,exist_ok=True)
        path=folder/('fond_'+uuid.uuid4().hex[:10]+'.bgeo.sc');geo.saveToFile(str(path));node.parm('cache').set(str(path));node.setUserData('repair_signature',fingerprint(node));node.setUserData('repair_report',json.dumps(report))
        if node.userData('repair_approved'):node.destroyUserData('repair_approved')
        node.parm('status').set('%s surfaces · %s cellules. Inspecter puis valider.'%(len(report['planes']),report['cells']))
        path.with_suffix('.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8');node.cook(force=True);node.setDisplayFlag(True);node.setCurrent(True,clear_all_selected=True)
    return report


def approve(node):
    import spirula_replace
    if not node.evalParm('cache') or node.userData('repair_signature')!=fingerprint(node):raise ValueError('Calculer et vérifier le fond actuel avant validation.')
    root=node.parent();patch=root.node(node.userData('repair_converter'));merge=root.node(node.userData('repair_merge'))
    if not patch or not merge:raise ValueError('Recréer les étapes de réparation ; convertisseur manquant.')
    patch.setInput(0,node);node.setUserData('repair_approved',node.userData('repair_signature'))
    try:
        import spirula_object
        patch.bypass(False);spirula_object.build(patch);merge.setInput(1,patch);merge.parm('enabled').set(1);merge.setDisplayFlag(True)
        merge.setUserData('repair_estimator',node.name());merge.setUserData('repair_approved',node.userData('repair_signature'))
        node.parm('status').set('Fond validé et converti. Vérifier le raccord sur 02E puis continuer en 03.')
    except Exception:
        node.destroyUserData('repair_approved');raise


def action(node,command):
    import hou
    try:
        if command=='estimate':return estimate(node)
        if command=='approve':return approve(node)
    except Exception as exc:
        node.parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def attach(root,selection,cut,merge,manual,patch):
    import hou
    existing=root.node('02C_ESTIMER_FOND')
    if existing:return existing
    merge.setName('02E_SCAN_REPARE',unique_name=True);patch.setName('02D_FOND_VERS_SPLAT',unique_name=True)
    estimator=root.createNode('spirula::repair_planes::1.0','02C_ESTIMER_FOND');estimator.setInput(0,cut);estimator.setInput(1,selection)
    estimator.setPosition(hou.Vector2(-3,-6));patch.setPosition(hou.Vector2(-3,-8));merge.setPosition(hou.Vector2(-3,-10));manual.setPosition(hou.Vector2(-8,-6))
    estimator.setUserData('repair_converter',patch.name());estimator.setUserData('repair_merge',merge.name())
    if not root.userData('spirula_repair_layout'):
        for child in root.children():
            if child.userData('spirula_chain_role') not in (None,'studio','scan'):child.setPosition(child.position()+hou.Vector2(0,-8))
        root.setUserData('spirula_repair_layout','1')
        for oldbox in root.networkBoxes():oldbox.fitAroundContents()
    box=root.createNetworkBox('REMPLACEMENT_GUIDE');box.setComment('02A–02E · retrait et réparation du décor')
    for n in (selection,cut,estimator,patch,merge,manual):box.addItem(n)
    box.fitAroundContents()
    return estimator
