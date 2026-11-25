"""Regression suite: run with hython  (hython spirula_selftest.py). Exit code 1 on failure."""
import sys, os, tempfile, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spirula_ply as P
FAILS = []
def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else ''))
    if not ok: FAILS.append(name)

def test_sh():
    rng = np.random.default_rng(1)
    d = rng.normal(size=(500, 3)); d /= np.linalg.norm(d, axis=1, keepdims=True)
    x, y, z = d.T; xx, yy, zz = x*x, y*y, z*z; xy, yz, xz = x*y, y*z, x*z
    C2 = [1.0925484305920792, -1.0925484305920792, 0.31539156525252005, -1.0925484305920792, 0.5462742152960396]
    C3 = [-0.5900435899266435, 2.890611442640554, -0.4570457994644658, 0.3731763325901154, -0.4570457994644658, 1.445305721320277, -0.5900435899266435]
    C1 = 0.4886025119029199
    ref = np.stack([0.28209479177387814+0*x, -C1*y, C1*z, -C1*x, C2[0]*xy, C2[1]*yz, C2[2]*(2*zz-xx-yy), C2[3]*xz, C2[4]*(xx-yy),
        C3[0]*y*(3*xx-yy), C3[1]*xy*z, C3[2]*y*(4*zz-xx-yy), C3[3]*z*(2*zz-3*xx-3*yy), C3[4]*x*(4*zz-xx-yy), C3[5]*z*(xx-yy), C3[6]*x*(xx-3*yy)], axis=-1)
    check('SH basis == 3DGS reference', np.abs(P.basis(d) - ref).max() < 1e-9)
    q = rng.normal(size=(20, 4)); q /= np.linalg.norm(q, axis=1, keepdims=True)
    coeff = rng.normal(size=(20, 16, 3)); out = P.rotate_sh(coeff, q, np.tile([0, 0, 0, 1.0], (20, 1))); R = P.rotation(q)
    e = max(np.abs(P.basis(d[:30]) @ coeff[i] - P.basis(d[:30] @ R[i].T) @ out[i]).max() for i in range(20))
    check('SH rotation invariance', e < 1e-6, 'err=%.1e' % e)

def test_runtime():
    import spirula_runtime as R
    tmp = tempfile.mkdtemp()
    for v in ('2026.9.5', '2026.10.30', '2026.10.4', 'empty'):
        os.makedirs(os.path.join(tmp, 'versions', v))
        if v != 'empty': open(os.path.join(tmp, 'versions', v, 'spirula.exe'), 'w').close()
    check('engine resolver picks highest real version', R.candidate_engine(tmp).parent.name == '2026.10.30')

def test_clean():
    import spirula_clean as C
    rng = np.random.default_rng(5)
    names = ['x','y','z','nx','ny','nz','f_dc_0','f_dc_1','f_dc_2'] + ['f_rest_%d' % i for i in range(45)] + ['opacity','scale_0','scale_1','scale_2','rot_0','rot_1','rot_2','rot_3']
    def rows(pts, alpha, size):
        r = np.zeros((len(pts), len(names)), np.float32); r[:, :3] = pts
        r[:, names.index('opacity')] = np.log(alpha / (1 - alpha)); r[:, 54-0+0] = r[:, 54]  # no-op
        for i in range(3): r[:, names.index('scale_%d' % i)] = np.log(size)
        r[:, names.index('rot_0')] = 1; return r
    wall = rows(np.c_[rng.uniform(0, 4, 20000), rng.uniform(0, 3, 20000), rng.normal(0, .002, 20000)], .9, .02)
    wire = rows(np.c_[np.linspace(0, 2, 400), np.full(400, 1.5), np.full(400, .3)], .95, .01)
    dust = rows(rng.uniform([-3, -3, -3], [7, 6, 3], (60, 3)) + 10 * (rng.random((60, 3)) > 2), .15, .02)
    ghost = rows(rng.uniform(0, 3, (30, 3)), .004, .02)
    fog = rows(rng.uniform(0, 3, (5, 3)), .5, 3.0)
    allr = np.concatenate([wall, wire, dust, ghost, fog]); keep, rep = C.keep_mask(names, allr, voxel=.1)
    wall_ok = keep[:20000].mean(); wire_ok = keep[20000:20400].mean()
    check('clean keeps real surfaces', wall_ok > .99 and wire_ok > .99, 'wall %.3f wire %.3f' % (wall_ok, wire_ok))
    junk = ~keep[20400:]
    check('clean removes floaters/ghosts/fog', junk.mean() > .9, 'removed %.2f of junk, report %s' % (junk.mean(), rep))

