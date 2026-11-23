# ABOUTME: Tests reading the gallery index that names the pictures of each thread.
# ABOUTME: Uses small index files of the tests' own; a missing or unreadable index means no pictures.

import json

from src.pictures import PictureIndex, get_pictures

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


GROUP = "https://groups.google.com/group/cozy_builders/attach/"
THUMBS_URL = "/cgimages/pictures/thumbs"


def thread(strId, lstNames, strUrl=None):
    return {"metadata": {"message_id": strId, "subject": f"Subject of {strId}",
                         "author": "zqauthor...@example.com", "date": "Jan 1, 2015"},
            "images": [{"url": strUrl or f"{GROUP}{strName}?part=0.1", "filename": strName,
                        "local_filename": strName, "thumbnail_filename": f"{strName}_thumb.jpg"}
                       for strName in lstNames]}


PICTURES = {"THREADaaaaa": thread("THREADaaaaa", ["a1.jpg", "a2.jpg"]),
            "THREADbbbbb": thread("THREADbbbbb", ["b1.jpg"]),
            "THREADccccc": thread("THREADccccc", ["c1.jpg"])}


def docs(*lstSources):
    return [{"id": f"{strSource}#{n}", "score": "0.80", "source": strSource}
            for n, strSource in enumerate(lstSources)]


def thread_ids(lstThreads):
    return [dctThread["url"].rsplit("/", 1)[1] for dctThread in lstThreads]


def test_threads_in_the_order_of_the_documents_each_once():
    lstProvided, lstRelated = get_pictures(docs("THREADbbbbb", "THREADaaaaa", "THREADbbbbb"), [],
                                           PICTURES, THUMBS_URL)

    assert thread_ids(lstProvided) == ["THREADbbbbb", "THREADaaaaa"]
    assert lstRelated == []


def test_thread_in_the_provided_and_the_related_documents_shown_with_the_provided():
    lstProvided, lstRelated = get_pictures(docs("THREADaaaaa"), docs("THREADccccc", "THREADaaaaa"),
                                           PICTURES, THUMBS_URL)

    assert thread_ids(lstProvided) == ["THREADaaaaa"]
    assert thread_ids(lstRelated) == ["THREADccccc"]


def test_document_of_a_newsletter_or_a_thread_without_pictures_changes_nothing():
    lstProvided, _ = get_pictures(docs("news_78", "THREADaaaaa", "cp__no21", "THREADnopic"), [],
                                  PICTURES, THUMBS_URL)

    assert thread_ids(lstProvided) == ["THREADaaaaa"]


def test_a_thread_has_its_subject_date_link_and_pictures():
    lstProvided, _ = get_pictures(docs("THREADaaaaa"), [], PICTURES, THUMBS_URL)

    assert lstProvided == [{
        "subject": "Subject of THREADaaaaa",
        "date": "Jan 1, 2015",
        "url": "https://groups.google.com/g/cozy_builders/c/THREADaaaaa",
        "pictures": [{"thumbnail_url": "/cgimages/pictures/thumbs/a1.jpg_thumb.jpg",
                      "url": f"{GROUP}a1.jpg?part=0.1"},
                     {"thumbnail_url": "/cgimages/pictures/thumbs/a2.jpg_thumb.jpg",
                      "url": f"{GROUP}a2.jpg?part=0.1"}]}]


def test_thumbnail_address_is_percent_encoded():
    dctIndex = {"THREADddddd": thread("THREADddddd", ["d my #1 100%\u202fshot?.png"])}

    lstProvided, _ = get_pictures(docs("THREADddddd"), [], dctIndex, THUMBS_URL)

    assert lstProvided[0]["pictures"][0]["thumbnail_url"] == \
        "/cgimages/pictures/thumbs/d%20my%20%231%20100%25%E2%80%AFshot%3F.png_thumb.jpg"


def test_link_that_does_not_go_to_google_groups_is_left_out():
    dctIndex = {"THREADddddd": thread("THREADddddd", ["d1.jpg"], strUrl="https://example.com/d1.jpg"),
                "THREADeeeee": thread("THREADeeeee", ["e1.jpg"], strUrl="javascript:alert(1)")}

    lstProvided, _ = get_pictures(docs("THREADddddd", "THREADeeeee"), [], dctIndex, THUMBS_URL)

    assert [dctThread["pictures"][0]["url"] for dctThread in lstProvided] == [None, None]


def test_the_author_is_not_given():
    lstProvided, lstRelated = get_pictures(docs("THREADaaaaa"), docs("THREADbbbbb"), PICTURES, THUMBS_URL)

    assert "zqauthor" not in json.dumps([lstProvided, lstRelated])


def test_no_index_gives_no_threads():
    assert get_pictures(docs("THREADaaaaa"), docs("THREADbbbbb"), {}, THUMBS_URL) == ([], [])
