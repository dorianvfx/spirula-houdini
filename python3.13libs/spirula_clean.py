"""Floater / outlier cleanup for standard 3DGS PLY files (numpy only, no scipy).

Three conservative filters, each reported separately:
  1. opacity   - nearly invisible gaussians (sigmoid(opacity) < min_opacity)
  2. size      - 'fog' gaussians far larger than the scene's typical gaussian
  3. isolation - gaussians with almost no neighbours in a voxel-hash density
                 grid. Opaque ones are protected (thin real structures such as
                 wires or window frames survive), unless fully alone.

Nothing is invented: rows are only removed, never edited. Always compare
before/after; this is a heuristic, not a guarantee.
"""
import numpy as np


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _col(names, rows, keys):
    return rows[:, [names.index(k) for k in keys]]


def neighbour_counts(points, voxel, query=None):
    """Gaussians in the 3x3x3 voxel block around each point (self included).
    `query` = indices of the points to evaluate (default: all)."""
    cell = np.floor((points - points.min(axis=0)) / voxel).astype(np.int64) + 1
    dims = cell.max(axis=0) + 3
    if dims.astype(float).prod() > 4e18:
        raise ValueError('Voxel trop petit pour cette scène (%s cellules).' % dims.astype(float).prod())
    key = (cell[:, 0] * dims[1] + cell[:, 1]) * dims[2] + cell[:, 2]
    uniq, counts = np.unique(key, return_counts=True)
    if query is not None:
        cell = cell[query]
    total = np.zeros(len(cell), np.int64)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                q = ((cell[:, 0] + dx) * dims[1] + cell[:, 1] + dy) * dims[2] + cell[:, 2] + dz
                pos = np.searchsorted(uniq, q)
                pos[pos >= len(uniq)] = len(uniq) - 1
                total += np.where(uniq[pos] == q, counts[pos], 0)
    return total


def keep_mask(names, rows, **options):
    """Return (keep, report). rows: float array (N, len(names)) of a 3DGS PLY."""
    if len(rows) == 0:
        raise ValueError('PLY vide.')
    xyz = _col(names, rows, ('x', 'y', 'z')).astype(np.float64)
    alpha = sigmoid(rows[:, names.index('opacity')].astype(np.float64))
    size = np.exp(_col(names, rows, ('scale_0', 'scale_1', 'scale_2')).astype(np.float64)).max(axis=1)
    return floater_mask(xyz, alpha, size, **options)


def floater_mask(xyz, alpha, size, min_opacity=0.005, max_size_factor=12.0, max_size_percentile=99.0,
                 voxel=None, min_neighbours=3, protect_opacity=0.25):
    """Core filter on arrays: xyz (N,3), linear alpha (N,), largest world-space radius (N,)."""
    n = len(xyz)
    if n == 0:
        raise ValueError('Splat vide.')
    keep = np.ones(n, bool)
    report = {'input': n}

    low = alpha < min_opacity
    keep &= ~low
    report['removed_low_opacity'] = int(low.sum())

    reference = np.percentile(size[keep], max_size_percentile) if keep.any() else 0.0
    median = np.median(size[keep]) if keep.any() else 0.0
    limit = max(reference, median * 1.0) * max_size_factor / 4.0 if max_size_factor else np.inf
    big = keep & (size > limit)
    keep &= ~big
    report['removed_oversized'] = int(big.sum())
    report['size_limit'] = float(limit)

    if min_neighbours and keep.sum() > 8:
        if voxel is not None and voxel <= 0 or voxel is not None and not np.isfinite(voxel):
            raise ValueError('Taille de voxel invalide.')
        alive = np.flatnonzero(keep)
        counts = np.zeros(n, np.int64)
        if voxel:
            counts[alive] = neighbour_counts(xyz[alive], float(voxel))
            report['voxel'] = float(voxel)
        else:
            # Multi-scale: each gaussian is judged at 8x its own size, so a huge
            # room scan and tiny detailed objects in the same splat do not interfere.
            level = np.floor(np.log(size[alive]) / np.log(2.5)).astype(int)
            floor = float(np.ptp(xyz[alive], axis=0).max()) / 1500.0  # keeps the voxel grid addressable
            for lv in np.unique(level):
                counts[alive[level == lv]] = neighbour_counts(
                    xyz[alive], max(8.0 * 2.5 ** (lv + .5), floor), query=np.flatnonzero(level == lv))
            report['voxel'] = 'auto x8 taille locale'
        # Isolated AND faint. Opaque points are never removed for being alone.
        iso = keep & (counts <= min_neighbours) & (alpha < protect_opacity)
        keep &= ~iso
        report['removed_isolated'] = int(iso.sum())
    else:
        report['removed_isolated'] = 0

    report['output'] = int(keep.sum())
    report['removed_total'] = n - report['output']
    return keep, report


