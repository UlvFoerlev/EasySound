import ast

import pytest

from conftest import source_files


@pytest.mark.parametrize("path", source_files(), ids=lambda p: p.name)
def test_source_file_parses(path):
    # main.py, backend.py, chooser.py and play_sound.py cannot be imported here, so parsing is the only check
    ast.parse(path.read_text())
