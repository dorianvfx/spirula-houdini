"""Surface Gaussian colour bake with mesh visibility, no free geometry optimisation."""
import json,math,time
from pathlib import Path
import numpy as np

def read_float_ply(path):
 with open(path,'rb') as stream:
  lines=[]
  while True:
   line=stream.readline();lines.append(line)
   if line.strip()==b'end_header':break
  header=b''.join(lines);count=int(next(s for s in lines if s.startswith(b'element vertex')).split()[2]);names=[s.split()[2].decode() for s in lines if s.startswith(b'property')]
  if any(not s.startswith(b'property float ') for s in lines if s.startswith(b'property')):raise ValueError('Float PLY required')
  data=np.fromfile(stream,dtype='<f4',count=count*len(names)).reshape(count,len(names));return header,names,data

def bake(init_ply,geo,transforms,dataset,target,progress=print,use_exr=False,color_metadata=None):
 import hou
 from PIL import Image
 born=time.monotonic();header,names,rows=read_float_ply(init_ply);points=rows[:,:3].astype(float);normal=rows[:,3:6].astype(float);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-15);accum=np.zeros_like(points);weights=np.zeros(len(points));hits=np.zeros(len(points),np.int32);ray=hou.sopNodeTypeCategory().nodeVerb('ray');ray.setParms({'method':1,'dirmethod':2,'dotrans':1,'newgrp':1,'hitgrp':'hits','rtolerance':1e-6});diag=np.linalg.norm(np.ptp(points,axis=0));tolerance=max(1e-5,diag*1e-5)
 for i,v in enumerate(transforms['frames']):
  if (Path(target).parent/'cancel.request').exists():raise InterruptedError('Cuisson arrêtée entre deux vues.')
  m=np.asarray(v['transform_matrix']);camera=m[:3,3];p=(points-camera)@m[:3,:3];z=-p[:,2];u=v['fl_x']*p[:,0]/np.maximum(z,1e-9)+v['cx']-.5;vv=-v['fl_y']*p[:,1]/np.maximum(z,1e-9)+v['cy']-.5;distance=np.linalg.norm(points-camera,axis=1);cos=np.abs(np.sum(normal*(points-camera)/np.maximum(distance[:,None],1e-9),axis=1));ids=np.where((z>0)&(u>=0)&(u<v['w']-1)&(vv>=0)&(vv<v['h']-1)&(cos>.12))[0]
  directions=points[ids]-camera;directions/=distance[ids,None];rays=hou.Geometry();rays.createPoints(np.repeat(camera[None],len(ids),axis=0).tolist());rays.addAttrib(hou.attribType.Point,'N',(0.,0.,-1.));rays.setPointFloatAttribValuesFromString('N',directions.astype(np.float32).tobytes());out=hou.Geometry();ray.execute(out,[rays,geo]);intersections=np.asarray(out.pointFloatAttribValues('P')).reshape(-1,3);visible=np.linalg.norm(intersections-points[ids],axis=1)<tolerance;ids=ids[visible]
  if use_exr:
   import OpenImageIO as oiio
   path=Path(dataset)/'renders'/(Path(v['file_path']).stem+'.exr');reader=oiio.ImageInput.open(str(path))
   if reader is None:raise ValueError('Rendu EXR manquant : '+str(path))
   spec=reader.spec();channels=[c.lower() for c in spec.channelnames];pixels=np.asarray(reader.read_image(format=oiio.FLOAT));reader.close()
   if (spec.width,spec.height)!=(v['w'],v['h']):raise ValueError('Résolution EXR différente de la caméra : '+str(path))
   prefix=next((p for p in ['', 'c.', 'ci.', 'beauty.', 'combined.'] if all(p+c in channels for c in ['r','g','b'])),None)
   if prefix is None:raise ValueError('Passe RGB absente : '+str(path))
   rgb=np.ascontiguousarray(pixels[:,:,[channels.index(prefix+c) for c in ['r','g','b']]],dtype=np.float32);alpha=pixels[:,:,channels.index(prefix+'a')] if prefix+'a' in channels else np.ones(rgb.shape[:2]);rgb=np.where(alpha[:,:,None]>1e-6,rgb/np.maximum(alpha[:,:,None],1e-6),0)
   if color_metadata:
    import PyOpenColorIO as ocio
    cfg=ocio.Config.CreateFromFile(color_metadata['ocio']) if color_metadata.get('ocio') else ocio.GetCurrentConfig();rgb=np.ascontiguousarray(rgb,dtype=np.float32);cfg.getProcessor(color_metadata['working_space'],'Linear Rec.709 (sRGB)').getDefaultCPUProcessor().applyRGB(rgb);rgb*=2**color_metadata.get('exposure',0)
   image=np.dstack([rgb,alpha])
  else:image=np.array(Image.open(Path(dataset)/v['file_path']).convert('RGBA'),dtype=float)/255
  x=u[ids];y=vv[ids];ix=x.astype(int);iy=y.astype(int);fx=(x-ix)[:,None];fy=(y-iy)[:,None];color=((image[iy,ix]*(1-fx)+image[iy,ix+1]*fx)*(1-fy)+(image[iy+1,ix]*(1-fx)+image[iy+1,ix+1]*fx)*fy);valid=color[:,3]>.99;ids=ids[valid];color=color[valid,:3];weight=cos[ids]**2/np.maximum(distance[ids]**2,1e-8);accum[ids]+=color*weight[:,None];weights[ids]+=weight;hits[ids]+=1
  progress('Couleurs Karma : vue %s / %s · %s gaussiennes visibles · %s couvertes'%(i+1,len(transforms['frames']),len(ids),int((weights>0).sum())))
 covered=weights>0;colors=accum[covered]/weights[covered,None]
 if use_exr:colors=np.where(colors<=.0031308,colors*12.92,1.055*np.maximum(colors,0)**(1/2.4)-.055)
 colors=np.clip(colors,0,1);rows[covered,6:9]=(colors-.5)/.28209479177387814;rows[:,9:54]=0;rows[:,54]=math.log(.995/.005)
 rows=rows[covered]
 if not len(rows) or not np.isfinite(rows).all():raise ValueError('Aucune gaussienne visible, ou valeurs non finies.')
 header=b'\n'.join((b'element vertex '+str(len(rows)).encode()) if line.startswith(b'element vertex ') else line for line in header.splitlines())+b'\n'
 temp=Path(target).with_name('.partial_'+Path(target).name)
 with temp.open('wb') as stream:stream.write(header);rows.tofile(stream)
 temp.replace(target)
 report={'gaussians':len(rows),'initial_candidates':len(covered),'observed_gaussians':int(covered.sum()),'observed_fraction':float(covered.mean()),'views':len(transforms['frames']),'seconds':time.monotonic()-born,'method':'Mesh-surface Gaussian radiance bake; visibility ray tests; weighted RGB; fixed covariance and opacity; no SH fit','unobserved_fallback':'Excluded: not supported by any capture view','geometry_frozen':True,'colour_source':'linear EXR radiance to standard sRGB PLY' if use_exr else 'display PNG'};Path(target).with_suffix('.json').write_text(json.dumps(report,indent=2));return report


