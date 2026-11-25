from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[1]
hou.putenv('SPIRULA_ROOT',str(ROOT).replace('\\','/'))
hou.Geometry().saveToFile(str(ROOT/'examples/empty.bgeo'))

def text(name,label,default='',file=False):
    p=hou.StringParmTemplate(name,label,1,default_value=(default,))
    if file:
        p.setStringType(hou.stringParmType.FileReference)
        if name=='workspace':p.setFileType(hou.fileType.Directory)
    if name in ('source','seed','path_sop','lop_source','box_object','scan_source'):
        p.setStringType(hou.stringParmType.NodeReference)
        p.setTags({'opfilter':'Lop' if name=='lop_source' else 'Object' if name=='box_object' else 'Sop','oprelative':'.'})
    return p

def button(name,label,module):
    p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import %s; %s.callback(kwargs['node'])"%(module,module));p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p

def save(sub,name,label,inputs):
    n=sub.createDigitalAsset(name=name,hda_file_name=str(ROOT/'otls/SpirulaWorkbench.hda'),description=label,min_num_inputs=0,max_num_inputs=inputs,create_backup=False)
    d=n.type().definition();d.setParmTemplateGroup(n.parmTemplateGroup());d.updateFromNode(n);d.setIcon('SOP_bakegsplat');d.save(str(ROOT/'otls/SpirulaWorkbench.hda'),template_node=n,create_backup=False);return n

g=hou.node('/obj').createNode('geo','workbench_build')
s=g.createNode('subnet','object_splat')
s.setParmTemplateGroup(hou.ParmTemplateGroup([
 text('source','SOP source (si aucune entrée)'),
 hou.IntParmTemplate('budget','Densité visée (estimation)',1,default_value=(1000000,),min=10000,max=5000000),
 hou.FloatParmTemplate('spacing','Arête maximale (0 = automatique)',1,default_value=(0,),min=0),
 hou.IntParmTemplate('limit','Limite de gaussiennes',1,default_value=(6000000,),min=10000,max=12000000),
 hou.FloatParmTemplate('coverage','Recouvrement des gaussiennes',1,default_value=(1.8,),min=.5,max=3),
 hou.FloatParmTemplate('thickness','Épaisseur / taille de cellule',1,default_value=(.035,),min=.001,max=.3),
 hou.FloatParmTemplate('opacity','Opacité au centre',1,default_value=(.995,),min=.01,max=.9999),
 hou.ToggleParmTemplate('lighting','Éclairage diffus studio fixe',default_value=False),
 hou.FloatParmTemplate('fallback','Couleur sans matériau',3,default_value=(.5,.5,.5)),
 text('workspace','Dossier des caches','$HIP/spirula/objects/$OS',True),
 button('build','Convertir le mesh en gaussiennes','spirula_object'),
 text('splatfile','Cache PLY','$SPIRULA_ROOT/examples/empty.bgeo',True),
 text('status','État','Brancher un mesh texturé, régler la précision, puis Convertir.')]))
f=s.createNode('file','read_splat');f.parm('file').setExpression('chs("../splatfile")')
b=s.createNode('bakegsplat','NATIVE_GSPLATS');b.setInput(0,f);b.parm('sphcoeff').set(1)
o=s.createNode('null','OUT_SPLAT');o.setInput(0,b);o.setDisplayFlag(True);o.setRenderFlag(True);s.layoutChildren()
save(s,'spirula::object_splat::1.0','Spirula Object to Splat',1)

s=g.createNode('subnet','assembly')
sources=text('sources','Sources SOP (espaces ou lignes)');sources.setTags({'editor':'1','editorlines':'5','opfilter':'Sop','oprelative':'.'})
s.setParmTemplateGroup(hou.ParmTemplateGroup([sources,text('exportfile','Export PLY complet','$HIP/spirula/export/composition.ply',True),button('export','Exporter toute la composition','spirula_scene'),text('status','État','Ajouter les chemins des sorties GSplats natives.')]))
m=s.createNode('python','COMPOSE_WORLD');m.parm('python').set('import hou, spirula_scene\nspirula_scene.cook(hou.pwd())')
o=s.createNode('null','OUT_ALL_SPLATS');o.setInput(0,m);o.setDisplayFlag(True);o.setRenderFlag(True);s.layoutChildren()
save(s,'spirula::assemble_splats::1.0','Spirula Assemble Splats',0)

