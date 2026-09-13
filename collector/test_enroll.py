"""Checks the collector's browser sign-in hand-off without a browser."""
import http.client
import threading
from urllib.parse import parse_qs, urlparse

import collector


def get(port, query):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", f"/callback?{query}")
    return conn.getresponse().status


def fake_dashboard(url):
    """Stand in for the /connect page: a forged answer first, then the real one."""
    q = parse_qs(urlparse(url).query)
    port, state = int(q["port"][0]), q["state"][0]
    assert q["host"][0], "Connect page needs the hostname to show"

    def respond():
        assert get(port, "state=forged&token=evil") == 400
        assert get(port, f"state={state}&token=good") == 302

    threading.Thread(target=respond).start()


collector.webbrowser.open = fake_dashboard
assert collector.enroll_via_browser() == "good"
print("✓ enroll: forged state rejected, real token accepted")
