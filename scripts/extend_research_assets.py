"""Add research controls without replacing the existing HDA internals."""
import hou

def primitive_template():
 return hou.MenuParmTemplate('primitive','Projection pendant l’apprentissage',['3dgs','mip','3dgut'],['Standard · 3DGS','Mip · anti-aliasing (évaluation)','Projection non linéaire · 3DGUT (expérimental)'])

def extend_all():
 for name in ['spirula::render_splat::1.0','spirula::arch_train::1.0','spirula::chain_train::1.0']:
  t=hou.nodeType(hou.sopNodeTypeCategory(),name)
  if t is None:continue
  d=t.definition();g=d.parmTemplateGroup()
  if not g.find('primitive'):
   p=primitive_template()
   if name=='spirula::arch_train::1.0':p.setConditional(hou.parmCondType.HideWhen,'{ method == 1 }')
   if g.find('train_tab'):
    folder=g.find('train_tab');folder.addParmTemplate(p);g.replace('train_tab',folder)
   else:g.insertBefore('iterations',p)
   d.setParmTemplateGroup(g)
 for name in ['spirula::render_splat::1.0','spirula::arch_train::1.0','spirula::chain_train::1.0']:
  t=hou.nodeType(hou.sopNodeTypeCategory(),name)
  if t is None:continue
  d=t.definition();g=d.parmTemplateGroup();p=g.find('primitive')
  if p:
   p.setMenuLabels(['Standard · 3DGS','Mip · anti-aliasing (évaluation)','Projection non linéaire · 3DGUT (évaluation)']);p.setHelp('Le choix concerne le trainer. Vérifier le résultat dans le viewport final : les renderers ne produisent pas exactement la même image. Ces variantes restent en évaluation.');g.replace('primitive',p);d.setParmTemplateGroup(g)
 for name in ['spirula::studio::1.0','spirula::render_splat::1.0','spirula::arch_train::1.0','spirula::chain_train::1.0']:
  t=hou.nodeType(hou.sopNodeTypeCategory(),name)
  if t is None:continue
  d=t.definition();g=d.parmTemplateGroup()
  if not g.find('engine_release'):
   p=hou.MenuParmTemplate('engine_release','Version du moteur',['stable','candidate'],['Exécutable actuel · 2026.10.16','Version récente · 2026.10.30 (évaluation)'])
   p.setHelp('Dans Studio, le choix s’applique à la prochaine réouverture après sauvegarde et fermeture de la session courante. Les checkpoints restent associés à leur version de moteur.')
   if name=='spirula::arch_train::1.0':p.setConditional(hou.parmCondType.HideWhen,'{ method == 1 }')
   if g.find('iterations'):g.insertBefore('iterations',p)
   elif g.find('executable'):g.insertBefore('executable',p)
   else:g.append(p)
   d.setParmTemplateGroup(g)
 for name,family in [('spirula::arch_export::1.0','spirula_arch'),('spirula::chain_export::1.0','spirula_chain')]:
  t=hou.nodeType(hou.sopNodeTypeCategory(),name)
  if t is None:continue
  d=t.definition();g=d.parmTemplateGroup()
  if not g.find('webfile'):
   file=hou.StringParmTemplate('webfile','Fichier compressé (.sog / .spz)',1);file.setStringType(hou.stringParmType.FileReference);file.setDefaultExpression(("str(__import__('pathlib').Path(hou.pwd().evalParm('exportfile') or hou.expandString('$HIP/scene_complete.ply')).with_suffix('.sog'))",));file.setDefaultExpressionLanguage((hou.scriptLanguage.Python,));device=hou.MenuParmTemplate('web_device','Calcul de compression',['auto','cpu','d3d12','vulkan'],['Automatique','CPU','WebGPU · Direct3D12','WebGPU · Vulkan']);parms=[file,device]
   for action,label in [('export_sog','Exporter compressé pour le web'),('export_monitor','Suivi de l’export'),('export_stop','Arrêter l’export')]:
    p=hou.ButtonParmTemplate(action,label);p.setScriptCallback("import hou,"+family+";hou.ui.postEventCallback(lambda n=kwargs['node']:"+family+".action(n,'"+action+"')) if hou.isUIAvailable() else "+family+".action(kwargs['node'],'"+action+"')");p.setScriptCallbackLanguage(hou.scriptLanguage.Python);parms.append(p)
   parms.append(hou.StringParmTemplate('jobfile','Job de conversion',1,is_hidden=True));anchor='export'
   for p in parms:g.insertAfter(anchor,p);anchor=p.name()
   d.setParmTemplateGroup(g)
  g=d.parmTemplateGroup()
  if not g.find('web_axes'):
   g.insertAfter('webfile',hou.MenuParmTemplate('web_axes','Axes pour le viewer',['playcanvas','preserve'],['PlayCanvas / SuperSplat · Y vertical','Conserver les axes du PLY']));d.setParmTemplateGroup(g)
 print('RESEARCH_CONTROLS_HDA_READY',flush=True)

if __name__=='__main__':extend_all()
