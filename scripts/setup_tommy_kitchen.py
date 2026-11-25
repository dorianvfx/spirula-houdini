"""Run with Houdini's Python Source Editor while Gaussian.hip is open."""
import hou
import spirula_insert
mesh=hou.node('/obj/testgeometry_tommy1/testgeometry_tommy1')
scan=hou.node('/obj/geo1/transform1')
if mesh is None or scan is None:
    raise ValueError('Ouvrir votre Gaussian.hip avant ce script, ou utiliser la sélection mesh + scan avec la shelf Spirula Insert Lit Object.')
node=spirula_insert.create_simple(mesh,scan)
print('Outil prêt : '+node.path())
