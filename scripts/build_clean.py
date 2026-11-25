"""Build otls/SpirulaClean.hda  ->  spirula::clean_floaters::1.0  (run with hython)."""
import hou
from pathlib import Path

root = Path(__file__).resolve().parents[1]
file = str(root / 'otls' / 'SpirulaClean.hda')
geo = hou.node('/obj').createNode('geo', 'BUILD_CLEAN')
sub = geo.createNode('subnet')

parms = [
    hou.StringParmTemplate('help', 'But', 1, default_value=('Retire les gaussiennes parasites (quasi invisibles, géantes, isolées). '
        'Les structures fines opaques sont protégées. Heuristique : comparer Avant/Après.',)),
    hou.StringParmTemplate('status', 'Résultat', 1, default_value=('En attente',)),
    hou.MenuParmTemplate('mode', 'Mode', ['remove', 'show', 'pass'],
                         ['Retirer les floaters', 'Voir seulement ce qui serait retiré', 'Désactivé (laisser passer)']),
    hou.FloatParmTemplate('min_opacity', 'Opacité minimale', 1, default_value=(0.005,), min=0, max=0.5),
    hou.FloatParmTemplate('max_size_factor', 'Taille maximale (0 = désactivé)', 1, default_value=(12.0,), min=0, max=100),
    hou.IntParmTemplate('min_neighbours', 'Voisins minimum (0 = désactivé)', 1, default_value=(3,), min=0, max=50),
    hou.FloatParmTemplate('protect_opacity', 'Protéger au-dessus de cette opacité', 1, default_value=(0.25,), min=0, max=1),
    hou.FloatParmTemplate('voxel', 'Voxel (0 = automatique, unités scène)', 1, default_value=(0.0,), min=0),
]

py = sub.createNode('python', 'EVALUER')
py.parm('python').set('import hou,spirula_clean\nspirula_clean.evaluate(hou.pwd())')
py.setInput(0, sub.indirectInputs()[0])
blast = sub.createNode('blast', 'RETIRER')
blast.setInput(0, py)
blast.parm('grouptype').set('points')
blast.parm('group').setExpression(
    "'@spirula_floater>5' if ch('../mode')==2 else '@spirula_floater=1'", hou.exprLanguage.Python)
blast.parm('negate').setExpression("1 if ch('../mode')==1 else 0", hou.exprLanguage.Python)
out = sub.createNode('output')
out.setInput(0, blast)
out.setDisplayFlag(True)
out.setRenderFlag(True)
sub.layoutChildren()

asset = sub.createDigitalAsset(name='spirula::clean_floaters::1.0', hda_file_name=file,
                               description='Spirula · Nettoyer les floaters', min_num_inputs=1,
                               max_num_inputs=1, create_backup=False)
definition = asset.type().definition()
definition.setParmTemplateGroup(hou.ParmTemplateGroup(parms))
definition.setIcon('SOP_bakegsplat')
geo.destroy()
print('CLEAN_HDA_BUILT')

