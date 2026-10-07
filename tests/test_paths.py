import importlib


def test_config_and_data_dirs_can_point_at_a_private_instance(tmp_path, monkeypatch):
    import paths

    monkeypatch.setenv("JOB_MONITOR_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("JOB_MONITOR_DATA_DIR", str(tmp_path / "data"))
    reloaded = importlib.reload(paths)
    assert reloaded.CONFIG_DIR == tmp_path / "config"
    assert reloaded.DATA_DIR == tmp_path / "data"
    monkeypatch.delenv("JOB_MONITOR_CONFIG_DIR")
    monkeypatch.delenv("JOB_MONITOR_DATA_DIR")
    assert importlib.reload(paths).CONFIG_DIR == reloaded.ROOT / "config"
