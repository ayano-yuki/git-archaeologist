from llm_tuning_lab.collect.github_api import GitHubClient


def test_build_url_omits_empty_params() -> None:
    client = GitHubClient(base_url="https://example.test")

    url = client.build_url("/repos/react/react/issues", {"state": "all", "since": ""})

    assert url == "https://example.test/repos/react/react/issues?state=all"


def test_headers_include_token_when_present() -> None:
    client = GitHubClient(token="secret")

    assert client._headers()["Authorization"] == "Bearer secret"
