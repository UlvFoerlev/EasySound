import ast

import pytest

LEGACY_ID = "dev_core477_EasySound::PlaySound"


def _action_holder_calls(main_ast: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ActionHolder"
    ]


def _kwargs(call: ast.Call) -> dict:
    return {kw.arg: kw.value for kw in call.keywords}


@pytest.fixture(scope="module")
def holder_calls(main_ast):
    calls = _action_holder_calls(main_ast)
    assert calls, "no ActionHolder(...) calls found in main.py"
    return calls


def test_legacy_action_id_constant_is_unchanged(main_ast):
    # The holder is gone, but migration still matches this id exactly to rewrite an imported old page
    values = [
        node.value.value
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and any(
            isinstance(t, ast.Name) and t.id == "LEGACY_PLAY_SOUND_ACTION_ID"
            for t in node.targets
        )
    ]
    assert values == [LEGACY_ID]


def test_the_actions_use_derived_ids_only(holder_calls):
    """No holder may pin an explicit action_id: the legacy one is deleted, and migration replaces it."""
    suffixes, pinned = [], []

    for call in holder_calls:
        kwargs = _kwargs(call)
        if "action_id_suffix" in kwargs:
            suffixes.append(kwargs["action_id_suffix"].value)
        if "action_id" in kwargs:
            pinned.append(ast.dump(kwargs["action_id"]))

    assert suffixes == ["PlaySound", "StopAll"]
    assert pinned == []


def test_the_actions_are_grouped_in_a_fixed_order(main_ast):
    """The chooser iterates loose holders as a set, so only a group keeps Stop All below Play Sound."""
    groups = [
        node
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ActionHolderGroup"
    ]
    assert len(groups) == 1

    holders = {kw.arg: kw.value for kw in groups[0].keywords}["action_holders"]
    assert isinstance(holders, ast.List)
    assert [element.attr for element in holders.elts] == [
        "action_play_sound",
        "action_stop_all",
    ]


def test_holders_use_action_core_not_the_deprecated_action_base(holder_calls):
    for call in holder_calls:
        kwargs = _kwargs(call)
        assert "action_core" in kwargs
        assert "action_base" not in kwargs


def test_key_input_is_declared_supported(holder_calls):
    for call in holder_calls:
        support = _kwargs(call)["action_support"]
        # Omitting action_support defaults every input to UNTESTED, which warns users on a working action
        assert isinstance(support, ast.Name)
        assert support.id == "action_support"


def test_every_holder_is_actually_registered(main_ast):
    """A holder that is constructed but never added is invisible: the action index only reads
    action_holders, so its actions resolve to nothing and every saved button breaks."""
    constructed = [
        target.attr
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "ActionHolder"
        for target in node.targets
        if isinstance(target, ast.Attribute)
    ]

    registered = [
        node.args[0].attr
        for node in ast.walk(main_ast)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_action_holder"
        and node.args
        and isinstance(node.args[0], ast.Attribute)
    ]

    assert constructed, "no ActionHolder assignments found"
    assert sorted(constructed) == sorted(registered), (
        f"constructed {sorted(constructed)} but registered {sorted(registered)}"
    )
