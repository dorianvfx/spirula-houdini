import os
from pathlib import Path
import hou

ROOT = Path(__file__).resolve().parents[1]
os.environ['SPIRULA_ROOT'] = str(ROOT)
hou.putenv('SPIRULA_ROOT', str(ROOT).replace('\\', '/'))
geo = hou.node('/obj').createNode('geo', 'spirula_build')
for c in geo.children():
    c.destroy()
sub = geo.createNode('subnet', 'spirula')
sub.setUserData('nodeshape', 'circle')

def string(name, label, default='', file=False, directory=False):
    p = hou.StringParmTemplate(name, label, 1, default_value=(default,))
    if file or directory:
        p.setStringType(hou.stringParmType.FileReference)
        p.setFileType(hou.fileType.Directory if directory else hou.fileType.Any)
    return p

def button(name, label, action):
    p = hou.ButtonParmTemplate(name, label)
    p.setScriptCallback("import spirula_houdini; spirula_houdini.callback(kwargs['node'], '%s')" % action)
    p.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    return p

def menu(name, label, tokens, default=0):
    return hou.MenuParmTemplate(name, label, tokens, tokens, default_value=default)

tabs = []
tabs.append(hou.FolderParmTemplate('project', 'Projet', parm_templates=[
    button('gui', 'Ouvrir le viewport Spirula Studio', 'studio'),
    string('workspace', 'Dossier de travail', '$HIP/spirula/$OS', directory=True),
    string('images', 'Dossier de photos', '$HIP/images', directory=True),
    string('video', 'Vidéo source', '', file=True),
    hou.IntParmTemplate('skip', 'Une image toutes les N images', 1, default_value=(15,), min=1),
    button('extract', 'Extraire la vidéo', 'extract'),
    string('executable', 'Moteur Spirula', '$SPIRULA_ROOT/runtime/spirula.exe', file=True),
    string('device', 'GPU (auto, index ou nom)', 'auto')]))
tabs.append(hou.FolderParmTemplate('training', 'Reconstruction / entraînement', parm_templates=[
    menu('quality', 'Qualité SfM', ['low', 'medium', 'high', 'extreme'], 2),
    menu('preset', 'Préréglage', ['3dgs', '360-camera', 'in-the-wild', 'centered-object', 'hdr', 'synthetic', 'meshing']),
    hou.IntParmTemplate('iterations', 'Itérations', 1, default_value=(30000,), min=1),
    hou.IntParmTemplate('port', 'Port du viewer', 1, default_value=(7007,), min=1024, max=65535),
    button('pipeline', 'Photos → caméras → splat → viewport', 'pipeline'),
    button('sfm', 'Reconstruire seulement les caméras', 'sfm'),
    button('train', 'Entraîner avec les caméras existantes', 'train'),
    button('viewer', 'Afficher le suivi de l’entraînement', 'viewer'),
    button('stop', 'Arrêter le calcul (dernier checkpoint conservé)', 'stop')]))
tabs.append(hou.FolderParmTemplate('display', 'Splat / placement', parm_templates=[
    string('splatfile', 'Splat PLY', '$SPIRULA_ROOT/examples/demo.ply', file=True),
    button('reload_splat', 'Recharger le splat', 'reload_splat'),
    hou.ToggleParmTemplate('linearize', 'Convertir sRGB → linéaire', default_value=True),
    hou.FloatParmTemplate('t', 'Translation', 3),
    hou.FloatParmTemplate('r', 'Rotation', 3),
    hou.FloatParmTemplate('scale', 'Échelle uniforme', 1, default_value=(1,), min=.00001),
    button('solaris', 'Créer l’import Solaris / Karma XPU', 'solaris')]))
tabs.append(hou.FolderParmTemplate('mesh_tab', 'Mesh / collisions', parm_templates=[
    hou.IntParmTemplate('mesh_resolution', 'Résolution maximale de grille', 1, default_value=(256,), min=16, max=1024),
    button('mesh', 'Générer le mesh avec Spirula puis l’importer', 'mesh'),
    string('meshfile', 'Mesh PLY / OBJ', '', file=True),
    button('import_mesh', 'Importer un mesh existant', 'import_mesh'),
    string('collisionpath', 'SOP de collision à utiliser dans les simulations')]))
tabs.append(hou.FolderParmTemplate('export_tab', 'Export', parm_templates=[
    string('export_source', 'SOP à exporter (facultatif)', ''),
    string('exportfile', 'Destination (.ply / .bgeo.sc)', '$HIP/spirula/export/splat.ply', file=True),
    button('export', 'Exporter le splat placé / édité', 'export')]))
tabs.append(hou.FolderParmTemplate('logs', 'Journal', parm_templates=[
    string('status', 'État', 'Prêt — splat de démonstration'),
    string('logfile', 'Journal du calcul', '', file=True)]))
