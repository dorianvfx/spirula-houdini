"""COLMAP sparse cameras -> OpenGL Nerfstudio frames, without CUDA or pycolmap."""
from pathlib import Path
import struct
import numpy as np

MODELS={0:('SIMPLE_PINHOLE',3),1:('PINHOLE',4),2:('SIMPLE_RADIAL',4),3:('RADIAL',5),4:('OPENCV',8)}

def unpack(f,fmt):
    size=struct.calcsize('<'+fmt);b=f.read(size)
    if len(b)!=size:raise ValueError('Reconstruction COLMAP tronquée.')
    return struct.unpack('<'+fmt,b)

def read(directory):
    root=Path(directory).resolve();sparse=next((p for p in (root/'sparse/0',root/'sparse',root) if (p/'cameras.bin').is_file() or (p/'cameras.txt').is_file()),None)
    if sparse is None:raise ValueError('Dataset attendu : transforms.json, ou dossier COLMAP contenant images/ et sparse/0/.')
    cameras={};images=[]
    if (sparse/'cameras.bin').is_file() and (sparse/'images.bin').is_file():
        with (sparse/'cameras.bin').open('rb') as f:
            count,=unpack(f,'Q')
            if count>1000000:raise ValueError('Nombre de caméras COLMAP invalide.')
            for _ in range(count):
                idx,model,w,h=unpack(f,'iiQQ')
                if model not in MODELS:raise ValueError('COLMAP : utiliser des images dédistordues pour ce modèle de caméra (id %s).'%model)
                name,n=MODELS[model];cameras[idx]=(name,w,h,unpack(f,'d'*n))
        with (sparse/'images.bin').open('rb') as f:
            count,=unpack(f,'Q')
            if count>1000000:raise ValueError('Nombre d’images COLMAP invalide.')
            for _ in range(count):
                data=unpack(f,'idddddddi');name=bytearray()
                for _ in range(65536):
                    c=f.read(1)
                    if not c:raise ValueError('Nom d’image COLMAP tronqué.')
                    if c==b'\0':break
                    name.extend(c)
                else:raise ValueError('Nom d’image COLMAP trop long.')
                points,=unpack(f,'Q');skip=points*24
                if f.tell()+skip>(sparse/'images.bin').stat().st_size:raise ValueError('Observations COLMAP tronquées.')
                f.seek(skip,1);images.append((data[0],data[1:5],data[5:8],data[8],name.decode('utf-8')))
    elif (sparse/'cameras.txt').is_file() and (sparse/'images.txt').is_file():
        for line in (sparse/'cameras.txt').read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.lstrip().startswith('#'):continue
            row=line.split();cameras[int(row[0])]=(row[1],int(row[2]),int(row[3]),list(map(float,row[4:])))
        lines=iter((sparse/'images.txt').read_text(encoding='utf-8').splitlines())
        for line in lines:
            if not line.strip() or line.lstrip().startswith('#'):continue
            row=line.split(maxsplit=9)
            if len(row)!=10:raise ValueError('Ligne de pose COLMAP invalide.')
            images.append((int(row[0]),list(map(float,row[1:5])),list(map(float,row[5:8])),int(row[8]),row[9]));next(lines,None)
    else:raise ValueError('Il manque cameras et images dans la reconstruction COLMAP.')
    from spirula_ply import rotation
    frames=[]
    for idx,q,t,cam,name in sorted(images):
        if cam not in cameras:raise ValueError('Caméra COLMAP introuvable pour '+name)
        model,w,h,p=cameras[cam];coeff={}
        if model in ('SIMPLE_PINHOLE','SIMPLE_RADIAL','RADIAL'):
            fx=fy=p[0];cx,cy=p[1:3]
            if model!='SIMPLE_PINHOLE':coeff['k1']=p[3]
            if model=='RADIAL':coeff['k2']=p[4]
        elif model in ('PINHOLE','OPENCV'):
            fx,fy,cx,cy=p[:4]
            if model=='OPENCV':coeff=dict(zip(('k1','k2','p1','p2'),p[4:8]))
        else:raise ValueError('COLMAP '+model+' : fournir sa reconstruction dédistordue PINHOLE pour ce raffinement.')
        qw,qx,qy,qz=q;r=rotation(np.array([[qx,qy,qz,qw]]))[0];m=np.eye(4);m[:3,:3]=r.T@np.diag([1.,-1.,-1.]);m[:3,3]=-r.T@np.array(t)
        path=next((p for p in (root/'images'/name,root/name) if p.is_file()),None)
        if path is None:raise ValueError('Photo COLMAP absente : '+name+' ; sélectionner la racine contenant images/ et sparse/.')
        path=path.resolve()
        if not path.is_relative_to(root):raise ValueError('Photo située hors du dossier projet.')
        frames.append(dict(file_path=path.relative_to(root).as_posix(),w=w,h=h,fl_x=fx,fl_y=fy,cx=cx,cy=cy,transform_matrix=m.tolist(),**coeff))
    return dict(camera_model='OPENCV',frames=frames,adapter='COLMAP binary/text to OpenGL; original coordinates, no pose normalization')
