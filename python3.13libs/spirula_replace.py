"""Non destructive object removal and explicit background repair in the SOP chain."""
import numpy as np


def evaluate(node,role):
 import hou
 stage=node.parent();out=node.geometry();out.clear();source=stage.inputs()[0]
 if source is None:return
 out.merge(source.geometry())
 if role=='selection':
  group=out.createPointGroup('spirula_remove')
  if stage.evalParm('mode')==0:
   pattern=stage.evalParm('points').strip()
   if pattern:group.add(out.globPoints(pattern))
  else:
   size=np.array(stage.evalParmTuple('size'))
   if np.any(size<=0):raise hou.NodeError('La taille du volume doit être positive.')
   matrix=hou.hmath.buildTransform({'translate':stage.evalParmTuple('center'),'rotate':stage.evalParmTuple('rotation')}).inverted()
   p=np.frombuffer(out.pointFloatAttribValuesAsString('P'),dtype=np.float32).reshape(-1,3)
   m=np.array(matrix.asTuple()).reshape(4,4);local=p@m[:3,:3]+m[3,:3]
   chosen=np.flatnonzero(np.all(np.abs(local)<=size*.5+stage.evalParm('margin'),axis=1))
   points=out.points();group.add([points[int(i)] for i in chosen])
  if stage.parm('protect') and stage.evalParm('protect').strip():group.remove(out.globPoints(stage.evalParm('protect')))
 elif role=='remove':
  group=out.findPointGroup('spirula_remove')
  if group and stage.evalParm('enabled'):out.deletePoints(group.points())
 elif role=='repair':
  if stage.evalParm('enabled') and len(stage.inputs())>1 and stage.inputs()[1] is not None:
   if stage.userData('repair_estimator'):
    import spirula_repair
    estimator=stage.parent().node(stage.userData('repair_estimator'))
    if estimator is None or stage.userData('repair_approved')!=spirula_repair.fingerprint(estimator):raise hou.NodeError('Fond périmé : recalculer et valider 02C avant de continuer.')
   patch=stage.inputs()[1].geometry()
   if not patch.findPointAttrib('GS_Alpha'):raise hou.NodeError('La réparation doit être convertie en splats avec REPARATION_VERS_SPLAT.')
   if stage.evalParm('enabled'):out.merge(patch)


def downstream(stage):
 return next((n for n in stage.outputs() if n.type().name()=='spirula::replace_remove::1.0'),None)


def show(stage,preview=False):
 import hou
 stage.cook(force=True);geo=stage.geometry();group=geo.findPointGroup('spirula_remove');count=len(group.points()) if group else 0
 if preview:
  name='APERCU_SELECTION_'+stage.name();node=stage.parent().node(name)
  if node is None:
   node=stage.parent().createNode('python',name);node.setInput(0,stage);node.setPosition(stage.position()+hou.Vector2(-3,0))
   node.parm('python').set("import hou\nn=hou.pwd();g=n.geometry();g.clear();g.merge(n.inputs()[0].geometry());s=g.findPointGroup('spirula_remove');keep=set(p.number() for p in s.points()) if s else set();g.deletePoints([p for p in g.points() if p.number() not in keep])")
  node.setDisplayFlag(True)
 else:
  node=downstream(stage)
  if node is None:raise ValueError('Brancher 02B en sortie de 02A.')
  node.parm('enabled').set(1);node.cook(force=True);node.setDisplayFlag(True);node.setRenderFlag(True)
 text='%s points sélectionnés / %s · %s'%(count,len(geo.points()),'aperçu isolé' if preview else 'sortie nettoyée affichée')
 if stage.parm('status'):stage.parm('status').set(text)
 stage.setComment(text);stage.setGenericFlag(hou.nodeFlag.DisplayComment,True)
 return count


def select(stage,protect=False):
 import hou
 viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
 if viewer is None:raise ValueError('Ouvrir un viewport Houdini.')
 source=stage.inputs()[0] if stage.inputs() else None
 if source is None:raise ValueError('Brancher le scan sur 02A.')
 viewer.setPwd(stage.parent());source.setDisplayFlag(True);stage.setCurrent(True,clear_all_selected=True)
 viewer.setPickingCurrentNode(False);viewer.setSelectionMode(hou.selectionMode.Geometry);viewer.setPickGeometryType(hou.geometryType.Points);viewer.setCurrentState('select')
 name='protect' if protect else 'points';pattern=stage.evalParm(name).strip()
 selection=hou.Selection(source.geometry(),hou.geometryType.Points,pattern) if pattern else hou.Selection(hou.geometryType.Points)
 viewer.setCurrentGeometrySelection(hou.geometryType.Points,(source,),(selection,))
 stage.setUserData('spirula_selection_target',name)
 stage.parm('status').set('Sélectionner dans le viewport, puis cliquer 2 · Appliquer la sélection. Échap quitte le mode de sélection.')
 return source


