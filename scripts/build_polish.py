"""Build otls/SpirulaPolish.hda -> spirula::polish::1.0  (run with hython)."""
import hou
from pathlib import Path

root = Path(__file__).resolve().parents[1]
file = str(root / 'otls' / 'SpirulaPolish.hda')
geo = hou.node('/obj').createNode('geo', 'BUILD_POLISH')
sub = geo.createNode('subnet')


def button(name, label, fn):
    p = hou.ButtonParmTemplate(name, label)
    p.setScriptCallback("import hou,spirula_polish\ntry:\n spirula_polish.%s(kwargs['node'])\nexcept Exception as e:\n"
                        " kwargs['node'].parm('status').set(str(e))\n hou.ui.displayMessage(str(e),severity=hou.severityType.Error) if hou.isUIAvailable() else None" % fn)
    p.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    return p


parms = [
    hou.StringParmTemplate('help', 'But', 1, default_value=(
        'Passe de raffinement par apprentissage : reprend le splat et ses photos, continue l\'entraînement '
        'en pleine résolution avec densification. Ajoute du détail visible dans les photos ; ne peut pas inventer ce qu\'aucune photo ne montre.',)),
    hou.StringParmTemplate('dataset', 'Dossier photos + caméras (COLMAP sparse/0 ou transforms.json)', 1, string_type=hou.stringParmType.FileReference),
    hou.StringParmTemplate('start_ply', 'PLY de départ (vide = exporter l\'entrée)', 1, string_type=hou.stringParmType.FileReference),
    hou.MenuParmTemplate('preset', 'Qualité', ['rapide', 'standard', 'maximum'],
                         ['Rapide (aperçu, ~3 000 étapes, demi-résolution)', 'Standard (8 000 étapes, pleine résolution)', 'Maximum (20 000 étapes, 6 M splats)'], default_value=1),
    hou.IntParmTemplate('iterations', 'Étapes (0 = selon la qualité)', 1, default_value=(0,), min=0),
    hou.ToggleParmTemplate('holdout', 'Mettre de côté 1 photo sur 8 pour mesurer le gain', default_value=True),
    hou.StringParmTemplate('workspace', 'Dossier de travail', 1, default_value=('$HIP/Polish',), string_type=hou.stringParmType.FileReference),
    button('go', 'Lancer le raffinement', 'ui_start'),
    button('refresh', 'Actualiser', 'ui_refresh'),
    button('halt', 'Arrêter', 'ui_stop'),
    hou.StringParmTemplate('status', 'État', 1, default_value=('Prêt',)),
    hou.MenuParmTemplate('show', 'Afficher', ['before', 'after'], ['Avant (splat d\'entrée)', 'Après (raffiné)']),
    hou.StringParmTemplate('result', 'PLY raffiné', 1, string_type=hou.stringParmType.FileReference),
]

reader = sub.createNode('file', 'LIRE_RESULTAT')
reader.parm('file').setExpression('chs("../result")', hou.exprLanguage.Hscript)
reader.parm('missingfile').set('none') if reader.parm('missingfile') else None
bake = sub.createNode('bakegsplat', 'BAKE_GSPLATS')
bake.setInput(0, reader)
switch = sub.createNode('switch', 'AVANT_APRES')
switch.setInput(0, sub.indirectInputs()[0])
switch.setInput(1, bake)
switch.parm('input').setExpression('ch("../show")==1 && strlen(chs("../result"))>0', hou.exprLanguage.Hscript)
out = sub.createNode('output')
out.setInput(0, switch)
out.setDisplayFlag(True)
out.setRenderFlag(True)
sub.layoutChildren()

asset = sub.createDigitalAsset(name='spirula::polish::1.0', hda_file_name=file,
                               description='Spirula · Raffiner par apprentissage', min_num_inputs=1, max_num_inputs=1, create_backup=False)
definition = asset.type().definition()
definition.setParmTemplateGroup(hou.ParmTemplateGroup(parms))
definition.setIcon('SOP_bakegsplat')
geo.destroy()
print('POLISH_HDA_BUILT')

