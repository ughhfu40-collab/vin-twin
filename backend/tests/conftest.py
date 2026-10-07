import pytest

@pytest.fixture(autouse=True)
def isolate_snapshot_store(tmp_path,monkeypatch):
    from backend.main import snapshots
    snapshots.clear()
    monkeypatch.setenv('VIN_STATE_PATH',str(tmp_path/'snapshot-test.sqlite3'))
    yield
    snapshots.clear()
