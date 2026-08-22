from actions.legacy_action import action_id_in_pages

ACTION_ID = "dev_core477_EasySound::PlaySound"


def test_finds_the_id_in_a_page(tmp_path):
    page = tmp_path / "page.json"
    page.write_text('{"keys": {"0x0": {"actions": [{"id": "%s"}]}}}' % ACTION_ID)

    assert action_id_in_pages(ACTION_ID, [str(page)]) is True


def test_ignores_pages_without_the_id(tmp_path):
    page = tmp_path / "page.json"
    page.write_text('{"keys": {"0x0": {"actions": [{"id": "uf_easy_sound::PlaySound"}]}}}')

    assert action_id_in_pages(ACTION_ID, [str(page)]) is False


def test_no_pages_means_not_in_use():
    assert action_id_in_pages(ACTION_ID, []) is False


def test_stops_at_the_first_hit(tmp_path):
    hit = tmp_path / "hit.json"
    hit.write_text(ACTION_ID)

    assert action_id_in_pages(ACTION_ID, [str(hit), str(tmp_path / "missing.json")]) is True


def test_unreadable_page_fails_open(tmp_path):
    # A hidden holder breaks a user's page, so an unreadable page must register the holder anyway
    assert action_id_in_pages(ACTION_ID, [str(tmp_path / "missing.json")]) is True


def test_directory_instead_of_file_fails_open(tmp_path):
    assert action_id_in_pages(ACTION_ID, [str(tmp_path)]) is True
