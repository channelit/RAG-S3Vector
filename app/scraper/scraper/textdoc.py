"""The plain-text document stored for each CSMS message.

    CSMS # <id> — <subject>
    Sent: <dateline as published, or 'unknown'>
    Source: <bulletin URL>
    <blank line>
    <body text>
    <blank line>
    Attachments:
    - <filename>

`render_text_doc` writes it (pipeline) and `split_text_doc` reads it back
(collection summary), so the format is defined in one place.
"""

from .bulletin import Bulletin

_SUBJECT_SEPARATOR = " — "
_ATTACHMENTS_MARKER = "\n\nAttachments:\n"


def render_text_doc(bulletin: Bulletin) -> str:
    lines = [
        f"CSMS # {bulletin.message_id}{_SUBJECT_SEPARATOR}{bulletin.subject}",
        f"Sent: {bulletin.sent_raw or 'unknown'}",
        f"Source: {bulletin.url}",
        "",
        bulletin.body_text or "(no body text)",
    ]
    if bulletin.attachments:
        lines += ["", "Attachments:"]
        lines += [f"- {att.filename}" for att in bulletin.attachments]
    return "\n".join(lines) + "\n"


def split_text_doc(text: str) -> tuple[str, str]:
    """Return (subject, body text) of a document written by `render_text_doc`.

    The header lines and the trailing attachment list are left out, so the
    result is what the scraper originally ran country detection on.
    """
    header, _, rest = text.partition("\n\n")
    first_line = header.split("\n", 1)[0]
    _, separator, subject = first_line.partition(_SUBJECT_SEPARATOR)
    if not separator:
        subject = first_line

    body = rest
    marker_at = body.rfind(_ATTACHMENTS_MARKER)
    if marker_at != -1:
        listed = [ln for ln in body[marker_at + len(_ATTACHMENTS_MARKER):].splitlines() if ln]
        if listed and all(ln.startswith("- ") for ln in listed):
            body = body[:marker_at]
    return subject.strip(), body.strip()
