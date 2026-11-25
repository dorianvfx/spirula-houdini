"""Spirula startup: keep the Tab menu readable.

The guided tools (Spirula Pipeline, Scene Karma, Studio, Raffinement local, ...) build the
numbered stage nodes themselves. Created alone from the Tab menu, those stage nodes are
unusable (they need the rig their tool creates), so they are hidden from the Tab menu.
They remain fully functional inside the networks the tools generate.

Applied now AND after every scene load/new, because node libraries can finish loading
after this file runs.
"""
HIDDEN = (
    'arch_source', 'arch_cameras', 'arch_preview', 'arch_renders', 'arch_train', 'arch_result', 'arch_export',
    'chain_scan', 'chain_mesh', 'chain_light', 'chain_cameras', 'chain_render', 'chain_train',
    'chain_assemble', 'chain_export',
    'replace_selection', 'replace_remove', 'replace_repair', 'repair_planes',
    'refine_zone', 'refine_renders', 'refine_apply', 'refine_check',
    'studio', 'render_splat', 'object_splat', 'assemble_splats', 'cut_splats', 'insert_asset',
)


def _hide_internal_nodes(*unused):
    import os
    import hou
    root = os.environ.get('SPIRULA_ROOT')
    if root:
        otls = os.path.join(root, 'otls')
        if os.path.isdir(otls):
            for name in sorted(os.listdir(otls)):
                if name.lower().endswith('.hda'):
                    try:
                        hou.hda.installFile(os.path.join(otls, name))  # idempotent; makes sure types exist
                    except hou.Error:
                        pass
    category = hou.sopNodeTypeCategory()
    for name in HIDDEN:
        node_type = hou.nodeType(category, 'spirula::%s::1.0' % name)
        if node_type is not None:
            node_type.setHidden(True)


try:
    import hou
    _hide_internal_nodes()
    hou.hipFile.addEventCallback(
        lambda event: _hide_internal_nodes() if event in (hou.hipFileEventType.AfterLoad, hou.hipFileEventType.AfterClear) else None)
except Exception as _exc:  # never block Houdini's startup
    print('Spirula pythonrc :', _exc)
