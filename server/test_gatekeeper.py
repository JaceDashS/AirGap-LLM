from gatekeeper import mask, restore


def test_single_url():
    text = "Call this endpoint: https://api.mycompany.com/v1/users"
    masked, vault = mask(text)
    assert "https://api.mycompany.com/v1/users" not in masked
    assert "[PII_URL_1]" in masked
    assert vault["[PII_URL_1]"] == "https://api.mycompany.com/v1/users"


def test_multiple_urls():
    text = "Use https://api.mycompany.com/auth to get a token, then call https://api.mycompany.com/data"
    masked, vault = mask(text)
    assert "[PII_URL_1]" in masked
    assert "[PII_URL_2]" in masked
    assert len(vault) == 2


def test_url_with_query_string():
    text = "GET https://api.mycompany.com/users?token=abc123&page=1"
    masked, vault = mask(text)
    assert "token=abc123" not in masked
    assert vault["[PII_URL_1]"] == "https://api.mycompany.com/users?token=abc123&page=1"


def test_no_url():
    text = "Write a function that sorts a list in Python."
    masked, vault = mask(text)
    assert masked == text
    assert vault == {}


def test_restore():
    text = "Call https://api.mycompany.com/v1/users and parse the response."
    masked, vault = mask(text)
    restored = restore(masked, vault)
    assert restored == text


def test_restore_survives_llm_context():
    # Simulates LLM keeping the token intact in its response
    vault = {"[PII_URL_1]": "https://api.mycompany.com/v1/users"}
    llm_response = "Here is the code to call [PII_URL_1] and handle errors."
    restored = restore(llm_response, vault)
    assert "https://api.mycompany.com/v1/users" in restored


if __name__ == "__main__":
    tests = [
        test_single_url,
        test_multiple_urls,
        test_url_with_query_string,
        test_no_url,
        test_restore,
        test_restore_survives_llm_context,
    ]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
