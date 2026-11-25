"""World-space assembly, non-destructive box cuts and portable Gaussian exports."""
from pathlib import Path
import json
import os
import time


def source_sop(node):
    import hou
    if isinstance(node,hou.ObjNode):node=node.displayNode()
    if not isinstance(node,hou.SopNode):raise ValueError('Sélectionner une géométrie ou un SOP.')
    return node


def export(node):
    import hou
    from spirula_ply import write_geometry
    target=Path(node.evalParm('exportfile'));target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name('.partial_'+target.name)
    from spirula_transform import transformed
    node.node('COMPOSE_WORLD').cook(force=True)
    g=transformed(node.geometry(),node.creator().worldTransform())
    if not g.findPointAttrib('GS_Alpha'):raise ValueError('La composition ne contient pas de GSplats natifs. Convertir les meshes avant la fusion.')
    born=time.monotonic()
    try:
        with hou.InterruptableOperation('Exporter la composition de splats',open_interrupt_dialog=True):
            write_geometry(g,temp,linearized=True);os.replace(temp,target)
    finally:
        if temp.exists():temp.unlink()
    count=g.intrinsicValue('pointcount');node.parm('status').set('%s gaussiennes exportées : %s'%(count,target))
    report={'gaussians':count,'file':str(target),'world_space':True,'seconds':time.monotonic()-born,'sources':node.evalParm('sources').split()}
    target.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


def cook(node):
    from spirula_transform import transformed
    import hou
    out=node.geometry();out.clear()
    paths=node.parent().evalParm('sources').split()
    if len(paths)>16:raise hou.NodeError('Au maximum 16 sources par composition.')
    target_inverse=node.creator().worldTransform().inverted()
    for path in paths:
        source=hou.node(path)
        if source is None:raise hou.NodeError('Source introuvable : '+path)
        source=source_sop(source)
        if not source.geometry().findPointAttrib('GS_Alpha'):raise hou.NodeError('Source non convertie en splat : '+source.path())
        world=source.creator().worldTransform()*target_inverse
        out.merge(transformed(source.geometry(),world))


def callback(node):
    import hou
    try:return export(node)
    except Exception as exc:
        node.parm('status').set(str(exc))
        if hou.isUIAvailable():hou.ui.displayMessage(str(exc),severity=hou.severityType.Error)
        else:raise


def assemble(sources=None):
    import hou
    sources=[source_sop(n) for n in (sources if sources is not None else hou.selectedNodes())]
    if not sources:raise ValueError('Sélectionner les objets de splats à fusionner.')
    if len(sources)>16:raise ValueError('Assembler au maximum 16 sources par nœud ; les compositions peuvent être imbriquées.')
    for source in sources:
        if not source.geometry().findPointAttrib('GS_Alpha'):
            raise ValueError(source.path()+' : convertir cette source avec Bake GSplats ou Objet → Splat avant la fusion.')
    obj=hou.node('/obj').createNode('geo','SPIRULA_COMPOSITION')
    for c in obj.children():c.destroy()
    n=obj.createNode('spirula::assemble_splats::1.0','ASSEMBLE_SPLATS');n.parm('sources').set('\n'.join(s.path() for s in sources))
    n.setDisplayFlag(True);n.setRenderFlag(True);n.setCurrent(True,clear_all_selected=True)
    for source in sources:
        if source.creator()!=obj:source.creator().setDisplayFlag(False)
    return n


def cut(source=None):
    import hou
    source=source_sop(source or (hou.selectedNodes()[0] if hou.selectedNodes() else None))
    if not source.geometry().findPointAttrib('GS_Alpha'):
        raise ValueError('Choisir la sortie de Bake GSplats ou un SOP de splats natifs.')
    n=source.parent().createNode('spirula::cut_splats::1.0','CUT_EXISTING_OBJECT');n.setInput(0,source)
    box=hou.node('/obj').createNode('geo','SPIRULA_REMOVE_BOX');box.setUserData('spirula_role','cut_guide')
    for child in box.children():child.destroy()
    cube=box.createNode('box','VOLUME_A_RETIRER');wire=box.createNode('attribwrangle','GUIDE');wire.setInput(0,cube);wire.parm('snippet').set('setdetailattrib(0,"gl_wireframe",1,"set");setdetailattrib(0,"gl_lit",0,"set");@Cd=set(1,.15,.05);');wire.setDisplayFlag(True)
    if box.parm('vm_renderable'):box.parm('vm_renderable').set(0)
    if box.parm('vm_rendervisibility'):box.parm('vm_rendervisibility').set('')
    box.createNode('null','NO_RENDER').setRenderFlag(True)
    from spirula_transform import bounding_box
    bounds=bounding_box(source.geometry(),source.creator().worldTransform())
    box.parmTuple('t').set(bounds.center());box.parmTuple('s').set(tuple(max(.1,x*.15) for x in bounds.sizevec()))
    n.parm('box_object').set(box.path());n.setPosition(source.position()+hou.Vector2(0,-2));n.setDisplayFlag(True);n.setRenderFlag(True);n.setCurrent(True,clear_all_selected=True)
    return n,box
