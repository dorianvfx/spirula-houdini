"""Build four explicit, reusable post-splat SOP stages."""
import hou
from pathlib import Path
root=Path(__file__).resolve().parents[1];file=str(root/'otls/SpirulaRefinement.hda');geo=hou.node('/obj').createNode('geo','BUILD_REFINEMENT')

def text(name,label,default='',reference=False,file=False):
    p=hou.StringParmTemplate(name,label,1,default_value=(default,))
    if reference:p.setStringType(hou.stringParmType.NodeReference)
    elif file:p.setStringType(hou.stringParmType.FileReference)
    return p

def button(name,label,command):
    p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import hou,spirula_refine;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_refine.action(n,'%s')) if hou.isUIAvailable() else spirula_refine.action(kwargs['node'],'%s')"%(command,command));p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p

def integer(name,label,value,minimum,maximum):return hou.IntParmTemplate(name,label,1,default_value=(value,),min=minimum,max=maximum,min_is_strict=True,max_is_strict=True)
def number(name,label,value,minimum=0):return hou.FloatParmTemplate(name,label,1,default_value=(value,),min=minimum,min_is_strict=True)

zone=[text('help','But','Réapprendre une zone avec les images sources ; multiplier les splats seul ne crée pas de détails.'),hou.MenuParmTemplate('method','Source des détails',['karma','photos'],['Scène Karma + mesh connu','Photos originales + caméras (Nerfstudio)']),text('mesh','Mesh SOP de référence',reference=True),text('lop_source','LOP complet éclairé',reference=True),text('dataset','Dossier photos + transforms.json','',file=True),number('units','Mètres par unité de la scène',1,1e-9),hou.FloatParmTemplate('center','Centre de zone (unités scène)',3,default_value=(0,1,0)),hou.FloatParmTemplate('size','Dimensions de zone (unités scène)',3,default_value=(1,1,.3)),button('select','Définir depuis des points sélectionnés','select'),button('fit','Cadrer tout le splat (attention au budget)','fit'),number('feather_m','Transition en mètres',.04),number('pixel_m','Détail cible Karma (mètres / pixel)',.003,1e-6),hou.MenuParmTemplate('axis','Côté à observer',['nz','pz','nx','px','py','ny'],['Façade −Z','Façade +Z','Façade −X','Façade +X','Dessus +Y','Dessous −Y']),integer('width','Largeur des vues Karma',1024,32,8192),integer('height','Hauteur des vues Karma',1024,32,8192),integer('samples','Échantillonnage Karma (budget au carré)',8,1,64),integer('max_views','Plafond de vues rapprochées',120,1,2000),integer('patch_cap','Budget gaussiennes (patch Karma / total photo)',2000000,100,12000000),integer('iterations','Itérations du raffinement photo',8000,1,200000),hou.ToggleParmTemplate('split','Subdiviser les gaussiennes de la zone avant réapprentissage photo',default_value=True),text('photo_help','Alignement','Photos perspective dédistordues et poses dans le même repère que le PLY. Pas de correction automatique d’un mauvais alignement.'),text('workspace','Dossier des calculs','$HIP/Projets/Raffinement',file=True),hou.ToggleParmTemplate('guides','Afficher la boîte de sélection',default_value=True),button('plan','Vérifier la zone et le nombre de vues','plan')]
zone.insert(6,text('photo_transform','Transformation dataset vers splat (matrice Houdini)','[]'))
for p in zone:
    if p.name()=='method':p.setMenuLabels(['Scène Karma + mesh connu','Photos originales + caméras (Nerfstudio / COLMAP)'])
    if p.name()=='dataset':p.setLabel('Dossier photos + caméras (Nerfstudio / COLMAP)')
    if p.name()=='photo_help':p.setDefaultValue(('Images et poses dans le repère du PLY. COLMAP : racine images/ + sparse/0/, caméras pinhole/radiales/OpenCV. Distorsion OpenCV rectifiée par le moteur. Vérifier l’alignement.',))
    if p.name() in ('mesh','lop_source','pixel_m','axis','width','height','samples','max_views'):p.setConditional(hou.parmCondType.HideWhen,'{ method == 1 }')
    if p.name() in ('dataset','photo_transform','iterations','split','photo_help'):p.setConditional(hou.parmCondType.HideWhen,'{ method == 0 }')
roles=[('refine_zone','06A · Zone à améliorer',zone),('refine_renders','06B · Images de détail',[text('help','Étape','Karma : nouveaux rendus rapprochés. Photos : vérification des originaux et des poses.'),button('renders','Produire / vérifier les images de détail','renders'),button('monitor','Voir les images et la progression','monitor'),button('stop','Arrêter après l’image courante','stop')]),('refine_apply','06C · Raffinement local du splat',[text('help','Étape','Reconstruire le patch avec les images. Les gaussiennes hors zone sont conservées. Le PLY original reste intact.'),button('apply','Calculer le candidat raffiné','apply'),button('monitor','Voir le calcul et le journal','monitor'),button('stop','Arrêter le raffinement','stop')]),('refine_check','06D · Comparer et valider le détail',[hou.MenuParmTemplate('compare','Comparaison dans le viewport',['before','after'],['Avant · splat original','Après · candidat raffiné']),text('help','Validation','Contrôler les gros plans, silhouettes et raccords. Valider seulement si le résultat est meilleur.'),button('accept','Valider le candidat affiché pour export','accept'),text('exportfile','PLY raffiné (export indépendant)','$HIP/splat_raffine.ply',file=True),button('export','Exporter le candidat validé','export')])]
for role,label,parms in roles:
    n=geo.createNode('subnet',role);base=[text('status','État','Prêt'),text('activity','Calcul','En attente'),number('progress','Progression (%)',0),text('elapsed','Temps écoulé','00:00:00'),hou.ToggleParmTemplate('running','Calcul actif',is_hidden=True)]
    templates=hou.ParmTemplateGroup(parms+base+[button('next','Étape suivante','next')]);n.setParmTemplateGroup(templates)
    if role in ('refine_renders','refine_apply'):n.createNode('spirula::render_splat::1.0','CAPTURE')
    py=n.createNode('python','DETAIL_OUTPUT');py.setInput(0,n.indirectInputs()[0]);py.parm('python').set('import hou,spirula_refine\nspirula_refine.geometry(hou.pwd(),'+repr(role)+')');out=n.createNode('output');out.setInput(0,py);out.setDisplayFlag(True);out.setRenderFlag(True);n.layoutChildren()
    asset=n.createDigitalAsset(name='spirula::'+role+'::1.0',hda_file_name=file,description=label,min_num_inputs=1,max_num_inputs=1,create_backup=False);d=asset.type().definition();d.setParmTemplateGroup(templates);d.setIcon('SOP_bakegsplat')
    if role in ('refine_renders','refine_apply'):d.addSection('EditableNodes','CAPTURE')
geo.destroy();print('REFINEMENT_FOUR_STAGE_HDA_BUILT',flush=True)