tabs.append(hou.FolderParmTemplate('advanced', 'Avancé', parm_templates=[
    menu('advanced_command', 'Outil Spirula', ['sam', 'geometry', 'dense', 'e57', 'lidar', 'partition', 'encode', 'sfm', 'train', 'mesh']),
    string('advanced_args', 'Arguments (liste JSON)', '["--help"]'),
    button('advanced_run', 'Exécuter et écrire le journal', 'advanced')]))
sub.setParmTemplateGroup(hou.ParmTemplateGroup(tabs))
read = sub.createNode('file', 'read_splat')
read.parm('file').setExpression('chs("../splatfile")')
bake = sub.createNode('bakegsplat', 'NATIVE_GAUSSIAN_SPLATS')
bake.setInput(0, read)
bake.parm('sphcoeff').set(1)
bake.parm('linearize').setExpression('ch("../linearize")')
x = sub.createNode('xform', 'PLACEMENT')
x.setInput(0, bake)
for name in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'scale']:
    x.parm(name).setExpression('ch("../%s")' % name)
out = sub.createNode('null', 'OUT_SPLAT')
out.setInput(0, x)
out.setDisplayFlag(True)
out.setRenderFlag(True)
sub.layoutChildren()
asset = sub.createDigitalAsset(name='spirula::studio::1.0',
    hda_file_name=str(ROOT / 'otls' / 'SpirulaStudio.hda'),
    description='Spirula Studio', min_num_inputs=0, max_num_inputs=1)
definition = asset.type().definition()
print('ASSET', asset.path(), len(asset.children()), len(asset.parms()), flush=True)
definition.updateFromNode(asset)
definition.setIcon('SOP_bakegsplat')
definition.addSection('Help', '''= Spirula Studio =

Photos ou vidéo → reconstruction → entraînement → GSplats natifs Houdini.

Les calculs tournent en arrière-plan. Le journal contient les commandes et erreurs.
Le splat est chargé automatiquement après un entraînement réussi.
Le mesh est nécessaire aux collisions physiques : les gaussiennes seules ne sont pas une surface solide.

Pour éditer, ajouter des SOP après Spirula. Pour exporter cette sortie, saisir son chemin
dans SOP à exporter (facultatif), puis utiliser Export.
L’entrée optionnelle sert uniquement de source d’export ; elle ne remplace pas le splat affiché.

PLY exporte les attributs 3DGS standards et fait tourner les harmoniques jusqu’au degré 3.
BGEO conserve tous les attributs Houdini. Les extensions Spirula non standards ne passent pas par PLY.
Les couleurs HDR / ACEScg demandent un réglage de gestion couleur adapté et de désactiver sRGB → linéaire.
''')
definition.setExtraFileOption('Help/IsPython', False)
definition.addSection('OnCreated', '''import hou
if hou.isUIAvailable():
    import spirula_houdini
    node = kwargs['node']
    hou.ui.postEventCallback(lambda n=node: spirula_houdini.studio(n))
''')
definition.setExtraFileOption('OnCreated/IsPython', True)
definition.setParmTemplateGroup(asset.parmTemplateGroup())
definition.save(str(ROOT / 'otls' / 'SpirulaStudio.hda'), template_node=asset)
print('SAVED', len(definition.parmTemplateGroup().entries()), flush=True)
geo.destroy()
print('HDA BUILT', str(ROOT / 'otls' / 'SpirulaStudio.hda'), flush=True)

hou.hda.installFile(str(ROOT / 'otls' / 'SpirulaStudio.hda'))
g = hou.node('/obj').createNode('geo', 'SPIRULA_DEMO')
for c in g.children():
    c.destroy()
n = g.createNode('spirula::studio::1.0', 'spirula')
n.setDisplayFlag(True)
n.setRenderFlag(True)
n.setCurrent(True, clear_all_selected=True)
g.layoutChildren()
print('POINTS', len(n.geometry().points()), 'ATTRS', [a.name() for a in n.geometry().pointAttribs()], flush=True)
overlay = hou.node('/obj').createNode('geo', 'MODELER_ICI')
for c in overlay.children():
    c.destroy()
box = overlay.createNode('box', 'EXEMPLE_GEOMETRIE_3D')
box.parmTuple('size').set((.4,.4,.4))
box.parmTuple('t').set((0,1.35,0))
overlay.layoutChildren()
if (ROOT / 'examples' / 'demo_mesh.ply').exists():
    collision = hou.node('/obj').createNode('geo', 'MESH_COLLISION')
    for c in collision.children():
        c.destroy()
    f = collision.createNode('file', 'OUT_COLLISION')
    f.parm('file').set('$SPIRULA_ROOT/examples/demo_mesh.ply')
    collision.setDisplayFlag(False)
    n.parm('collisionpath').set(f.path())
hou.node('/obj').layoutChildren()
n.setCurrent(True, clear_all_selected=True)
hou.hipFile.save(str(ROOT / 'examples' / 'Spirula_Demo.hip'))



