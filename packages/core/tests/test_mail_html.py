from homer_core.services.mail_html import sanitise

HOSTILE = (
    '<p style="color:red;background:url(https://e.example.test/x)">Hi</p>'
    '<svg onload="alert(1)"><circle/></svg><iframe src="https://e.example.test"></iframe>'
    '<a href=" JaVaScRiPt:alert(2)">a</a><a href="data:text/html,<b>x</b>">b</a>'
    '<img src="cid:logo"><img src="//e.example.test/p.gif"><img src="data:image/png;base64,AA">'
    '<form action="https://e.example.test"><input name="q"></form><b onmouseover="x()">bold</b>'
)


def test_hostile_markup_keeps_text_and_drops_everything_that_runs_or_fetches() -> None:
    cleaned = sanitise(HOSTILE)
    for unsafe in ("url(", "<svg", "<iframe", "javascript", "data:text", "cid:", "e.example"):
        assert unsafe.lower() not in cleaned.html.lower()
    for unsafe in ("onload", "onmouseover", "<form", "<input"):
        assert unsafe not in cleaned.html
    assert '<p style="color:red">Hi</p>' in cleaned.html and "<b>bold</b>" in cleaned.html
    assert 'src="data:image/png;base64,AA"' in cleaned.html
    assert cleaned.remote_images == 1


def test_shown_images_keep_their_source() -> None:
    cleaned = sanitise('<img src="https://e.example.test/p.gif" alt="logo">', show_images=True)
    assert cleaned.html == '<img src="https://e.example.test/p.gif" alt="logo">'
    assert cleaned.remote_images == 1