s=g.createNode('subnet','cut')
owner=text('owner','Objet source');owner.setDefaultExpression(('hou.pwd().creator().path()',));owner.setDefaultExpressionLanguage((hou.scriptLanguage.Python,));owner.hide(True)
s.setParmTemplateGroup(hou.ParmTemplateGroup([hou.ToggleParmTemplate('enable','Activer le retrait',default_value=False),text('box_object','Objet boîte de découpe'),hou.ToggleParmTemplate('keep_inside','Garder seulement l’intérieur',default_value=False),owner,text('status','Principe','Déplacer la boîte avec les handles Houdini, puis activer le retrait. Les originaux restent intacts.')]))
w=s.createNode('attribwrangle','REMOVE_INSIDE_BOX');w.setInput(0,s.indirectInputs()[0]);w.parm('snippet').set('''if (!chi("../enable") || chs("../box_object")=="") return;
matrix world=optransform(chs("../owner"));
matrix box=optransform(chs("../box_object"));
vector p=(@P*world)*invert(box);
int inside=max(abs(p.x),max(abs(p.y),abs(p.z)))<=0.5;
if (inside != chi("../keep_inside")) removepoint(0,@ptnum);
''')
o=s.createNode('null','OUT_CLEAN_SPLAT');o.setInput(0,w);o.setDisplayFlag(True);o.setRenderFlag(True);s.layoutChildren()
save(s,'spirula::cut_splats::1.0','Spirula Cut Splats',1)

def render_button(name,label,action):
    p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import spirula_render; spirula_render.callback(kwargs['node'],'%s')"%action);p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p

def preset_button(name,label):
    p=hou.ButtonParmTemplate('preset_'+name,label);p.setScriptCallback("import spirula_render; spirula_render.preset(kwargs['node'],'%s')"%name);p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p

