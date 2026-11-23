# ABOUTME: Tests reading the gallery index that names the pictures of each thread.
# ABOUTME: Uses small index files of the tests' own; a missing or unreadable index means no pictures.

import json
import re

import pytest

from src.pictures import PictureIndex, count_pictures, first_pictures, get_pictures

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


def test_first_pictures_cuts_a_thread_and_leaves_out_the_rest():
    lstThreads, _ = get_pictures(docs("THREADbbbbb", "THREADaaaaa", "THREADccccc"), [], PICTURES, THUMBS_URL)

    lstFirst = first_pictures(lstThreads, 2)

    assert thread_ids(lstFirst) == ["THREADbbbbb", "THREADaaaaa"]
    assert [len(dctThread["pictures"]) for dctThread in lstFirst] == [1, 1]
    assert count_pictures(lstThreads) == 4
    assert count_pictures(lstFirst) == 2


# ---- the results page and the status response
@pytest.fixture
def pictures(site_app, tmp_path, monkeypatch):
    """The app with the given gallery index."""
    def use_index(dctIndex):
        pathIndex = tmp_path / "gallery.idx"
        pathIndex.write_text(json.dumps(dctIndex))
        monkeypatch.setattr(site_app, "Pictures", PictureIndex(str(pathIndex)))
    assert site_app.cfg.get("PICTURES", "THUMBS_URL") == THUMBS_URL
    return use_index


def write_answer(pathJobs, lstProvided, lstRelated=None, strType="new"):
    dctResult = {"answer": "Four.", "provided_docs": lstProvided}
    if lstRelated is not None:
        dctResult["related_docs"] = lstRelated
    dctJob = {"process_id": "done", "status": "complete", "created": 1.0, "elapsed": 2.5,
              "type": strType, "query": "how many seats", "result": dctResult}
    (pathJobs / "done.json").write_text(json.dumps(dctJob))


def results_page(client, strPath="/cozyrag/done/processid"):
    response = client.get(strPath)
    assert response.status_code == 200
    return response.get_data(as_text=True)


BOTH_PAGES = pytest.mark.parametrize("strPath", ["/cozyrag/done/processid", "/cozyrag/done/pictures"])


def thumbnails(strPage):
    return re.findall(r'<img [^>]*src="([^"]*)"', strPage)


MANY = {f"THREAD{n:05d}": thread(f"THREAD{n:05d}", [f"p{n}_{m}.jpg" for m in range(5)]) for n in range(4)}


def test_a_thread_with_pictures_is_shown_under_the_answer(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), [])

    strPage = results_page(client)

    assert "Pictures from the threads this answer drew on" in strPage
    assert thumbnails(strPage) == ["/cgimages/pictures/thumbs/a1.jpg_thumb.jpg",
                                   "/cgimages/pictures/thumbs/a2.jpg_thumb.jpg"]
    assert f'href="{GROUP}a1.jpg?part=0.1"' in strPage
    assert re.search(r'<a href="https://groups.google.com/g/cozy_builders/c/THREADaaaaa"[^>]*>'
                     r'Subject of THREADaaaaa</a>', strPage)
    assert "Jan 1, 2015" in strPage
    assert 'href="/cozyrag/done/pictures">All pictures for this answer (2)</a>' in strPage


def test_the_pictures_are_between_the_provided_docs_and_the_other_related_docs(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), docs("news_78"))

    strPage = results_page(client)

    assert strPage.index("Use at your own risk") < strPage.index('name="satisfaction"') \
        < strPage.index('action="/cozyrag/followup"') < strPage.index("Provided Docs") \
        < strPage.index("<img ") < strPage.index("All pictures for this answer") \
        < strPage.index("Other Related Docs") < strPage.index("Statistics:")


def test_without_other_related_docs_the_pictures_are_above_the_statistics(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), strType="revise")

    strPage = results_page(client)

    assert strPage.index("Provided Docs") < strPage.index("<img ") < strPage.index("Statistics:")


def test_a_picture_opens_in_a_new_tab(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), [])

    assert re.search(rf'<a href="{re.escape(GROUP)}a1.jpg\?part=0.1" target="_blank"', results_page(client))


def test_no_thread_with_pictures_no_section(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("news_78", "THREADnopic"), docs("cp__no21"))

    strPage = results_page(client)

    assert "Pictures from" not in strPage
    assert "All pictures" not in strPage
    assert "<img" not in strPage


def test_a_newsletter_among_the_provided_documents_changes_nothing(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), [])
    strWithout = results_page(client)
    write_answer(jobs_dir, docs("news_78", "THREADaaaaa"), [])

    strWith = results_page(client)

    assert thumbnails(strWith) == thumbnails(strWithout)
    assert "All pictures for this answer (2)" in strWith


def test_over_12_pictures_shows_12_and_the_full_count(client, jobs_dir, pictures):
    pictures(MANY)
    write_answer(jobs_dir, docs("THREAD00000", "THREAD00001", "THREAD00002"), docs("THREAD00003"))

    strPage = results_page(client)

    assert len(thumbnails(strPage)) == 12
    assert thumbnails(strPage)[-1] == "/cgimages/pictures/thumbs/p2_1.jpg_thumb.jpg"
    assert "All pictures for this answer (20)" in strPage


def test_link_without_thumbnails_when_only_other_threads_have_pictures(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("news_78"), docs("THREADbbbbb"))

    strPage = results_page(client)

    assert "<img" not in strPage
    assert "Pictures from the threads this answer drew on" not in strPage
    assert "All pictures for this answer (1)" in strPage


