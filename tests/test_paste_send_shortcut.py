import spuk.paste as paste


def test_send_paste_shortcut_invokes_injector(monkeypatch):
    fired = []
    monkeypatch.setattr(paste, "_get_injector", lambda: (lambda: fired.append(1)))
    paste.send_paste_shortcut()
    assert fired == [1]
