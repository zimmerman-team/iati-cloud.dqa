import json
from unittest.mock import patch

import pytest


@pytest.fixture
def data_dir(tmp_path):
    """Temp data directory with two JSON config lists."""
    (tmp_path / "default_dates.json").write_text(json.dumps(["1900-01-01", "1970-01-01"]))
    (tmp_path / "document_validation_exemptions.json").write_text(json.dumps([]))
    return tmp_path


@pytest.fixture
def patched_data_dir(data_dir):
    """Patch DATA_DIR in main so routes use the temp directory."""
    with patch("app.main.DATA_DIR", str(data_dir)):
        yield data_dir


class TestListConfigs:
    """GET /dqa/config"""

    def test_returns_sorted_config_names(self, client, patched_data_dir):
        response = client.get("/dqa/config")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["configs"] == ["default_dates", "document_validation_exemptions"]

    def test_names_have_no_extension(self, client, patched_data_dir):
        response = client.get("/dqa/config")
        data = json.loads(response.data)
        for name in data["configs"]:
            assert not name.endswith(".json")

    def test_non_json_files_excluded(self, client, patched_data_dir):
        (patched_data_dir / "README.txt").write_text("ignore me")
        response = client.get("/dqa/config")
        data = json.loads(response.data)
        assert "README" not in data["configs"]

    def test_invalid_config_name(self, client, patched_data_dir):
        # Test with a config name matching re.compile(r"^\w+$")
        response = client.get("/dqa/config/invalid-name!")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Invalid" in data["error"]


class TestGetConfig:
    """GET /dqa/config/<config_name>"""

    def test_returns_values(self, client, patched_data_dir):
        response = client.get("/dqa/config/default_dates")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["config_name"] == "default_dates"
        assert data["values"] == ["1900-01-01", "1970-01-01"]

    def test_returns_empty_list(self, client, patched_data_dir):
        response = client.get("/dqa/config/document_validation_exemptions")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["values"] == []

    def test_unknown_config_returns_404(self, client, patched_data_dir):
        response = client.get("/dqa/config/nonexistent")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data


class TestEditConfigAdd:
    """PATCH /dqa/config/<config_name> — action: add"""

    def test_add_new_value(self, client, patched_data_dir):
        payload = {"action": "add", "value": "2000-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "2000-01-01" in data["values"]

    def test_add_value_returns_sorted_list(self, client, patched_data_dir):
        payload = {"action": "add", "value": "1800-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = json.loads(response.data)
        assert data["values"] == sorted(data["values"])

    def test_add_persists_to_file(self, client, patched_data_dir):
        payload = {"action": "add", "value": "2000-01-01"}
        client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        with open(patched_data_dir / "default_dates.json") as f:
            saved = json.load(f)
        assert "2000-01-01" in saved

    def test_add_duplicate_returns_409(self, client, patched_data_dir):
        payload = {"action": "add", "value": "1900-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_add_missing_value_field_returns_400(self, client, patched_data_dir):
        payload = {"action": "add"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestEditConfigRemove:
    """PATCH /dqa/config/<config_name> — action: remove"""

    def test_remove_existing_value(self, client, patched_data_dir):
        payload = {"action": "remove", "value": "1900-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "1900-01-01" not in data["values"]

    def test_remove_persists_to_file(self, client, patched_data_dir):
        payload = {"action": "remove", "value": "1900-01-01"}
        client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        with open(patched_data_dir / "default_dates.json") as f:
            saved = json.load(f)
        assert "1900-01-01" not in saved

    def test_remove_nonexistent_value_returns_404(self, client, patched_data_dir):
        payload = {"action": "remove", "value": "9999-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_remove_missing_value_field_returns_400(self, client, patched_data_dir):
        payload = {"action": "remove"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestEditConfigUpdate:
    """PATCH /dqa/config/<config_name> — action: update"""

    def test_update_existing_value(self, client, patched_data_dir):
        payload = {"action": "update", "old_value": "1900-01-01", "new_value": "1901-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "1901-01-01" in data["values"]
        assert "1900-01-01" not in data["values"]

    def test_update_persists_to_file(self, client, patched_data_dir):
        payload = {"action": "update", "old_value": "1900-01-01", "new_value": "1901-01-01"}
        client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        with open(patched_data_dir / "default_dates.json") as f:
            saved = json.load(f)
        assert "1901-01-01" in saved
        assert "1900-01-01" not in saved

    def test_update_old_value_not_found_returns_404(self, client, patched_data_dir):
        payload = {"action": "update", "old_value": "9999-01-01", "new_value": "1901-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_update_new_value_already_exists_returns_409(self, client, patched_data_dir):
        payload = {"action": "update", "old_value": "1900-01-01", "new_value": "1970-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_update_missing_fields_returns_400(self, client, patched_data_dir):
        payload = {"action": "update", "old_value": "1900-01-01"}
        response = client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestEditConfigErrors:
    """Cross-action error cases for PATCH."""

    def test_unknown_config_returns_404(self, client, patched_data_dir):
        payload = {"action": "add", "value": "foo"}
        response = client.patch(
            "/dqa/config/nonexistent",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_invalid_body_returns_400(self, client, patched_data_dir):
        response = client.patch(
            "/dqa/config/default_dates",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_invalid_action_returns_400(self, client, patched_data_dir):
        payload = {"action": "delete", "value": "1900-01-01"}
        response = client.patch(
            "/dqa/config/default_dates!",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 400


@pytest.fixture(autouse=True)
def restore_default_dates():
    """Save and restore settings.default_dates after every test to prevent cross-test leakage."""
    from app.config import settings

    original = settings.default_dates
    yield
    settings.default_dates = original


class TestDefaultDatesSettingsSync:
    """After editing default_dates, settings.default_dates should reflect the change."""

    def test_add_syncs_settings(self, client, patched_data_dir):
        from app.config import settings

        payload = {"action": "add", "value": "2000-01-01"}
        client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert "2000-01-01" in settings.default_dates

    def test_remove_syncs_settings(self, client, patched_data_dir):
        from app.config import settings

        payload = {"action": "remove", "value": "1900-01-01"}
        client.patch(
            "/dqa/config/default_dates",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert "1900-01-01" not in settings.default_dates

    def test_other_config_does_not_affect_settings(self, client, patched_data_dir):
        from app.config import settings

        original = settings.default_dates
        payload = {"action": "add", "value": "GB-GOV-99"}
        client.patch(
            "/dqa/config/document_validation_exemptions",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert settings.default_dates == original
