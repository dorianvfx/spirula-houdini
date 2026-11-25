"""Shelf entry points with Houdini selection and undo handling.

Every action runs through `_guard`: an error is shown in a dialog AND appended to
spirula_errors.log (temp folder) instead of vanishing silently, which is what
happened when the work was deferred with hou.ui.postEventCallback.
"""
import os
import tempfile
import time
import traceback


def log_path():
    return os.path.join(tempfile.gettempdir(), 'spirula_errors.log')


def report(action, exc):
    import hou
    text = traceback.format_exc()
    try:
        with open(log_path(), 'a', encoding='utf8') as f:
            f.write('[%s] %s\n%s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), action, text))
    except OSError:
        pass
    if hou.isUIAvailable():
        hou.ui.displayMessage('Spirula · %s\n\n%s\n\nDétail : %s' % (action, exc, log_path()),
                              severity=hou.severityType.Error)
    else:
        raise exc


def _guard(action, function):
    def wrapped():
        try:
            return function()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never swallowed
            report(action, exc)
    return wrapped


def _deferred(action, function):
    """Run after the current UI event (needed by the pipeline/architecture builders)."""
    import hou
    if hou.isUIAvailable():
        hou.ui.postEventCallback(_guard(action, function))
    else:
        function()


def run(action):
    import hou
    try:
        with hou.undos.group('Spirula : ' + action):
            if action == 'architecture':
                import spirula_arch
                return _deferred(action, lambda: spirula_arch.create())
            if action == 'pipeline':
                import spirula_chain
                return _deferred(action, lambda: spirula_chain.create())
            if action == 'insert':
                import spirula_insert
                return spirula_insert.create_simple()
            if action == 'surface':
                import spirula_object
                return spirula_object.create()
            if action == 'render':
                import spirula_render
                return spirula_render.create()
            import spirula_scene
            return spirula_scene.assemble() if action == 'assemble' else spirula_scene.cut()
    except Exception as exc:  # noqa: BLE001
        report(action, exc)
