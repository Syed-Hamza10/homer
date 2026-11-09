def test_build_raw_adds_an_html_part_that_reflows() -> None:
    import base64
    from email import message_from_bytes, policy

    from homer_mcp_google.messages import build_raw

    sentence = "A long sentence that should never be broken mid-line by a mail app. <b>"
    body = f"Hi Rosa,\n\n{sentence}\n\nBest,\nHamza\n"
    raw = build_raw("rosa@example.test", "Hello", body, None)
    parsed = message_from_bytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default
    )
    assert parsed.get_content_type() == "multipart/alternative"
    assert parsed.get_body(("plain",)).get_content() == body
    markup = parsed.get_body(("html",)).get_content()
    assert (
        "<p>A long sentence that should never be broken mid-line by a mail app. &lt;b&gt;</p>"
        in markup
    )
    assert "<p>Best,<br>Hamza</p>" in markup