def run_worker(data,folder,status):
    import hou
    import spirula_object as obj
    folder=Path(folder);source=hou.node(data['training_seed'])
    if source is None:raise ValueError('Le mode surface nécessite un mesh SOP valide.')
    status('training','Préparation des gaussiennes sur le mesh…',step=0,steps=len(data['views']))
    captured=obj.capture(source);world=np.array(source.creator().worldTransform().asTuple()).reshape(4,4)
    captured['triangles'][:,:,:3]=captured['triangles'][:,:,:3]@world[:3,:3]+world[3,:3]-np.array(data.get('training_origin',[0,0,0]))
    cap=int(data['cap']);spacing=math.sqrt(4*captured['area']/(math.sqrt(3)*max(1,cap/5)));init=folder/'surface_initial.ply'
    for attempt in range(8):
        report=obj.convert(captured,init,spacing=spacing,limit=max(cap*4,len(captured['triangles'])*2),coverage=1.8,thickness=.02,opacity=.995)
        if report['gaussians']<=cap:break
        spacing*=max(1.05,math.sqrt(report['gaussians']/cap)*1.02)
    else:raise ValueError('Budget de surface insuffisant pour cette géométrie ; augmenter le plafond.')
    geo=hou.Geometry();geo.merge(source.geometry());geo.transform(source.creator().worldTransform()*hou.hmath.buildTranslate(tuple(-np.array(data.get('training_origin',[0,0,0])))))
    target=folder/'surface_baked.ply';transforms=json.loads((folder/'transforms.json').read_text(encoding='utf-8'));counter=0
    def progress(message):
        nonlocal counter
        counter+=1;status('training',message,step=counter,steps=len(transforms['frames']),rendered=len(transforms['frames']),total=len(transforms['frames']))
    result=bake(init,geo,transforms,folder,target,progress,use_exr=True,color_metadata=data)
    result.update(requested_cap=cap,sampling=report,training_method='surface_bake');target.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return target
