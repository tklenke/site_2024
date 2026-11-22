# ABOUTME: Tests the page on which Tom rates the answers of the models without knowing the model.
# ABOUTME: Checks the hidden order, what the page shows and that each rating is saved.

import json
import random
import re
import subprocess

import pytest

from answer_models import write_json
from review_answers import create_app, get_key

QUESTIONS = [{"question_id": "Q01", "kind": "factual", "question": "how <many> seats"},
             {"question_id": "Q03", "kind": "broad", "question": "which tires"}]
MODELS = ["gpt-4o-mini", "gpt-6-luna", "gpt-6.1-terra"]


def save_answer(pathOutput, strId, strModel, dctRecord):
    write_json(str(pathOutput / "answers" / f"{strId}_{strModel}.json"),
               {"question_id": strId, "model": strModel} | dctRecord)


@pytest.fixture
def output(tmp_path):
    for dctQuestion in QUESTIONS:
        strId = dctQuestion["question_id"]
        write_json(str(tmp_path / "prompts" / f"{strId}.json"),
                   dctQuestion | {"ids": ["a", "b"], "prompt": f"documents for {strId}"})
        for strModel in MODELS:
            save_answer(tmp_path, strId, strModel,
                        {"answer": f"{strId} answer **{MODELS.index(strModel)}**"})
    return tmp_path


@pytest.fixture
def review(output):
    return create_app(str(output), QUESTIONS).test_client()


def read_ratings(output):
    return json.loads((output / "ratings.json").read_text())


def rate(review, **changes):
    dctRating = {"question_id": "Q01", "position": "B", "rating": "ok", "factual_error": False,
                 "note": ""}
    return review.post("/rate", json=dctRating | changes)


def test_the_key_holds_every_model_once_and_the_order_varies(output):
    setOrders = set()
    for intSeed in range(20):
        (output / "key.json").unlink(missing_ok=True)
        dctKey = get_key(str(output), QUESTIONS, random.Random(intSeed))
        assert all(sorted(dctKey[strId].values()) == sorted(MODELS) for strId in ("Q01", "Q03"))
        assert list(dctKey["Q01"]) == ["A", "B", "C"]
        setOrders.add(tuple(dctKey["Q01"].values()))
    assert len(setOrders) > 1


def test_the_key_stays_the_same(output):
    dctKey = get_key(str(output), QUESTIONS, random.Random(1))
    assert get_key(str(output), QUESTIONS, random.Random(2)) == dctKey
    assert json.loads((output / "key.json").read_text()) == dctKey


def test_another_batch_is_added_to_the_key(output):
    dctFirst = get_key(str(output), QUESTIONS[:1])
    dctBoth = get_key(str(output), QUESTIONS)
    assert dctBoth["Q01"] == dctFirst["Q01"]
    assert set(dctBoth) == {"Q01", "Q03"}


def test_a_model_answered_after_the_key_was_made_is_refused(output):
    get_key(str(output), QUESTIONS)
    save_answer(output, "Q01", "gpt-6.2-sol", {"answer": "late"})
    with pytest.raises(ValueError, match="Q01"):
        get_key(str(output), QUESTIONS)


def test_a_failed_answer_is_not_reviewed(output):
    save_answer(output, "Q01", "gpt-6-luna", {"error": "RateLimitError: no credits left"})
    strPage = create_app(str(output), QUESTIONS).test_client().get("/").text
    assert "no credits left" not in strPage
    assert get_key(str(output), QUESTIONS)["Q01"].keys() == {"A", "B"}


def test_a_question_without_an_answer_is_refused(output):
    for strModel in MODELS:
        save_answer(output, "Q03", strModel, {"error": "broken"})
    with pytest.raises(ValueError, match="Q03"):
        get_key(str(output), QUESTIONS)


def test_the_page_shows_the_answers_and_no_model(review):
    strPage = review.get("/").text
    assert "how &lt;many&gt; seats" in strPage
    for strId in ("Q01", "Q03"):
        assert f"documents for {strId}" in strPage
        for intModel in range(3):
            assert f"{strId} answer <strong>{intModel}</strong>" in strPage
    assert "gpt" not in strPage.lower()


def test_the_answers_are_shown_in_the_order_of_the_key(review, output):
    strPage = review.get("/").text
    dctKey = json.loads((output / "key.json").read_text())
    lstPlaces = [strPage.index(f"Q01 answer <strong>{MODELS.index(strModel)}</strong>")
                 for strModel in dctKey["Q01"].values()]
    assert lstPlaces == sorted(lstPlaces)


def test_a_rating_is_saved_and_shown_again(review, output):
    assert rate(review, factual_error=True, note='wrong "torque"').status_code == 200
    assert read_ratings(output) == {"Q01": {"B": {"rating": "ok", "factual_error": True,
                                                  "note": 'wrong "torque"'}}}
    strPage = review.get("/").text
    assert "wrong &#34;torque&#34;" in strPage
    assert 'name="Q01-B" value="ok" checked' in strPage
    assert strPage.count(" checked") == 2