def commit_selection(stage):
 import hou
 viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
 result=viewer.currentGeometrySelection() if viewer else None
 source=stage.inputs()[0]
 if result is None or not result.nodes():raise ValueError('Aucune sélection du viewport. Cliquer 1 · Sélectionner puis choisir les points.')
 values=result.selectionStrings(empty_string_selects_all=False)
 selected={n.path():v for n,v in zip(result.nodes(),values)}
 if source.path() not in selected:raise ValueError('Sélectionner le scan affiché en amont de 02A.')
 pattern=selected[source.path()];name=stage.userData('spirula_selection_target') or 'points'
 if not pattern.strip():raise ValueError('Sélection vide : aucun point modifié.')
 stage.parm(name).set(pattern)
 if name=='points':stage.parm('mode').set(0)
 stage.setCurrent(True,clear_all_selected=True);count=show(stage);viewer.enterViewState();return count


def dispatch(stage,command):
 import hou
 try:
  if command=='select':return select(stage)
  if command=='protect':return select(stage,True)
  if command=='commit':return commit_selection(stage)
  if command=='preview':return show(stage,True)
  if command=='apply':return show(stage)
  if command=='clear':stage.parm('points').set('');stage.parm('mode').set(0);return show(stage)
  if command=='build':return build_patch(stage)
 except Exception as exc:
  if stage.parm('status'):stage.parm('status').set(str(exc))
  if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
  else:raise


def install(root,scan=None):
 import hou,spirula_chain
 data=spirula_chain.config(root);scan=scan or hou.node(data['scan'])
 if root.userData('spirula_replacement'):
  existing=root.node(root.userData('spirula_replacement').split('/')[-1])
  if existing:
   cut=downstream(existing);repair=next((n for n in cut.outputs() if n.type().name()=='spirula::replace_repair::1.0'),None) if cut else None
   manual=root.node('SURFACE_FOND_A_MODELER');patch=next((n for n in root.children() if n.type().name()=='spirula::object_splat::1.0' and n.name().startswith(('REPARATION_VERS_SPLAT','02D_FOND_VERS_SPLAT'))),None)
   if cut and repair and manual and patch:
    import spirula_repair
    spirula_repair.attach(root,existing,cut,repair,manual,patch)
    existing.setCurrent(True,clear_all_selected=True);return existing,cut,repair,manual,patch
   raise ValueError('La branche de remplacement est incomplète : rétablir ses connexions avant la mise à niveau.')

 # Clean existing colours are used for removal; highlighting belongs to a side preview only.
 sel=root.createNode('spirula::replace_selection::1.0','02A_SELECTION_FRIGO');sel.setInput(0,scan)
 cut=root.createNode('spirula::replace_remove::1.0','02B_RETRAIT_OBJET');cut.setInput(0,sel)
 repair=root.createNode('spirula::replace_repair::1.0','02C_REPARATION_FOND');repair.setInput(0,cut)
 mesh=root.createNode('grid','SURFACE_FOND_A_MODELER');mesh.parm('sizex').set(2);mesh.parm('sizey').set(2)
 mesh.setComment('Modéliser ici le mur / sol révélé, ajouter UV et matériaux. Ajuster à la zone cachée.');mesh.setGenericFlag(hou.nodeFlag.DisplayComment,True)
 patch=root.createNode('spirula::object_splat::1.0','REPARATION_VERS_SPLAT');patch.setInput(0,mesh)
 patch.parm('workspace').set(hou.node(data['studio']).evalParm('workspace')+'/reparation');patch.parm('budget').set(50000)
 repair.setInput(1,patch);patch.bypass(True)
 # Disconnected until deliberately converted and enabled: no demo patch in final scene.
 repair.setInput(1,None)
 for branch in data['branches']:
  light=hou.node(branch['light']);assembly=hou.node(branch['assemble'])
  if light.inputs()[0]==scan:light.setInput(0,repair)
  if assembly.inputs()[0]==scan:assembly.setInput(0,repair)
 for n,pos in [(sel,(-3,-2)),(cut,(-3,-4)),(repair,(-3,-6)),(mesh,(-8,-2)),(patch,(-8,-4))]:n.setPosition(hou.Vector2(*pos))
 root.setUserData('spirula_replacement',sel.path());repair.setDisplayFlag(True);sel.setCurrent(True,clear_all_selected=True)
 import spirula_repair
 spirula_repair.attach(root,sel,cut,repair,mesh,patch)
 return sel,cut,repair,mesh,patch


def build_patch(stage):
 import hou,spirula_object
 candidates=[n for n in stage.parent().children() if n.type().name()=='spirula::object_splat::1.0' and n.name().startswith(('REPARATION_VERS_SPLAT','02D_FOND_VERS_SPLAT'))]
 if len(candidates)!=1:raise ValueError('Brancher manuellement le convertisseur voulu en entrée 2 de 02C ; plusieurs réparations présentes.')
 patch=candidates[0];manual=stage.parent().node('SURFACE_FOND_A_MODELER')
 if manual:patch.setInput(0,manual)
 patch.bypass(False);spirula_object.build(patch)
 for key in ('repair_estimator','repair_approved'):
  if stage.userData(key):stage.destroyUserData(key)
 stage.setInput(1,patch);stage.parm('enabled').set(1);stage.setDisplayFlag(True)