s=g.createNode('subnet','render_splat')
s.setParmTemplateGroup(hou.ParmTemplateGroup([
 hou.FolderParmTemplate('scan_tab','Objet éclairé par le scan',parm_templates=[hou.ToggleParmTemplate('scan_lighting','Éclairer l’objet par le Gaussian splat (Karma XPU)',default_value=False),text('scan_source','SOP du décor Gaussian splat'),text('scan_info','Méthode','Rayons indirects dans le scan, sans lumière automatique. Aperçu puis apprentissage. L’intensité HDR perdue n’est pas récupérée.')]),
 hou.FolderParmTemplate('scene_tab','Scène',parm_templates=[text('source','Mesh / SOP de référence'),hou.MenuParmTemplate('backend','Renderer',['mantra','karma_obj','karma_cpu','karma_xpu'],['Mantra PBR · OBJ','Karma CPU · OBJ','Karma CPU · Solaris','Karma XPU · Solaris'],default_value=1),text('lop_source','LOP final (Solaris)'),text('render_settings','ROP existant / USD Render Settings (facultatif)'),text('objects','Objets à rendre (OBJ)','*'),hou.ToggleParmTemplate('isolate','Isoler le mesh/SOP de référence',default_value=True),hou.ToggleParmTemplate('studio_lights','Ajouter 3 lumières studio fixes',default_value=False)]),
 hou.FolderParmTemplate('camera_tab','Caméras',parm_templates=[hou.MenuParmTemplate('capture_mode','Disposition',['orbit','cameras','path','facade'],['Tour d’objet','Caméras existantes / animées','Parcours intérieur','Façades / objet géant par tuiles']),hou.IntParmTemplate('views','Vues / tour ou directions / position',1,default_value=(24,),min=3,max=128),text('elevations','Angles verticaux (degrés)','-20 15 50'),hou.FloatParmTemplate('radius','Rayon (0 = automatique)',1,default_value=(0,),min=0),hou.FloatParmTemplate('fov','Champ horizontal (degrés)',1,default_value=(65,),min=15,max=130),text('cameras','Caméras OBJ (chemins séparés)'),text('camera_frames','Images des poses caméra (facultatif)'),text('path_sop','Courbe du parcours intérieur'),hou.FloatParmTemplate('target_detail','Précision façade (unités / pixel)',1,default_value=(.01,),min=.000001),hou.IntParmTemplate('max_views','Limite de vues par capture',1,default_value=(1000,),min=6,max=100000),hou.IntParmTemplate('path_positions','Positions du parcours',1,default_value=(12,),min=2,max=1000),hou.FloatParmTemplate('eye_height','Hauteur ajoutée au parcours',1,default_value=(1.6,))]),
 hou.FolderParmTemplate('render_tab','Rendus',parm_templates=[preset_button('preview','Préréglage aperçu rapide'),preset_button('high','Préréglage architecture haute qualité'),preset_button('production','Préréglage production détaillée'),hou.IntParmTemplate('width','Largeur',1,default_value=(1024,),min=64,max=8192),hou.IntParmTemplate('height','Hauteur',1,default_value=(1024,),min=64,max=8192),hou.IntParmTemplate('samples','Qualité échantillonnage',1,default_value=(8,),min=1,max=64),hou.FloatParmTemplate('exposure','Exposition PNG (EV, identique pour toutes les vues)',1,default_value=(0,)),hou.ToggleParmTemplate('hdr','Entraîner depuis les EXR linéaires HDR',default_value=False),text('working_space','Espace des EXR (vide = rôle OCIO scene_linear)'),text('display','Affichage OCIO (vide = défaut)'),text('view','Vue OCIO (vide = défaut)')]),
 hou.FolderParmTemplate('train_tab','Apprentissage',parm_templates=[hou.IntParmTemplate('iterations','Itérations',1,default_value=(15000,),min=1,max=100000),hou.IntParmTemplate('cap','Limite de gaussiennes',1,default_value=(2000000,),min=10000,max=10000000),text('seed','SOP des points de départ (facultatif)'),text('device','GPU Spirula','auto')]),
 hou.FolderParmTemplate('job_tab','Calcul',parm_templates=[text('workspace','Dossier des jobs','$HIP/spirula/render_jobs/$OS',True),render_button('start','Rendre les vues puis entraîner le splat','start'),render_button('render','Rendre le dataset seulement','render'),render_button('preview','Tester une image avant le calcul complet','preview'),render_button('open_folder','Ouvrir le dossier des rendus et journaux','folder'),render_button('resume','Reprendre le job existant','resume'),render_button('stop','Arrêter après le rendu courant','stop'),text('jobfile','Job JSON',file=True),render_button('camera_guides','Afficher les repères des caméras','cameras'),text('capture_summary','Capture prévue','Aperçu = vérification technique. Pour une visite : couverture complète et réglages haute qualité.'),text('status','État','Configurer une scène éclairée et des caméras ; les calculs tournent en arrière-plan.')]),
 hou.FolderParmTemplate('output_tab','Résultat',parm_templates=[text('splatfile','Splat appris','$SPIRULA_ROOT/examples/empty.bgeo',True),text('result_transform','Transformation du résultat (automatique)','[]')])]))
f=s.createNode('file','read_splat');f.parm('file').setExpression('chs("../splatfile")');b=s.createNode('bakegsplat','NATIVE_GSPLATS');b.setInput(0,f);b.parm('sphcoeff').set(1);b.parm('linearize').setExpression('1-ch("../hdr")')
placed=s.createNode('python','PLACE_RESULT');placed.setInput(0,b);placed.parm('python').set('import hou,spirula_insert\nspirula_insert.output_geometry(hou.pwd())');o=s.createNode('null','OUT_TRAINED_SPLAT');o.setInput(0,placed);o.setDisplayFlag(True);o.setRenderFlag(True);s.layoutChildren();save(s,'spirula::render_splat::1.0','Spirula Render to Splat',0)
# Compact artist-facing wrapper; advanced controls remain inside CAPTURE.
s=g.createNode('subnet','insert_asset')
def insert_button(name,label,action):
 p=hou.ButtonParmTemplate(name,label);p.setScriptCallback("import spirula_insert;spirula_insert.simple_callback(kwargs['node'],'%s')"%action);p.setScriptCallbackLanguage(hou.scriptLanguage.Python);return p