def clean_ply(source, target, **options):
    from spirula_refine import read_ply, write_ply
    names, rows = read_ply(source)
    keep, report = keep_mask(names, rows, **options)
    if keep.sum() < max(10, len(rows) * 0.05):
        raise ValueError('Nettoyage trop agressif (%d/%d conservés) : écriture refusée.' % (keep.sum(), len(rows)))
    write_ply(target, names, rows[keep])
    report['source'] = str(source)
    report['target'] = str(target)
    return report


ATTRIB = 'spirula_floater'


def evaluate(node):
    """Python SOP body of spirula::clean_floaters: tags points with spirula_floater=1."""
    import hou
    geo = node.geometry()  # a Python SOP starts as a copy of its input
    count = geo.intrinsicValue('pointcount')
    if not count:
        return
    if not geo.findPointAttrib('GS_Alpha'):
        raise hou.NodeError('Entrée : splat Houdini requis (attribut GS_Alpha).')
    parent = node.parent()
    def f(name):
        return parent.evalParm(name)
    p = np.frombuffer(geo.pointFloatAttribValuesAsString('P'), np.float32).reshape(-1, 3).astype(np.float64)
    alpha = np.frombuffer(geo.pointFloatAttribValuesAsString('GS_Alpha'), np.float32).astype(np.float64)
    scale = np.frombuffer(geo.pointFloatAttribValuesAsString('scale'), np.float32).reshape(-1, 3).astype(np.float64) \
        if geo.findPointAttrib('scale') else np.full((count, 3), .01)
    if geo.findPointAttrib('pscale'):
        scale = scale * np.frombuffer(geo.pointFloatAttribValuesAsString('pscale'), np.float32).astype(np.float64)[:, None]
    keep, report = floater_mask(p, alpha, scale.max(axis=1), min_opacity=f('min_opacity'),
                                max_size_factor=f('max_size_factor'), voxel=f('voxel') or None,
                                min_neighbours=f('min_neighbours'), protect_opacity=f('protect_opacity'))
    if not geo.findPointAttrib(ATTRIB):
        geo.addAttrib(hou.attribType.Point, ATTRIB, 0)
    geo.setPointIntAttribValuesFromString(ATTRIB, (~keep).astype(np.int32).tobytes())
    parent.parm('status').set('%d / %d retirées (opacité %d · taille %d · isolées %d)' % (
        report['removed_total'], report['input'], report['removed_low_opacity'],
        report['removed_oversized'], report['removed_isolated']))


def create(selected=None):
    """Insert a 'Nettoyer les floaters' node after the selected splat SOP."""
    import hou
    selected = selected or next(iter(hou.selectedNodes()), None)
    if selected is None or not isinstance(selected, hou.SopNode):
        raise ValueError('Sélectionner la sortie SOP du splat à nettoyer.')
    parent = selected.parent()
    node = parent.createNode('spirula::clean_floaters::1.0', 'NETTOYER_FLOATERS')
    old = selected.outputs()
    node.setInput(0, selected)
    for out in old:
        for i, inp in enumerate(out.inputs()):
            if inp == selected:
                out.setInput(i, node)
    node.setPosition(selected.position() + hou.Vector2(0, -1.5))
    node.setColor(hou.Color((.52, .36, .68)))
    node.setDisplayFlag(True)
    node.setCurrent(True, clear_all_selected=True)
    return node


if __name__ == '__main__':
    import argparse, json
    ap = argparse.ArgumentParser(description='Nettoyer les floaters d\'un PLY 3DGS.')
    ap.add_argument('source'); ap.add_argument('target')
    ap.add_argument('--min-opacity', type=float, default=0.005)
    ap.add_argument('--voxel', type=float, default=None)
    ap.add_argument('--min-neighbours', type=int, default=3)
    a = ap.parse_args()
    print(json.dumps(clean_ply(a.source, a.target, min_opacity=a.min_opacity, voxel=a.voxel,
                               min_neighbours=a.min_neighbours), indent=2))

