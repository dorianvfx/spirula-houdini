import hou
from pathlib import Path
root=Path(__file__).resolve().parents[1];file=str(root/'otls/SpirulaArchitecture.hda');g=hou.node('/obj').createNode('geo','BUILD_ARCHITECTURE')
def text(name,label,default='',file=False):
 p=hou.StringParmTemplate(name,label,1,default_value=(default,))
 if file:p.setStringType(hou.stringParmType.FileReference)
 if name=='lop_source':p.setStringType(hou.stringParmType.NodeReference)
 return p
def button(name,label,action):
 p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import hou,spirula_arch;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_arch.action(n,'%s')) if hou.isUIAvailable() else spirula_arch.action(kwargs['node'],'%s')"%(action,action));p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p
def build(role,label,parms):
 n=g.createNode('subnet',role);base=[text('status','État','Prêt'),text('activity','Calcul','En attente'),hou.FloatParmTemplate('progress','Progression (%)',1,default_value=(0,),min=0,max=100),text('elapsed','Temps écoulé','00:00:00'),hou.ToggleParmTemplate('running','Calcul actif',is_hidden=True)]
 templates=hou.ParmTemplateGroup(parms+base+[button('next','Étape suivante','next')])
 if role=='train':
  for name,condition in [('iterations','{ method == 1 }'),('method_help','{ method == 0 }')]:
   t=templates.find(name);t.setConditional(hou.parmCondType.HideWhen,condition);templates.replace(name,t)
 n.setParmTemplateGroup(templates)
 if role=='source':
  imp=n.createNode('lopimport','SCENE_USD');imp.parm('loppath').setExpression('chs("../lop_source")');imp.parm('primpattern').setExpression('chs("../preview_prims")');imp.parm('importtraversal').set('std:boundables');imp.parm('purpose').set('default render');unique=n.createNode('python','UNIQUE_USD_PRIMS');unique.setInput(0,imp);unique.parm('python').set('import hou,spirula_arch\nspirula_arch.unique_usd_geometry(hou.pwd())');unpack=n.createNode('unpack','SEED_NATIVE');unpack.setInput(0,unique);unpack.parm('iterations').set(8);out=n.createNode('output');out.setInput(0,unique)
 elif role in ('result','export'):
  out=n.createNode('output');out.setInput(0,n.indirectInputs()[0])
 else:
  if role in ('renders','train'):n.createNode('spirula::render_splat::1.0','CAPTURE')
  py=n.createNode('python');py.parm('python').set('import hou,spirula_arch\nspirula_arch.geometry(hou.pwd(),'+repr(role)+')');py.setInput(0,n.indirectInputs()[0]);out=n.createNode('output');out.setInput(0,py)
 out.setDisplayFlag(True);out.setRenderFlag(True);n.layoutChildren();a=n.createDigitalAsset(name='spirula::arch_'+role+'::1.0',hda_file_name=file,description=label,min_num_inputs=0 if role=='source' else 1,max_num_inputs=0 if role=='source' else 1,create_backup=False);d=a.type().definition();d.setParmTemplateGroup(templates);d.setIcon('SOP_bakegsplat')
 if role in ('renders','train'):d.addSection('EditableNodes','CAPTURE')
 if role=='source':
  d.addSection('OnLoaded',"import hou,importlib,spirula_arch\nif getattr(spirula_arch,'PIPELINE_REVISION','')!='7.2.0':importlib.reload(spirula_arch)\nif hou.isUIAvailable() and kwargs['node'].creator().userData('spirula_arch'):\n import spirula_arch\n hou.ui.postEventCallback(lambda r=kwargs['node'].creator():spirula_arch.focus(r))\n");d.setExtraFileOption('OnLoaded/IsPython',True)
 return a
