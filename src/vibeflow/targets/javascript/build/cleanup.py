"""Release all owned resources before reporting lifecycle cleanup errors."""


def finish_cleanup(primary, errors):
    if not errors:
        return
    error = primary or errors[0]
    details = dict(getattr(error, "details", {}) or {})
    details["cleanup_errors"] = [*details.get("cleanup_errors", ()), *(
        {"code": str(getattr(item, "code", type(item).__name__)),
         "message": str(item), "phase": "cleanup"} for item in errors)]
    error.details = details
    if primary is None:
        raise error
