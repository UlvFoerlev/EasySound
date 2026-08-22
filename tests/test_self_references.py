import ast

import pytest

from conftest import REPO_ROOT

# These modules cannot be imported outside StreamController, so their self.* use is checked statically
MODULES = [
    REPO_ROOT / "actions" / "play_sound" / "play_sound.py",
    REPO_ROOT / "actions" / "group_dialog.py",
    REPO_ROOT / "actions" / "spatial_dialog.py",
    REPO_ROOT / "actions" / "icon_combo.py",
    REPO_ROOT / "main.py",
]

# Names supplied by the framework base classes rather than by our own code
INHERITED = {
    # ActionCore / SoundActionBase / PluginBase
    "_get_property",
    "_set_property",
    "add_action_holder",
    "add_event_assigner",
    "generative_ui_objects",
    "get_plugin_id",
    "get_settings",
    "launch_backend",
    "locale_manager",
    "plugin_base",
    "register",
    "set_settings",
    "show_error",
    "wait_for_backend",
    # Gtk/Adw widget surface used by the dialog
    "add_css_class",
    "add_prefix",
    "add_suffix",
    "add_top_bar",
    "connect",
    "get_text",
    "present",
    "remove_css_class",
    "set_child",
    "set_content",
    "set_content_height",
    "set_content_width",
    "set_sensitive",
    "set_text",
    "set_title",
}


def self_names(tree: ast.Module) -> tuple[set[str], set[str], list[tuple[str, int]]]:
    defined: set[str] = set()
    assigned: set[str] = set()
    used: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
            continue

        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        if node.value.id != "self":
            continue

        if isinstance(node.ctx, ast.Store):
            assigned.add(node.attr)
        else:
            used.append((node.attr, node.lineno))

    return defined, assigned, used


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_every_self_reference_resolves(path):
    """Catches a self.method() that no longer exists — an edit can silently delete one."""
    defined, assigned, used = self_names(ast.parse(path.read_text()))
    known = defined | assigned | INHERITED

    unresolved = sorted({(name, line) for name, line in used if name not in known})
    assert not unresolved, f"{path.name} references undefined attributes: {unresolved}"
