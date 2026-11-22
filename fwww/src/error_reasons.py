# ABOUTME: The failures of a job that Tom has to fix, and what a visitor is told about a failed job.
# ABOUTME: Gives the reason code for an exception and the text shown for a reason code.

import openai

# the codes of a used-up budget, from https://developers.openai.com/api/docs/guides/error-codes
BUDGET_CODES = ('credit_balance_exhausted', 'organization_spend_limit_exceeded',
                'project_spend_limit_exceeded', 'organization_usage_limit_exceeded')
# can be the code or the type of the error
BUDGET_QUOTA = 'insufficient_quota'

def is_budget_used_up(exception):
    return isinstance(exception, openai.RateLimitError) and \
        (exception.code in BUDGET_CODES or BUDGET_QUOTA in (exception.code, exception.type))

def is_access_refused(exception):
    return isinstance(exception, (openai.AuthenticationError, openai.PermissionDeniedError))

def is_model_missing(exception):
    return isinstance(exception, openai.NotFoundError)

# for each reason code: how its failure is recognised, and the phrase shown to the visitor
ERROR_REASONS = {
    'openai_budget': (is_budget_used_up, "OpenAI budget used up"),
    'openai_access': (is_access_refused, "OpenAI key rejected"),
    'openai_model': (is_model_missing, "OpenAI model not available"),
}

def get_error_reason(exception):
    """
    Gives the reason code of a failure that Tom has to fix.

    :param exception: The exception that ended the job.
    :return: The code, or None when the failure has no reason.
    """
    for code, (is_recognised, _) in ERROR_REASONS.items():
        if is_recognised(exception):
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
