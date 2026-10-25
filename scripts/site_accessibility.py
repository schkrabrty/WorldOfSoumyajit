"""Small accessibility checks shared by page saving and production validation."""
from html.parser import HTMLParser


def content_accessibility_errors(text):
    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.errors = []

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "img" and "alt" not in attrs:
                self.errors.append('Add an image description (alt text), or use alt="" for a decorative image.')
            if tag == "iframe" and not (attrs.get("title") or "").strip():
                self.errors.append("Give every embedded video or frame a descriptive title.")

        handle_startendtag = handle_starttag

    check = Check()
    check.feed(text)
    return list(dict.fromkeys(check.errors))
