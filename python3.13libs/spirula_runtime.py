"""Engine discovery: never hard-code a Spirula version folder.

runtime/spirula.exe            -> stable engine
runtime/versions/<version>/    -> side-by-side candidates; the highest sortable
                                  version name that really contains spirula.exe wins.
"""
from pathlib import Path


def runtime_root():
    return Path(__file__).resolve().parents[1] / 'runtime'


def version_key(name):
    """'2026.10.30' -> (2026, 10, 30); non numeric parts sort last-but-stable."""
    parts = []
    for piece in name.replace('-', '.').split('.'):
        parts.append((0, int(piece), '') if piece.isdigit() else (-1, 0, piece))
    return tuple(parts)


def candidate_engine(root=None):
    base = Path(root) if root else runtime_root()
    versions = base / 'versions'
    found = [d for d in versions.iterdir() if (d / 'spirula.exe').is_file()] if versions.is_dir() else []
    if not found:
        raise FileNotFoundError('Aucun moteur candidat dans ' + str(versions))
    return max(found, key=lambda d: version_key(d.name)) / 'spirula.exe'


def stable_engine(root=None):
    path = (Path(root) if root else runtime_root()) / 'spirula.exe'
    if not path.is_file():
        raise FileNotFoundError('Moteur Spirula absent : ' + str(path))
    return path
