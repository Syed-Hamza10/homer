from achilles_mcp_search.search import parse_results, real_url

PAGE = """
<html><body>
<div class="result results_links results_links_deep web-result result--ad">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_provider=x">Sponsored</a>
  </h2>
  <a class="result__snippet" href="https://duckduckgo.com/y.js?ad_provider=x">Buy now</a>
</div>
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&amp;rut=abc">
      Welcome to <b>Python</b>.org
    </a>
  </h2>
  <a class="result__snippet"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&amp;rut=abc">
    The official home of the <b>Python</b> Programming Language.<br>
  </a>
</div>
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://docs.example.test/guide">Guide</a>
  </h2>
  <a class="result__snippet" href="https://docs.example.test/guide">A guide.</a>
</div>
</body></html>
"""


def test_real_url_decodes_redirects_only() -> None:
    encoded = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&rut=abc"
    assert real_url(encoded) == "https://www.python.org/"
    assert real_url("https://docs.example.test/guide") == "https://docs.example.test/guide"


def test_parse_results_pairs_titles_and_snippets_and_drops_ads() -> None:
    assert parse_results(PAGE) == [
        {
            "title": "<untrusted>Welcome to Python.org</untrusted>",
            "url": "https://www.python.org/",
            "snippet": "<untrusted>The official home of the Python Programming Language."
            "</untrusted>",
        },
        {
            "title": "<untrusted>Guide</untrusted>",
            "url": "https://docs.example.test/guide",
            "snippet": "<untrusted>A guide.</untrusted>",
        },
    ]


def test_parse_results_empty_page() -> None:
    assert parse_results("<html><body><p>No results.</p></body></html>") == []
