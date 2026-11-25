"""Houdini startup script; launch after the documented waitforui argument."""
import hou
import spirula_houdini

selected = [n for n in hou.selectedNodes() if n.type().name() == 'spirula::studio::1.0']
node = selected[0] if selected else spirula_houdini.create()
spirula_houdini.studio(node)
