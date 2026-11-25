# ABOUTME: Gives the HTML of an answer, which is text written by a language model.
# ABOUTME: Raw HTML in an answer is shown as text; only the renderer's own tags reach the page.

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

AnswerMd = MarkdownIt('commonmark', {'html': False}).enable('table').disable('image')

# a citation mark, [3] or [2, 5], and the marks that follow it with nothing but spaces between
CITATION_MARK = r"\[\d+(?:\s*,\s*\d+)*\]"
CITATION_RUN = re.compile(rf"{CITATION_MARK}(?:[ \t]*{CITATION_MARK})*")

def get_answer_html(text, citations=None):
    """
    Renders the Markdown of an answer.

    :param text: The text of the answer.
    :param citations: For a numbered answer, for each chunk sent in the order sent, the 'number',
                      'href' (None when the source has no address) and 'title' of its source's row.
                      None for an answer that was not numbered: its text is not touched.
    :return: The HTML, safe to put in a page.
    """
    if citations is None:
        return AnswerMd.render(text)
    env = {}
    tokens = AnswerMd.parse(text, env)
    for token in tokens:
        if token.children:
            token.children = [new for child in token.children for new in link_citations(child, citations)]
    return AnswerMd.renderer.render(tokens, AnswerMd.options, env)

def get_cited_rows(run, citations):
    """The rows named by a run of marks, once each in the order written; a number that names no chunk is left out."""
    rows = {}
    for number in re.findall(r"\d+", run):
        index = int(number) - 1
        if 0 <= index < len(citations):
            rows.setdefault(citations[index]['number'], citations[index])
    return list(rows.values())

def link_citations(token, citations):
    """The tokens that replace a text token: its citation marks become the numbers of their rows."""
    if token.type != 'text':
        return [token]
    tokens = []
    position = 0
    for match in CITATION_RUN.finditer(token.content):
        tokens.append(text_token(token.content[position:match.start()]))
        for row in get_cited_rows(match.group(), citations):
            tokens += row_tokens(row)
        position = match.end()
    tokens.append(text_token(token.content[position:]))
    return [t for t in tokens if t.type != 'text' or t.content]

def text_token(content):
    token = Token('text', '', 0)
    token.content = content
    return token

def row_tokens(row):
    """A link to the row's source showing its number, or the number alone when the source has no address."""
    number = text_token(f"[{row['number']}]")
    if not row['href']:
        return [number]
    link_open = Token('link_open', 'a', 1)
    link_open.attrs = {'href': row['href'], 'title': row['title'], 'target': '_blank', 'rel': 'noopener'}
    return [link_open, number, Token('link_close', 'a', -1)]
