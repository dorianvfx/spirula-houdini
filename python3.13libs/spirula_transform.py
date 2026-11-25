"""Bake OBJ affine transforms into Gaussian positions, covariance and SH colour."""
import numpy as np
from spirula_ply import read, rotation, rotate_sh, basis
from spirula_object import quaternion_from_matrix


def bounding_box(geometry,matrix):
    import hou
    box=geometry.boundingBox();lo=np.array(box.minvec());hi=np.array(box.maxvec())
    corners=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    m=np.array(matrix.asTuple()).reshape(4,4);corners=corners@m[:3,:3]+m[3,:3]
    return hou.BoundingBox(*corners.min(axis=0),*corners.max(axis=0))


def transformed(source,matrix):
    import hou
    geo=hou.Geometry();geo.merge(source)
    m=np.array(matrix.asTuple(),dtype=np.float64).reshape(4,4)
    if np.allclose(m,np.eye(4),atol=1e-12):return geo
    if not geo.findPointAttrib('GS_Alpha'):raise ValueError('La source à transformer doit être un splat natif.')
    a=m[:3,:3].T
    scales=read(geo,'scale',3)*read(geo,'pscale',1,[1])
    singular=np.linalg.svd(a,compute_uv=False)
    if singular.min()<1e-12:raise ValueError('Transformation singulière : une échelle objet est nulle.')
    uniform=float(singular.mean())
    if np.max(np.abs(a-np.eye(3)*uniform))<1e-9:
        geo.transform(matrix)
        geo.setPointFloatAttribValuesFromString('scale',(scales*uniform).astype(np.float32).tobytes())
        if geo.findPointAttrib('pscale'):geo.setPointFloatAttribValuesFromString('pscale',np.ones(len(scales),np.float32).tobytes())
        return geo
    oldq=read(geo,'orient',4);oldr=rotation(oldq)
    u,s,vt=np.linalg.svd(a);orthogonal=u@vt
    if np.max(np.abs(s-uniform))<1e-9 and np.linalg.det(a)>0:
        frames=orthogonal@oldr;newscale=scales*uniform
    else:
        frames=np.empty_like(oldr);newscale=np.empty_like(scales)
        for start in range(0,len(scales),65536):
            end=start+65536
            f=a@oldr[start:end]*scales[start:end,None,:]
            cov=f@np.swapaxes(f,1,2)
            eigen,vectors=np.linalg.eigh(cov)
            flip=np.linalg.det(vectors)<0;vectors[flip,:,0]*=-1
            frames[start:end]=vectors;newscale[start:end]=np.sqrt(np.maximum(eigen,1e-30))
    coeff=np.stack([read(geo,'GS_SPH_'+c,16,np.zeros(16)) for c in 'RGB'],axis=-1)
    # Without restorient, write_geometry() applies no SH rotation; stay consistent
    # (default to orient) instead of silently rotating colours by the old orient.
    coeff=rotate_sh(coeff,oldq,read(geo,'restorient',4,None) if geo.findPointAttrib('restorient') else oldq)
    i=np.arange(64);z=1-2*(i+.5)/64;phi=i*np.pi*(3-np.sqrt(5));d=np.stack([np.sqrt(1-z*z)*np.cos(phi),np.sqrt(1-z*z)*np.sin(phi),z],axis=1)
    mat=np.linalg.pinv(basis(d))@basis(d@orthogonal)
    coeff=np.einsum('kl,nlc->nkc',mat,coeff,optimize=True)
    q=quaternion_from_matrix(frames).astype(np.float32)
    geo.transform(matrix)
    geo.setPointFloatAttribValuesFromString('scale',newscale.astype(np.float32).tobytes())
    geo.setPointFloatAttribValuesFromString('orient',q.tobytes())
    if not geo.findPointAttrib('restorient'):geo.addAttrib(hou.attribType.Point,'restorient',(0.,0.,0.,1.))
    geo.setPointFloatAttribValuesFromString('restorient',q.tobytes())
    if geo.findPointAttrib('pscale'):geo.setPointFloatAttribValuesFromString('pscale',np.ones(len(scales),np.float32).tobytes())
    for idx,c in enumerate('RGB'):
        geo.setPointFloatAttribValuesFromString('GS_SPH_'+c,coeff[:,:,idx].astype(np.float32).tobytes())
    return geo
