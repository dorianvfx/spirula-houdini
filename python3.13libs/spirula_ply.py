"""Standard 3DGS PLY export, including orientation-aware SH rotation."""
import math
import numpy as np


def basis(d):
    x, y, z = np.moveaxis(d, -1, 0)
    phi = np.arctan2(y, x)
    out = []
    for l in range(4):
        for m in range(-l, l + 1):
            k = abs(m)
            p = np.ones_like(z)
            for j in range(1, k + 1):
                p *= -(2 * j - 1) * np.sqrt(np.maximum(0, 1 - z * z))
            if l > k:
                a, b = p, (2 * k + 1) * z * p
                for j in range(k + 2, l + 1):
                    a, b = b, ((2 * j - 1) * z * b - (j + k - 1) * a) / (j - k)
                p = b
            p = p * math.sqrt((2 * l + 1) / (4 * math.pi) * math.factorial(l - k) / math.factorial(l + k))
            if m < 0:
                p *= math.sqrt(2) * np.sin(k * phi)
            elif m > 0:
                p *= math.sqrt(2) * np.cos(k * phi)
            out.append(p)
    return np.stack(out, axis=-1)


def rotation(q):
    q = q / np.maximum(np.linalg.norm(q, axis=-1, keepdims=True), 1e-20)
    x, y, z, w = q.T
    return np.stack([1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w),
                     2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w),
                     2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)], axis=-1).reshape(-1, 3, 3)


def rotate_sh(coeff, orient, rest):
    r = rotation(orient) @ np.swapaxes(rotation(rest), 1, 2)
    i = np.arange(64)
    z = 1 - 2 * (i + .5) / 64
    phi = i * np.pi * (3 - np.sqrt(5))
    d = np.stack([np.sqrt(1-z*z)*np.cos(phi), np.sqrt(1-z*z)*np.sin(phi), z], axis=-1)
    inverse = np.linalg.pinv(basis(d))
    out = coeff.copy()
    changed = np.where(np.max(np.abs(r - np.eye(3)), axis=(1, 2)) > 1e-6)[0]
    if len(changed):
        keys, first, groups = np.unique(np.round(r[changed].reshape(-1, 9), 5), axis=0,
                                        return_index=True, return_inverse=True)
        if len(keys) <= 128:
            for group, first_index in enumerate(first):
                ids = changed[groups == group]
                mat = inverse @ basis(d @ r[changed[first_index]])
                out[ids] = np.einsum('kl,nlc->nkc', mat, coeff[ids], optimize=True)
            return out
    for start in range(0, len(changed), 1024):
        ids = changed[start:start+1024]
        y = basis(np.einsum('dj,njk->ndk', d, r[ids]))
        mat = np.einsum('kd,ndl->nkl', inverse, y)
        out[ids] = np.einsum('nkl,nlc->nkc', mat, coeff[ids])
    return out


def read(geo, name, width, default=None):
    if geo.findPointAttrib(name):
        return np.frombuffer(geo.pointFloatAttribValuesAsString(name), dtype=np.float32).astype(np.float64).reshape(-1, width)
    if default is None:
        raise ValueError('Attribut GSplat requis : ' + name)
    return np.broadcast_to(default, (int(geo.intrinsicValue('pointcount')), width)).copy()


def write_geometry(geo, target, linearized=True):
    p = read(geo, 'P', 3)
    n = len(p)
    if not n or not geo.findPointAttrib('GS_Alpha'):
        raise ValueError('La géométrie doit contenir des Gaussian Splats convertis par Bake GSplats.')
    scale = read(geo, 'scale', 3) * read(geo, 'pscale', 1, [1])
    if np.any(scale <= 0):
        raise ValueError('Les tailles des gaussiennes doivent être positives.')
    q = read(geo, 'orient', 4)
    if np.any(np.linalg.norm(q, axis=1) < 1e-12):
        raise ValueError('Quaternion nul dans orient.')
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    alpha = np.clip(read(geo, 'GS_Alpha', 1), 1e-7, 1-1e-7)
    coeff = np.stack([read(geo, 'GS_SPH_' + c, 16, np.zeros(16)) for c in 'RGB'], axis=-1)
    if geo.findPointAttrib('restorient'):
        coeff = rotate_sh(coeff, q, read(geo, 'restorient', 4))
    cd = read(geo, 'Cd', 3)
    if linearized:
        cd = np.where(cd <= .0031308, cd * 12.92, 1.055 * np.maximum(cd, 0)**(1/2.4) - .055)
    coeff[:, 0, :] = (cd - .5) / .28209479177387814
    names = ['x','y','z','nx','ny','nz'] + ['f_dc_' + str(i) for i in range(3)]
    names += ['f_rest_' + str(i) for i in range(45)] + ['opacity']
    names += ['scale_' + str(i) for i in range(3)] + ['rot_' + str(i) for i in range(4)]
    rows = np.concatenate([p, np.zeros_like(p), coeff[:, 0, :],
                           coeff[:, 1:, :].transpose(0, 2, 1).reshape(n, 45),
                           np.log(alpha/(1-alpha)), np.log(scale), q[:, [3,0,1,2]]], axis=1)
    if not np.isfinite(rows).all():
        raise ValueError('Valeurs NaN ou infinies : export annulé.')
    header = 'ply\nformat binary_little_endian 1.0\ncomment Spirula Houdini standard 3DGS\nelement vertex %d\n' % n
    header += ''.join('property float %s\n' % name for name in names) + 'end_header\n'
    with open(target, 'wb') as f:
        f.write(header.encode('ascii'))
        rows.astype('<f4').tofile(f)
