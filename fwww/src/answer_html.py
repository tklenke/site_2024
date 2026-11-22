# ABOUTME: Gives the HTML of an answer, which is text written by a language model.
# ABOUTME: Raw HTML in an answer is shown as text; only the renderer's own tags reach the page.

from markdown_it import MarkdownIt

AnswerMd = MarkdownIt('commonmark', {'html': False}).enable('table').disable('image')

def get_answer_html(text):
    """
    Renders the Markdown of an answer.

    :param text: The text of the answer.
    :return: The HTML, safe to put in a page.
    """
    return AnswerMd.render(text)
