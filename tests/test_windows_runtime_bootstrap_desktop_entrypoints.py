from types import SimpleNamespace

import pytest

from prompt_enhancer import desktop_overlay


class _Bootstrap:
    def __init__(self, fail: bool = False): self.closed = False; self.fail = fail
    def close(self) -> None:
        self.closed = True
        if self.fail: raise RuntimeError('synthetic')


@pytest.mark.parametrize(('entrypoint','runner'),[(desktop_overlay.desktop_main,'run_desktop_overlay'),(desktop_overlay.agent_desktop_main,'launch_desktop_agent')])
def test_gui_entrypoints_keep_bootstrap_alive_through_runner(monkeypatch,entrypoint,runner):
    value=_Bootstrap();monkeypatch.setattr(desktop_overlay,'bootstrap_current_embedded_windows_runtime',lambda:value)
    monkeypatch.setattr(desktop_overlay.AppSettings,'from_env',lambda:SimpleNamespace())
    def run(_):
        assert not value.closed
    monkeypatch.setattr(desktop_overlay,runner,run)
    assert entrypoint()==0 and value.closed


@pytest.mark.parametrize(('entrypoint','runner'),[(desktop_overlay.desktop_main,'run_desktop_overlay'),(desktop_overlay.agent_desktop_main,'launch_desktop_agent')])
def test_gui_entrypoints_fail_when_bootstrap_cleanup_fails(monkeypatch,entrypoint,runner):
    value=_Bootstrap(fail=True);monkeypatch.setattr(desktop_overlay,'bootstrap_current_embedded_windows_runtime',lambda:value)
    monkeypatch.setattr(desktop_overlay.AppSettings,'from_env',lambda:SimpleNamespace())
    monkeypatch.setattr(desktop_overlay,runner,lambda _:None)
    assert entrypoint()==1 and value.closed
