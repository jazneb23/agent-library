from agents.hello import agent as hello


def test_search_finds_keyword():
    assert "SAML" in hello.search_docs("sso")


def test_search_miss_is_explicit():
    assert hello.search_docs("hipaa") == "No matching docs found."


def test_save_note_is_approval_gated():
    assert hello.registry.get("save_note").needs_approval
    assert not hello.registry.get("search_docs").needs_approval
