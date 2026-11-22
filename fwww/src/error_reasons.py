# ABOUTME: The failures of a job that Tom has to fix, and what a visitor is told about a failed job.
# ABOUTME: Gives the reason code for an exception and the text shown for a reason code.

import openai

# for each reason code: the exceptions it is recognised by, and the phrase shown to the visitor
ERROR_REASONS = {
    'openai_access': ((openai.AuthenticationError, openai.PermissionDeniedError),
                      "OpenAI key rejected"),
    'openai_model': ((openai.NotFoundError,), "OpenAI model not available"),
}

def get_error_reason(exception):
    """
    Gives the reason code of a failure that Tom has to fix.

    :param exception: The exception that ended the job.
    :return: The code, or None when the failure has no reason.
    """
    for code, (exceptions, _) in ERROR_REASONS.items():
        if isinstance(exception, exceptions):
            return code
    return None

def get_error_text(code):
    """
    Gives the text that tells a visitor about a failed job.

    :param code: The reason code saved with the job, or None.
    :return: The text.
    """
    if code in ERROR_REASONS:
        _, phrase = ERROR_REASONS[code]
        return f"The site cannot answer questions until Tom fixes it. Please let him know: {phrase}."
    return "The question could not be answered. Please try again in a few minutes. " \
           "If it keeps failing, please let Tom know."
