import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def manifest() -> dict:
    return json.loads((REPO_ROOT / "manifest.json").read_text())


@pytest.fixture(scope="session")
def locales() -> dict:
    return json.loads((REPO_ROOT / "locales" / "en_US.json").read_text())


@pytest.fixture(scope="session")
def main_ast() -> ast.Module:
    # main.py cannot be imported outside StreamController, so its wiring is asserted against the AST
    return ast.parse((REPO_ROOT / "main.py").read_text())


def source_files() -> list[Path]:
    # Filters on repo-relative parts so a dotted directory above the repo cannot widen the walk
    def is_source(path: Path) -> bool:
        parts = path.relative_to(REPO_ROOT).parts
        if path.name == "conftest.py":
            return False
        return not any(part.startswith(".") for part in parts) and "tests" not in parts

    return sorted(p for p in REPO_ROOT.rglob("*.py") if is_source(p))
