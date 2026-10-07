import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mac"))


def test_mail_sync_without_configured_accounts_is_a_noop(tmp_path, monkeypatch, capsys):
    import importlib
    import sys

    monkeypatch.setenv("JOB_MONITOR_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("JOB_MONITOR_MAIL_ACCOUNTS", raising=False)
    sys.modules.pop("mail_sync", None)
    mail_sync = importlib.import_module("mail_sync")
    mail_sync.main()
    assert "JOB_MONITOR_MAIL_ACCOUNTS" in capsys.readouterr().out
    assert not (tmp_path / "application_history.json").exists()


def test_mail_accounts_fall_back_to_accounts_yaml(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("JOB_MONITOR_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("JOB_MONITOR_MAIL_ACCOUNTS", raising=False)
    sys.modules.pop("mail_sync", None)
    mail_sync = importlib.import_module("mail_sync")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "accounts.yaml").write_text(
        "application_history:\n  mail_accounts: [me@example.com, school@example.edu]\n"
    )
    monkeypatch.setattr(mail_sync, "ROOT", tmp_path)
    assert mail_sync.configured_accounts() == ["me@example.com", "school@example.edu"]
    monkeypatch.setenv("JOB_MONITOR_MAIL_ACCOUNTS", "env@example.com")
    assert mail_sync.configured_accounts() == ["env@example.com"]