build('source','01 · Scène Solaris / Karma',[text('lop_source','LOP final de la scène'),text('targets','Chemins USD du bâtiment à cadrer',''),text('settings_path','Render Settings USD existants (facultatif)',''),text('preview_prims','Primitives affichées / graines','*'),text('workspace','Dossier du projet','$HIP/Projets/Architecture',True),text('help','Utilisation','Référencer la scène complète éclairée. Cadrer le bâtiment, pas un sol immense ou le ciel.'),button('check','Vérifier la scène et le budget','check')])
build('cameras','02 · Caméras autour du bâtiment',[hou.MenuParmTemplate('mode','Disposition',['orbit','facades'],['Tour autour du bâtiment','Façades par précision cible']),hou.IntParmTemplate('views','Directions par niveau',1,default_value=(24,),min=3,max=1000),text('elevations','Angles verticaux','0 15 35'),hou.FloatParmTemplate('fov','Champ horizontal (degrés)',1,default_value=(65,),min=10,max=149),hou.FloatParmTemplate('margin','Marge de cadrage',1,default_value=(1.12,),min=1,max=3),hou.FloatParmTemplate('min_height','Hauteur minimale depuis la base (m)',1,default_value=(1.6,),min=0),hou.FloatParmTemplate('detail','Précision façade (mètres / pixel)',1,default_value=(.01,),min=.000001),hou.IntParmTemplate('max_views','Limite de vues',1,default_value=(1500,),min=3,max=100000),text('extra_cameras','Caméras de détail OBJ ou USD (facultatif)'),hou.ToggleParmTemplate('guides','Afficher les repères',default_value=False),button('show','Construire et afficher les caméras','cameras')])
build('preview','03 · Aperçu Karma et validation',[text('help','Étape','Rendre une vue de la scène complète, contrôler matériaux et lumière, puis valider.'),button('preview','Calculer l’aperçu Karma','preview'),button('monitor','Voir l’image et la progression','monitor'),button('approve','Valider l’aperçu actuel','approve')])
build('renders','04 · Rendus Karma du dataset',[hou.IntParmTemplate('width','Largeur des images',1,default_value=(1024,),min=32,max=8192),hou.IntParmTemplate('height','Hauteur des images',1,default_value=(768,),min=32,max=8192),hou.IntParmTemplate('samples','Qualité échantillonnage (budget au carré)',1,default_value=(8,),min=1,max=64),hou.FloatParmTemplate('exposure','Exposition de conversion PNG (EV)',1,default_value=(0,)),hou.ToggleParmTemplate('hdr','HDR avancé',default_value=False,is_hidden=True),button('render','Rendre les images seulement','renders'),button('monitor','Voir les rendus en direct','monitor'),button('stop','Arrêter après l’image courante','stop')])
build('train','05 · Apparence et génération du splat',[hou.MenuParmTemplate('method','Méthode',['spirula','surface'],['Apprentissage libre · Spirula','Mesh connu · radiance sur surfaces']),text('method_help','Surface connue','Géométrie fixe, couleurs des rendus, surfaces non observées exclues. Extérieur statique ; reflets dépendants de la vue non appris.'),hou.IntParmTemplate('iterations','Itérations',1,default_value=(30000,),min=1,max=200000),hou.IntParmTemplate('cap','Limite de gaussiennes',1,default_value=(3000000,),min=10000,max=12000000),button('train','Générer depuis le dataset 04 / reprendre','train'),button('monitor','Voir l’apprentissage en direct','monitor'),button('stop','Arrêter l’apprentissage','stop')])
build('result','06 · Splat dans le viewport',[text('help','Vérification','Inspecter silhouette, détails, reflets et déplacement avant export. Les réglages seuls ne garantissent pas la qualité.'),button('check','Afficher les informations de capture','check')])
build('export','07 · Export PLY de la scène',[text('exportfile','Fichier PLY final','$HIP/scene_complete.ply',True),button('export','Exporter le splat complet','export')])
g.destroy();print('ARCHITECTURE_HDA_BUILT',flush=True)

from extend_research_assets import extend_all
extend_all()
from extend_refinement_assets import extend_all as extend_refinement
extend_refinement()
