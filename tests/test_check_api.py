import httpx
import pytest

from scripts.check_api import check


def test_check_uses_existing_token_and_reports_inference_receipt(capsys):
    calls = []
    def handle(request):
        calls.append(request)
        if request.url.path == '/health/ready':
            return httpx.Response(200 if request.headers.get('Authorization') else 401)
        if request.method == 'POST':
            return httpx.Response(202, json={'id': 'a'*32})
        return httpx.Response(200, json={'status': 'succeeded'})
    with httpx.Client(base_url='https://test', headers={'Authorization': 'Bearer private'},
                      transport=httpx.MockTransport(handle)) as client:
        result = check(client, True)
    assert result['inference_status'] == 'succeeded'
    assert len(calls) == 4
    output = capsys.readouterr().out
    assert 'a'*32 in output and 'private' not in output


def test_readiness_check_never_submits():
    def handle(request):
        assert request.method == 'GET'
        return httpx.Response(200 if request.headers.get('Authorization') else 401)
    with httpx.Client(base_url='https://test', headers={'Authorization': 'Bearer private'},
                      transport=httpx.MockTransport(handle)) as client:
        assert check(client)['authenticated_readiness'] == 200


def test_missing_authentication_enforcement_is_a_failed_check():
    with httpx.Client(base_url='https://test', transport=httpx.MockTransport(
            lambda request: httpx.Response(200))) as client:
        with pytest.raises(ValueError, match='401'):
            check(client)
