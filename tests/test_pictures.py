# ABOUTME: Tests reading the gallery index that names the pictures of each thread.
# ABOUTME: Uses small index files of the tests' own; a missing or unreadable index means no pictures.

import json

from src.pictures import PictureIndex

INDEX = {"THREADaaaaa": {"metadata": {"message_id": "THREADaaaaa", "subject": "Canopy",
                                      "date": "Jan 1, 2015"},
                         "images": [{"url": "https://groups.google.com/g/cozy_builders/c/x/m/y",
                                     "thumbnail_filename": "a_photo_thumb.jpg"}]}}


def test_reads_the_index(tmp_path):
    pathIndex = tmp_path / "gallery.idx"
    pathIndex.write_text(json.dumps(INDEX))

    assert PictureIndex(str(pathIndex)).threads() == INDEX


def test_read_once_at_first_use(tmp_path, capsys):
    pathIndex = tmp_path / "gallery.idx"
    pathIndex.write_text(json.dumps(INDEX))
    index = PictureIndex(str(pathIndex))

    index.threads()
    pathIndex.unlink()

    assert index.threads() == INDEX
    assert capsys.readouterr().out == ""


def test_not_read_before_first_use(tmp_path):
    pathIndex = tmp_path / "gallery.idx"
    index = PictureIndex(str(pathIndex))
    pathIndex.write_text(json.dumps(INDEX))

    assert index.threads() == INDEX


def test_no_setting_gives_no_pictures_and_one_log_line(capsys):
    index = PictureIndex("")

    assert index.threads() == {}
    assert index.threads() == {}
    assert capsys.readouterr().out.splitlines() == [
        "No pictures: the gallery index is not set (INDEX in [PICTURES])"]


def test_missing_file_gives_no_pictures_and_one_log_line(tmp_path, capsys):
    strPath = str(tmp_path / "gallery.idx")
    index = PictureIndex(strPath)

    assert index.threads() == {}
    assert index.threads() == {}
    lstLines = capsys.readouterr().out.splitlines()
    assert len(lstLines) == 1
    assert lstLines[0].startswith(f"No pictures: cannot read the gallery index {strPath}: FileNotFoundError")


def test_file_that_is_not_json_gives_no_pictures_and_one_log_line(tmp_path, capsys):
    pathIndex = tmp_path / "gallery.idx"
    pathIndex.write_text("{not json")

    assert PictureIndex(str(pathIndex)).threads() == {}
    lstLines = capsys.readouterr().out.splitlines()
    assert len(lstLines) == 1
    assert lstLines[0].startswith(f"No pictures: cannot read the gallery index {pathIndex}: JSONDecodeError")


def test_file_that_is_not_an_object_gives_no_pictures(tmp_path, capsys):
    pathIndex = tmp_path / "gallery.idx"
    pathIndex.write_text("[]")

    assert PictureIndex(str(pathIndex)).threads() == {}
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_the_site_reads_its_setting(site_app):
    assert site_app.Pictures.strPath == site_app.cfg.get("PICTURES", "INDEX", fallback="")
