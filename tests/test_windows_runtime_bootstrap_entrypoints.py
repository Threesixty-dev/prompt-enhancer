from types import SimpleNamespace

import pytest

from prompt_enhancer import cli


class _Bootstrap:
    def __init__(self, fail: bool = False): self.closed = False; self.fail = fail
    def close(self) -> None:
        self.closed = True
        if self.fail: raise RuntimeError("synthetic")


def test_cli_keeps_embedded_bootstrap_until_handler_returns(monkeypatch):
    value=_Bootstrap();monkeypatch.setattr(cli,'bootstrap_current_embedded_windows_runtime',lambda:value)
    monkeypatch.setattr(cli,'_parser',lambda:SimpleNamespace(parse_args=lambda _:SimpleNamespace(command='status')))
    monkeypatch.setattr(cli.AppSettings,'from_env',lambda:SimpleNamespace())
    def status(_):
        assert not value.closed
        return 0
    monkeypatch.setattr(cli,'_run_status',status)
    assert cli.main(['status'])==0 and value.closed


def test_cli_returns_nonzero_when_embedded_bootstrap_cleanup_fails(monkeypatch):
    value=_Bootstrap(fail=True);monkeypatch.setattr(cli,'bootstrap_current_embedded_windows_runtime',lambda:value)
    monkeypatch.setattr(cli,'_parser',lambda:SimpleNamespace(parse_args=lambda _:SimpleNamespace(command='status')))
    monkeypatch.setattr(cli.AppSettings,'from_env',lambda:SimpleNamespace())
    monkeypatch.setattr(cli,'_run_status',lambda _:0)
    assert cli.main(['status'])==1 and value.closed

def test_cli_preserves_pending_keyboard_interrupt_while_cleaning_bootstrap(monkeypatch):
    value=_Bootstrap();monkeypatch.setattr(cli,'bootstrap_current_embedded_windows_runtime',lambda:value)
    monkeypatch.setattr(cli,'_parser',lambda:SimpleNamespace(parse_args=lambda _:(_ for _ in ()).throw(KeyboardInterrupt())))
    with pytest.raises(KeyboardInterrupt):cli.main(['status'])
    assert value.closed
