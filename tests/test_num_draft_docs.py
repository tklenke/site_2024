# ABOUTME: Tests how many retrieved chunks the first answer is given.
# ABOUTME: The number is a count of chunks, between the minimum and maximum settings.

import pytest

from src.llm_functions import get_num_draft_docs

MAX_DISTANCE = .35
MIN_DOCS = 5
MAX_DRAFT_DOCS = 15
RETRIEVED = 60


def query_result(intClose):
    """A query result whose first intClose chunks are inside the distance cutoff."""
    return {"distances": [[.2] * intClose + [.5] * (RETRIEVED - intClose)]}


@pytest.mark.parametrize("intClose, intExpected", [
    (60, 15), (16, 15), (15, 15), (14, 14), (7, 7), (6, 6), (5, 5), (4, 5), (1, 5), (0, 5)])
def test_number_of_draft_docs(intClose, intExpected):
    assert get_num_draft_docs(query_result(intClose), MAX_DISTANCE, MIN_DOCS,
                              MAX_DRAFT_DOCS) == intExpected
