from app.utils import backend_data_paths


class TestBackendDataPaths:
    def test_ensure_backend_data_dir_moves_legacy_files_and_directories(
        self, tmp_path, monkeypatch
    ):
        backend_dir = tmp_path / "src" / "backend" / "data"
        legacy_dir = tmp_path / "data"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "manual_gateways.json").write_text("[]", encoding="utf-8")
        gateway_dir = legacy_dir / "manual_gateways"
        gateway_dir.mkdir()
        (gateway_dir / "config.json").write_text('{"exchange_type":"MT5"}', encoding="utf-8")

        monkeypatch.setattr(backend_data_paths, "BACKEND_DATA_DIR", backend_dir)
        monkeypatch.setattr(backend_data_paths, "LEGACY_BACKEND_DATA_DIR", legacy_dir)
        monkeypatch.setattr(backend_data_paths, "_MIGRATION_DONE", False)

        resolved = backend_data_paths.ensure_backend_data_dir()

        assert resolved == backend_dir
        assert (backend_dir / "manual_gateways.json").read_text(encoding="utf-8") == "[]"
        assert (backend_dir / "manual_gateways" / "config.json").exists()
        assert not legacy_dir.exists()

    def test_ensure_backend_data_dir_keeps_existing_backend_files(self, tmp_path, monkeypatch):
        backend_dir = tmp_path / "src" / "backend" / "data"
        legacy_dir = tmp_path / "data"
        backend_dir.mkdir(parents=True)
        legacy_dir.mkdir(parents=True)
        (backend_dir / "manual_gateways.json").write_text('[{"from":"backend"}]', encoding="utf-8")
        (legacy_dir / "manual_gateways.json").write_text('[{"from":"legacy"}]', encoding="utf-8")

        monkeypatch.setattr(backend_data_paths, "BACKEND_DATA_DIR", backend_dir)
        monkeypatch.setattr(backend_data_paths, "LEGACY_BACKEND_DATA_DIR", legacy_dir)
        monkeypatch.setattr(backend_data_paths, "_MIGRATION_DONE", False)

        backend_data_paths.ensure_backend_data_dir()

        assert (backend_dir / "manual_gateways.json").read_text(
            encoding="utf-8"
        ) == '[{"from":"backend"}]'
        assert (legacy_dir / "manual_gateways.json").read_text(
            encoding="utf-8"
        ) == '[{"from":"legacy"}]'

    def test_get_backend_data_path_returns_nested_path(self, tmp_path, monkeypatch):
        backend_dir = tmp_path / "src" / "backend" / "data"
        legacy_dir = tmp_path / "data"

        monkeypatch.setattr(backend_data_paths, "BACKEND_DATA_DIR", backend_dir)
        monkeypatch.setattr(backend_data_paths, "LEGACY_BACKEND_DATA_DIR", legacy_dir)
        monkeypatch.setattr(backend_data_paths, "_MIGRATION_DONE", False)

        resolved = backend_data_paths.get_backend_data_path("manual_gateways", "config.json")

        assert resolved == backend_dir / "manual_gateways" / "config.json"
        assert backend_dir.exists()