mesh=text('mesh','1 · Objet 3D (SOP)');mesh.setStringType(hou.stringParmType.NodeReference)
scan=text('scan','2 · Décor Gaussian splat (SOP)');scan.setStringType(hou.stringParmType.NodeReference)
state=text('status','État');state.setDefaultExpression(('chs("CAPTURE/status")',))
s.setParmTemplateGroup(hou.ParmTemplateGroup([insert_button('pipeline','Ouvrir le pipeline guidé','workflow'),hou.ToggleParmTemplate('running','Calcul actif',default_value=False,is_hidden=True),state,text('activity','Étape actuelle','Prêt'),hou.FloatParmTemplate('progress','Progression de l’étape (%)',1,default_value=(0,),min=0,max=100),text('elapsed','Temps écoulé','00:00:00'),insert_button('monitor','Ouvrir le suivi en direct','monitor'),mesh,scan,hou.MenuParmTemplate('quality','3 · Qualité',['preview','high','production'],['Test technique','Haute qualité · 108 vues / 1536²','Production · 108 vues / 2048²'],default_value=2),hou.FloatParmTemplate('exposure','Exposition de sortie (EV)',1,default_value=(2,)),hou.FloatParmTemplate('detail','Détail cible (unités/pixel ; 0 = tour automatique)',1,default_value=(0,),min=0),hou.IntParmTemplate('max_views','Limite de vues pour façades',1,default_value=(1000,),min=6,max=100000),insert_button('preview','4 · Voir l’objet éclairé par le scan','preview'),insert_button('image','Revoir l’aperçu dans Houdini','image'),insert_button('folder','Dossier des rendus / journaux','folder'),insert_button('build','5 · Générer le splat final de l’objet','start'),insert_button('stop','Arrêter après l’image en cours','stop'),insert_button('resume','Reprendre le calcul','resume'),text('workspace','Dossier des calculs','$HIP/spirula_insert_jobs/$OS',True),text('exportfile','Fichier final décor + objet','$HIP/Decor_avec_objet.ply',True),insert_button('export','6 · Exporter décor + objet en PLY','export'),text('method','Éclairage','Karma XPU : rayons indirects dans le scan. Source HDR non récupérée. CPU utilisé en l’absence de GPU NVIDIA compatible.'),text('advanced','Réglages avancés','Entrer dans ce nœud : CAPTURE contient caméras, itérations et réglages détaillés.')]))
group=s.parmTemplateGroup()
for name in ('mesh','scan','quality','exposure','detail','max_views','preview','build','resume','workspace','exportfile','export'):
 template=group.find(name);template.setConditional(hou.parmCondType.DisableWhen,'{ running == 1 }');group.replace(name,template)
s.setParmTemplateGroup(group)
capture=s.createNode('spirula::render_splat::1.0','CAPTURE');capture.parm('scan_lighting').set(1)
o=s.createNode('null','OUT_INSERTED_SPLAT');o.setInput(0,capture);o.setDisplayFlag(True);o.setRenderFlag(True);s.layoutChildren();asset=save(s,'spirula::insert_asset::1.0','Spirula Insert Lit Object',0);asset.type().definition().addSection('EditableNodes','CAPTURE')
asset.type().definition().addSection('OnLoaded',"import hou\nif hou.isUIAvailable() and kwargs['node'].userData('spirula_workflow_auto')=='1':\n from PySide6.QtCore import QTimer\n import spirula_workflow\n path=kwargs['node'].path()\n hou.ui.postEventCallback(lambda p=path:spirula_workflow.open(hou.node(p)) if hou.node(p) else None)\n")
asset.type().definition().setExtraFileOption('OnLoaded/IsPython',True)
asset.type().definition().addSection('OnCreated',asset.type().definition().sections()['OnLoaded'].contents().replace(" and kwargs['node'].userData('spirula_workflow_auto')=='1'",''))
asset.type().definition().setExtraFileOption('OnCreated/IsPython',True)

g.destroy()
print('WORKBENCH_HDA_BUILT',flush=True)





from extend_research_assets import extend_all
extend_all()
