import ast

import pytest

from conftest import REPO_ROOT, calls_named

SOURCE = REPO_ROOT / "actions" / "play_sound" / "play_sound.py"


@pytest.fixture(scope="module")
def action() -> ast.ClassDef:
    tree = ast.parse(SOURCE.read_text())
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PlaySoundAction"
    ]
    assert classes, "PlaySoundAction not found"

    return classes[0]


def method(action: ast.ClassDef, name: str) -> ast.FunctionDef:
    found = [
        node
        for node in action.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert found, f"PlaySoundAction.{name} is missing"

    return found[0]


def calls_to(node: ast.AST) -> set[str]:
    return {
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }


@pytest.mark.parametrize(
    "hook", ["on_remove", "on_removed_from_cache", "on_page_deleted", "on_page_changed"]
)
def test_every_removal_hook_stops_the_sounds(action, hook):
    """A sound that outlives its action can never be stopped again, so each exit path must stop it."""
    assert "stop_sounds" in calls_to(method(action, hook))


def test_deletion_is_told_apart_from_cache_eviction(action):
    """Stopping on plain eviction would cut off a loop set to keep playing on other pages."""
    assert "input_still_saved" in calls_to(method(action, "on_removed_from_cache"))


def test_page_deletion_is_subscribed_to(action):
    signals = {
        node.attr
        for node in ast.walk(method(action, "__init__"))
        if isinstance(node, ast.Attribute) and node.attr in {"ChangePage", "PageDelete"}
    }
    assert signals == {"ChangePage", "PageDelete"}


def test_every_playback_is_tagged_in_one_place(action):
    """The tag is what survives action recreation; a call site setting its own could miss one."""
    defaults = [
        call
        for call in calls_named(method(action, "_play"), "setdefault")
        if call.args and getattr(call.args[0], "value", None) == "tag"
    ]
    assert len(defaults) == 1

    tagged_by_hand = [
        keyword.arg
        for call in calls_named(action, "_play")
        for keyword in call.keywords
        if keyword.arg == "tag"
    ]
    assert tagged_by_hand == []


def test_no_handle_based_stop_survives(action):
    """One mechanism only: a handle is lost when the action is recreated, the tag is not."""
    source = SOURCE.read_text()
    assert "looping_handle" not in source
    assert "stop_looping" not in source