def test_a_rating_can_be_changed_and_leaves_the_others(review, output):
    rate(review)
    rate(review, position="A", rating="perfect")
    rate(review, rating="not_good")
    dctRatings = read_ratings(output)["Q01"]
    assert {strPosition: dctRating["rating"] for strPosition, dctRating in dctRatings.items()} == \
        {"A": "perfect", "B": "not_good"}


def test_a_note_can_be_saved_before_the_rating(review, output):
    assert rate(review, rating=None, note="look up").status_code == 200
    assert read_ratings(output)["Q01"]["B"]["rating"] is None


@pytest.mark.parametrize("changes", [
    {"rating": "good"}, {"position": "D"}, {"question_id": "Q99"}, {"factual_error": "yes"},
    {"note": None}])
def test_a_rating_that_makes_no_sense_is_refused(review, output, changes):
    assert rate(review, **changes).status_code == 400
    assert not (output / "ratings.json").exists()


# Runs the page's script with one answer, not rated at first. Each step is something the reader does.
PAGE_RUNNER = """
const vm = require('vm');
const {script, steps} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const elements = {progress: {}, saved: {}, failed: {}};
const listeners = {}, pageListeners = {}, sent = [], shown = [];
const radio = {value: 'perfect', checked: false}, box = {checked: false};
const note = {value: '', tagName: 'TEXTAREA'};
let reachable = true, asked = false;
const answer = {
  dataset: {question: 'Q01', position: 'B'},
  classList: {toggle: () => {}},
  querySelector: q => q === 'textarea' ? note : q === 'input[type=checkbox]' ? box
                    : radio.checked ? radio : null,
  addEventListener: (name, call) => { listeners[name] = call; },
};
const page = {
  console: {error: () => {}},
  window: {addEventListener: (name, call) => { pageListeners[name] = call; }},
  document: {querySelectorAll: () => [answer], getElementById: id => elements[id]},
  fetch: (url, options) => {
    if (!reachable) return Promise.reject(new Error('unreachable'));
    sent.push([url, options.method, JSON.parse(options.body)]);
    return Promise.resolve({ok: true});
  },
};
const actions = {
  rate: () => { radio.checked = true; listeners.change({target: radio}); },
  type: () => { note.value = 'wrong'; listeners.input({target: note}); },
  leave_note: () => listeners.change({target: note}),
  stop_server: () => { reachable = false; },
  close: () => { pageListeners.beforeunload({preventDefault: () => { asked = true; }}); },
};
vm.runInNewContext(script, page);
(async () => {
  for (const step of steps) {
    actions[step]();
    await new Promise(setImmediate);
    shown.push([elements.progress, elements.saved, elements.failed].map(e => e.textContent));
  }
  console.log(JSON.stringify({sent, shown, asked}));
})();
"""


@pytest.fixture
def use_page(review):
    """Runs the page's script while the reader does the given steps."""
    (strScript,) = re.findall(r"<script>(.*?)</script>", review.get("/").text, re.DOTALL)

    def run(*lstSteps):
        process = subprocess.run(["node", "-e", PAGE_RUNNER], check=True, capture_output=True,
                                 input=json.dumps({"script": strScript, "steps": lstSteps}),
                                 text=True, timeout=20)
        assert process.stderr == ""
        return json.loads(process.stdout)
    return run


def test_a_click_is_sent_at_once_and_the_route_accepts_it(use_page, review, output):
    dctSeen = use_page("rate", "close")
    ((strUrl, strMethod, dctBody),) = dctSeen["sent"]
    assert strMethod == "POST"
    assert review.post(strUrl, json=dctBody).status_code == 200
    assert read_ratings(output) == {"Q01": {"B": {"rating": "perfect", "factual_error": False,
                                                  "note": ""}}}
    assert dctSeen["shown"][0] == ["1 of 1 rated.", "All saved.", ""]
    assert not dctSeen["asked"]


def test_a_rating_that_could_not_be_saved_is_reported(use_page):
    dctSeen = use_page("stop_server", "rate", "close")
    assert dctSeen["shown"][1] == ["1 of 1 rated.", "", "1 not saved."]
    assert dctSeen["asked"]


def test_closing_the_page_with_an_unsaved_note_is_questioned(use_page):
    dctSeen = use_page("type", "close")
    assert dctSeen["sent"] == []
    assert dctSeen["shown"][0] == ["0 of 1 rated.", "", "1 not saved."]
    assert dctSeen["asked"]


def test_a_note_is_sent_when_the_reader_leaves_it(use_page):
    dctSeen = use_page("type", "leave_note", "close")
    assert [body["note"] for _, _, body in dctSeen["sent"]] == ["wrong"]
    assert dctSeen["shown"][1] == ["0 of 1 rated.", "All saved.", ""]
    assert not dctSeen["asked"]