def test_a_revise_shows_the_pictures_of_its_provided_documents(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADbbbbb", "THREADaaaaa"), strType="revise")

    strPage = results_page(client)

    assert len(thumbnails(strPage)) == 3
    assert "All pictures for this answer (3)" in strPage


@BOTH_PAGES
def test_names_are_percent_encoded_and_a_subject_is_text(client, jobs_dir, pictures, strPath):
    dctThread = thread("THREADddddd", ["d my #1 100%.png"])
    dctThread["metadata"]["subject"] = "Canopy <script>alert(1)</script>"
    pictures({"THREADddddd": dctThread})
    write_answer(jobs_dir, docs("THREADddddd"), [])

    strPage = results_page(client, strPath)

    assert thumbnails(strPage) == ["/cgimages/pictures/thumbs/d%20my%20%231%20100%25.png_thumb.jpg"]
    assert "<script>alert(1)" not in strPage
    assert "Canopy &lt;script&gt;alert(1)&lt;/script&gt;" in strPage


@BOTH_PAGES
def test_a_picture_whose_link_is_not_google_groups_has_no_link(client, jobs_dir, pictures, strPath):
    pictures({"THREADddddd": thread("THREADddddd", ["d1.jpg"], strUrl="https://example.com/d1.jpg")})
    write_answer(jobs_dir, docs("THREADddddd"), [])

    strPage = results_page(client, strPath)

    assert thumbnails(strPage) == ["/cgimages/pictures/thumbs/d1.jpg_thumb.jpg"]
    assert "example.com" not in strPage


@BOTH_PAGES
def test_the_author_is_not_on_the_page(client, jobs_dir, pictures, strPath):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), docs("THREADbbbbb"))

    assert "zqauthor" not in results_page(client, strPath)


def test_the_status_response_of_a_finished_job_carries_the_thumbnails(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), [])

    strHtml = client.get("/cozyrag/done/status").get_json()["result_html"]

    assert thumbnails(strHtml) == ["/cgimages/pictures/thumbs/a1.jpg_thumb.jpg",
                                   "/cgimages/pictures/thumbs/a2.jpg_thumb.jpg"]


@pytest.mark.parametrize("strSetting, strLog", [
    ("", "No pictures: the gallery index is not set (INDEX in [PICTURES])"),
    ("/nonexistent/gallery.idx", "No pictures: cannot read the gallery index /nonexistent/gallery.idx: FileNotFoundError"),
])
@BOTH_PAGES
def test_without_an_index_the_page_is_served_without_pictures(client, jobs_dir, site_app, monkeypatch, capsys,
                                                             strSetting, strLog, strPath):
    monkeypatch.setattr(site_app, "Pictures", PictureIndex(strSetting))
    write_answer(jobs_dir, docs("THREADaaaaa"), [])

    strPage = results_page(client, strPath)
    results_page(client, strPath)

    assert "how many seats" in strPage
    assert "<img" not in strPage
    lstLines = capsys.readouterr().out.splitlines()
    assert len(lstLines) == 1
    assert lstLines[0].startswith(strLog)



# ---- the pictures page
def pictures_page(client):
    return results_page(client, "/cozyrag/done/pictures")


def test_pictures_page_has_the_question_and_a_link_back_to_the_answer(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADaaaaa"), [])

    strPage = pictures_page(client)

    assert "how many seats" in strPage
    assert 'href="/cozyrag/done/processid"' in strPage


def test_pictures_page_shows_provided_threads_then_the_others(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADbbbbb"), docs("THREADccccc", "THREADbbbbb", "THREADaaaaa"))

    strPage = pictures_page(client)

    assert thumbnails(strPage) == ["/cgimages/pictures/thumbs/b1.jpg_thumb.jpg",
                                   "/cgimages/pictures/thumbs/c1.jpg_thumb.jpg",
                                   "/cgimages/pictures/thumbs/a1.jpg_thumb.jpg",
                                   "/cgimages/pictures/thumbs/a2.jpg_thumb.jpg"]
    assert strPage.index("Pictures from the threads this answer drew on") < strPage.index("b1.jpg") \
        < strPage.index("Pictures from other threads found") < strPage.index("c1.jpg")


def test_pictures_page_shows_every_picture(client, jobs_dir, pictures):
    pictures(MANY)
    write_answer(jobs_dir, docs("THREAD00000", "THREAD00001", "THREAD00002"), docs("THREAD00003"))

    assert len(thumbnails(pictures_page(client))) == 20


def test_pictures_page_of_a_revise_has_one_section(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("THREADbbbbb", "THREADaaaaa"), strType="revise")

    strPage = pictures_page(client)

    assert len(thumbnails(strPage)) == 3
    assert "Pictures from the threads this answer drew on" in strPage
    assert "Pictures from other threads found" not in strPage


def test_pictures_page_without_pictures_says_so(client, jobs_dir, pictures):
    pictures(PICTURES)
    write_answer(jobs_dir, docs("news_78"), [])

    strPage = pictures_page(client)

    assert "<img" not in strPage
    assert "No pictures were found for this answer." in strPage


def test_pictures_page_thumbnails_load_when_they_come_into_view(client, jobs_dir, pictures):
    pictures(MANY)
    write_answer(jobs_dir, docs("THREAD00000"), [])

    assert re.findall(r"<img [^>]*>", pictures_page(client))[0].count('loading="lazy"') == 1
