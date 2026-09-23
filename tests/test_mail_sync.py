import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "mac"))


def test_mail_sync_without_configured_accounts_is_a_noop(tmp_path, monkeypatch, capsys):
    import importlib, sys
    monkeypatch.setenv("JOB_MONITOR_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("JOB_MONITOR_MAIL_ACCOUNTS", raising=False)
    sys.modules.pop("mail_sync", None)
    mail_sync = importlib.import_module("mail_sync")
    mail_sync.main()
    assert "JOB_MONITOR_MAIL_ACCOUNTS" in capsys.readouterr().out
    assert not (tmp_path / "application_history.json").exists()