def test_transform():
    import hou, spirula_transform as T
    rng=np.random.default_rng(3); n=300
    def randrot():
        q=rng.normal(size=4); q/=np.linalg.norm(q); return q
    def mk():
        g=hou.Geometry()
        for nm,sz in (("scale",3),("orient",4),("restorient",4),("GS_Alpha",1),("Cd",3),("pscale",1)):
            g.addAttrib(hou.attribType.Point,nm,(0.,)*sz if sz>1 else 0.)
        for c in "RGB": g.addAttrib(hou.attribType.Point,"GS_SPH_"+c,tuple([0.]*16))
        g.createPoints([tuple(x) for x in rng.normal(size=(n,3))])
        pos=np.frombuffer(g.pointFloatAttribValuesAsString("P"),np.float32).reshape(-1,3).copy()
        q=rng.normal(size=(n,4)); q/=np.linalg.norm(q,axis=1,keepdims=True)
        s=np.exp(rng.normal(size=(n,3))*.5-1)
        sh=rng.normal(size=(n,16,3))*.3
        S=lambda nm,a:g.setPointFloatAttribValuesFromString(nm,np.asarray(a,np.float32).tobytes())
        S("scale",s);S("orient",q);S("restorient",q);S("GS_Alpha",rng.uniform(.2,.9,n));S("Cd",rng.uniform(0,1,(n,3)));S("pscale",np.ones(n))
        for i,c in enumerate("RGB"):S("GS_SPH_"+c,sh[:,:,i])
        return g,pos,q,s
    def read_ply(path):
        with open(path,"rb") as f:
            names=[];
            while True:
                l=f.readline().decode().split()
                if l[:1]==["property"]:names.append(l[2])
                if l==["end_header"]:break
            a=np.fromfile(f,dtype="<f4").reshape(-1,len(names))
        return names,a.astype(np.float64)
    def cov_from_ply(names,a):
        s=np.exp(a[:,[names.index("scale_%d"%i) for i in range(3)]]); w,x,y,z=a[:,[names.index("rot_%d"%i) for i in range(4)]].T
        R=P.rotation(np.stack([x,y,z,w],1)); return R@(s[:,:,None]**2*np.swapaxes(R,1,2)), R
    def sh_from_ply(names,a):
        dc=a[:,[names.index("f_dc_%d"%i) for i in range(3)]][:,None,:]
        rest=a[:,[names.index("f_rest_%d"%i) for i in range(45)]].reshape(-1,3,15).transpose(0,2,1)
        return np.concatenate([dc,rest],1)
    tmp=tempfile.mkdtemp()
    cases={}
    a1=np.eye(3); 
    Rm=P.rotation(np.array([[0.3,-0.5,0.2,0.78]]))[0]
    cases["rot_only"]=Rm
    cases["rot_uniform_x3"]=Rm*3.0
    cases["nonuniform"]=Rm@np.diag([1.0,2.5,0.6])
    for name,A in cases.items():
        g,pos,q,s=mk()
        # no-transform baseline export
        base=os.path.join(tmp,"b.ply"); P.write_geometry(g,base,linearized=False)
        nb,ab=read_ply(base); covb,_=cov_from_ply(nb,ab); shb=sh_from_ply(nb,ab)
        m=hou.Matrix4(); M=np.eye(4); M[:3,:3]=A.T   # Houdini row-vector convention
        m=hou.Matrix4(tuple(M.ravel()))
        g2=T.transformed(g,m); out=os.path.join(tmp,"o.ply"); P.write_geometry(g2,out,linearized=False)
        no,ao=read_ply(out); cov,_=cov_from_ply(no,ao)
        expect=A@covb@A.T
        cerr=np.abs(cov-expect).max()/np.abs(expect).max()
        perr=np.abs(ao[:,:3]-(ab[:,:3]@A.T)).max()
        # SH: colour seen along world direction d after == colour along A-normalised-inverse direction before
        shn=sh_from_ply(no,ao); d=rng.normal(size=(30,3)); d/=np.linalg.norm(d,axis=1,keepdims=True)
        # direction in old frame: for rotation part U (polar), d_old = U^T d_new
        U,_,Vt=np.linalg.svd(A); Ro=U@Vt
        e=0
        for i in range(0,n,10):
            new=P.basis(d)@shn[i]; old=P.basis(d@Ro)@shb[i]; e=max(e,np.abs(new-old).max())
        print("%-16s cov relerr=%.2e  pos err=%.2e  SH err=%.2e"%(name,cerr,perr,e), "PASS" if cerr<1e-4 and perr<1e-4 and e<1e-4 else "FAIL")
    
    
    

def test_package():
    """Every module imports, internal stage nodes are hidden from Tab, user-facing ones are not."""
    import glob, importlib, hou
    here = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for f in sorted(glob.glob(os.path.join(here, 'spirula_*.py'))):
        name = os.path.basename(f)[:-3]
        if name == 'spirula_selftest':
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            bad.append('%s (%s)' % (name, exc))
    check('tous les modules s\'importent', not bad, '; '.join(bad))
    cat = hou.sopNodeTypeCategory()
    shown = sorted(n for n, t in cat.nodeTypes().items() if n.startswith('spirula::') and not t.hidden())
    check('menu Tab : seuls clean_floaters et polish visibles', shown == ['spirula::clean_floaters::1.0', 'spirula::polish::1.0'], str(shown))
    import spirula_tools
    try:
        raise ValueError('x')
    except ValueError as exc:
        try:
            spirula_tools.report('selftest', exc)
            ok = False
        except ValueError:
            ok = True  # headless: the error is re-raised, never swallowed
    check('les erreurs d\'outils ne sont pas avalées', ok)


if __name__ == '__main__':
    test_sh(); test_runtime(); test_clean()
    try:
        import hou; test_package()
    except ImportError:
        print('SKIP package test (needs hython)')
    try:
        import hou; test_transform()
    except ImportError:
        print('SKIP transform test (needs hython)')
    print('\n%d échec(s)' % len(FAILS)); sys.exit(1 if FAILS else 0)

