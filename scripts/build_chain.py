from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1];FILE=str(ROOT/'otls/SpirulaChain.hda');g=hou.node('/obj').createNode('geo','BUILD_CHAIN')
def text(name,label,default='',file=False):
 p=hou.StringParmTemplate(name,label,1,default_value=(default,))
 if file:p.setStringType(hou.stringParmType.FileReference)
 if name=='file':p.setScriptCallback("kwargs['node'].parm('mode').set(1)");p.setScriptCallbackLanguage(hou.scriptLanguage.Python)
 return p
def button(name,label,action):
 p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import hou,spirula_chain;hou.ui.postEventCallback(lambda n=kwargs['node']:spirula_chain.action(n,'%s')) if hou.isUIAvailable() else spirula_chain.action(kwargs['node'],'%s')"%(action,action));p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p
def common(note):
 return [button('audit','Vérifier tout le pipeline','audit'),text('instruction','Étape',note),text('status','État','En attente'),text('activity','Calcul','Prêt'),hou.FloatParmTemplate('progress','Progression (%)',1,default_value=(0,),min=0,max=100),text('elapsed','Temps écoulé','00:00:00'),hou.ToggleParmTemplate('running','Calcul actif',default_value=False,is_hidden=True)]
def build(role,label,inputs,parms):
 templates=hou.ParmTemplateGroup(common(label)+parms+[button('next','Étape suivante','next')]);s=g.createNode('subnet',role);s.setParmTemplateGroup(templates)
 if role=='render':
  capture=s.createNode('spirula::render_splat::1.0','CAPTURE');out=s.createNode('output','OUT_CONTEXTE');out.setInput(0,s.indirectInputs()[0])
 elif role=='export':out=s.createNode('output','OUT_SCENE');out.setInput(0,s.indirectInputs()[0])
 else:
  if role=='train':s.createNode('spirula::render_splat::1.0','CAPTURE')
  py=s.createNode('python','EVALUER');py.parm('python').set("import hou,spirula_chain\nspirula_chain.geometry(hou.pwd(),'%s')"%role)
  for i in range(inputs):py.setInput(i,s.indirectInputs()[i])
  out=s.createNode('output','OUT');out.setInput(0,py)
 out.setDisplayFlag(True);out.setRenderFlag(True);s.layoutChildren()
 a=s.createDigitalAsset(name='spirula::chain_%s::1.0'%role,hda_file_name=FILE,description=label,min_num_inputs=0,max_num_inputs=inputs,create_backup=False)
 d=a.type().definition();d.updateFromNode(a);d.setParmTemplateGroup(templates);d.setIcon('SOP_bakegsplat');d.save(FILE,template_node=a,create_backup=False)
 if role in ('render','train'):d.addSection('EditableNodes','CAPTURE')
 if role=='mesh':
  d.addSection('OnInputChanged',"n=kwargs['node']\nn.parm('mode').set(0 if n.inputs() and n.inputs()[0] is not None else 1)\n");d.setExtraFileOption('OnInputChanged/IsPython',True)
 return a
build('scan','02 · Scan Houdini / orientation',1,[hou.FloatParmTemplate('t','Translation du scan',3),hou.FloatParmTemplate('r','Rotation du scan',3),hou.FloatParmTemplate('s','Échelle XYZ du scan',3,default_value=(1,1,1))])
build('mesh','03 · Objet 3D',1,[text('help','Source','Brancher un SOP de modélisation dans ce même réseau, ou charger un fichier.'),hou.MenuParmTemplate('mode','Source utilisée',['input','file','existing'],['Entrée connectée dans ce réseau','Fichier 3D','SOP existant'],default_value=1),text('file','Fichier mesh',file=True),text('source','SOP existant'),button('pick','Utiliser le mesh sélectionné','pick')])
build('light','05 · Éclairage par le scan',2,[hou.FloatParmTemplate('exposure','Exposition des rendus (EV)',1,default_value=(2,)),button('preview','Calculer un aperçu éclairé','preview'),button('monitor','Voir le calcul / le rendu','monitor'),button('approve','Valider cet éclairage et passer en 06','approve')])
build('cameras','06 · Caméras de capture',1,[hou.MenuParmTemplate('mode','Disposition',['orbit','facade'],['Tour d’objet','Façades par tuiles']),hou.IntParmTemplate('views','Vues par tour',1,default_value=(36,),min=3,max=1000),text('elevations','Angles verticaux','-25 10 45'),hou.FloatParmTemplate('radius','Rayon (0 = automatique)',1,default_value=(0,),min=0),hou.FloatParmTemplate('fov','Champ horizontal',1,default_value=(65,),min=10,max=140),hou.FloatParmTemplate('detail','Façade : unités par pixel',1,default_value=(.01,),min=.000001),hou.IntParmTemplate('max_views','Limite de vues',1,default_value=(1000,),min=6,max=100000),hou.ToggleParmTemplate('show_cameras','Afficher les repères des caméras',default_value=False),hou.FloatParmTemplate('guide_size','Taille des repères',1,default_value=(.15,),min=.001),button('show','Construire / afficher les caméras','cameras')])
build('render','07 · Rendus Karma',1,[hou.IntParmTemplate('width','Largeur',1,default_value=(1536,),min=64,max=8192),hou.IntParmTemplate('height','Hauteur',1,default_value=(1536,),min=64,max=8192),hou.IntParmTemplate('samples','Qualité échantillonnage',1,default_value=(12,),min=1,max=64),button('render','Rendre toutes les vues (sans apprentissage)','render'),button('monitor','Suivi des rendus','monitor'),button('stop','Arrêter après l’image courante','stop')])
build('train','08 · Apprentissage du splat',1,[hou.IntParmTemplate('iterations','Itérations Spirula',1,default_value=(30000,),min=1,max=200000),hou.IntParmTemplate('cap','Limite de gaussiennes',1,default_value=(4000000,),min=10000,max=12000000),button('train','Entraîner depuis les rendus 07 / reprendre','train'),button('monitor','Suivi de l’apprentissage','monitor'),button('stop','Arrêter l’apprentissage','stop')])
build('assemble','09 · Assemblage scan et objet',2,[text('help','Composition','Entrée 1 : décor. Entrée 2 : objet appris en 08. Tout reste dans ce Geo.')])
build('export','10 · Export et répétition',1,[text('exportfile','PLY final',file=True),button('export','Exporter toute la scène en PLY','export'),button('repeat','Ajouter un autre objet : répéter 03 → 10 ici','repeat')])
g.destroy()
studio=hou.nodeType(hou.sopNodeTypeCategory(),'spirula::studio::1.0').definition()
studio.addSection('OnLoaded',"import hou\nif hou.isUIAvailable() and kwargs['node'].userData('spirula_chain_root'):\n import spirula_chain\n root=kwargs['node'].creator()\n hou.ui.postEventCallback(lambda r=root:spirula_chain.focus(r,r.userData('spirula_chain_auto_studio')=='1'))\n")
studio.setExtraFileOption('OnLoaded/IsPython',True)
print('CHAIN_HDA_BUILT',flush=True)

from extend_research_assets import extend_all
extend_all()
