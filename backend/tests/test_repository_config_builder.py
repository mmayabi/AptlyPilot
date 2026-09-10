from copy import deepcopy
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import config_loader_service
from app.ui import repository_config_builder as builder


class FormParser(HTMLParser):
    """Collect successful controls as a browser would submit them."""

    def __init__(self, html):
        super().__init__()
        self.data = {}
        self.textareas = {}
        self.select = None
        self.textarea = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        name = attrs.get("name")
        if tag == "input" and name and "disabled" not in attrs:
            if attrs.get("type") != "checkbox" or "checked" in attrs:
                self.data[name] = attrs.get("value", "")
        if tag == "select":
            self.select = name if "disabled" not in attrs else None
        if tag == "option" and self.select:
            if self.select not in self.data or "selected" in attrs:
                self.data[self.select] = attrs.get("value", "")
        if tag == "textarea":
            self.textarea = name
            self.textareas[name] = ""

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None
        if tag == "textarea":
            self.textarea = None

    def handle_data(self, data):
        if self.textarea:
            self.textareas[self.textarea] += data


@pytest.fixture
def setup_builder(monkeypatch, tmp_path):
    config = {
        "defaults": {"schedule": {"enabled": True, "type": "weekly"}},
        "custom_root": {"keep": True},
        "repos": {"debian": {"bookworm": {
            "main": {
                "mirror": {"archive_url": "https://example.org/debian", "distribution": "bookworm",
                           "components": ["main"], "architectures": ["amd64"], "custom": "keep"},
                "publish": {"enabled": False, "codename": "custom", "suite": "stable"},
                "test": {"enabled": False, "checks": ["custom-check"]},
                "custom_repo": [1, 2],
            },
            "other": {
                "mirror": {"archive_url": "https://example.org/other", "distribution": "bookworm",
                           "components": ["main"], "architectures": ["amd64"]},
                "publish": {"enabled": False},
            },
        }}},
    }
    path = tmp_path / "repos.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(builder, "load_repos_config_text", path.read_text)
    monkeypatch.setattr(builder, "get_repos_config_source", lambda: "local")
    monkeypatch.setattr(builder, "get_repos_config_location", lambda: str(path))
    monkeypatch.setattr(builder, "is_local_repos_config_source", lambda: True)
    monkeypatch.setattr(config_loader_service, "get_repos_config_path", lambda: path)
    monkeypatch.setattr(config_loader_service, "is_local_repos_config_source", lambda: True)
    app = FastAPI()
    app.include_router(builder.router)
    app.dependency_overrides[builder.get_web_admin] = lambda: SimpleNamespace(is_superuser=True)
    app.dependency_overrides[builder.get_db_session] = lambda: None
    return TestClient(app), path, config


def edit_form(client):
    response = client.get("/repositories/config-builder", params={
        "repository_key": builder._repository_key("debian", "bookworm", "main"),
    })
    assert response.status_code == 200
    return FormParser(response.text).data


def preview(client, data):
    response = client.post("/repositories/config-builder/preview", data=data)
    assert response.status_code == 200
    return FormParser(response.text)


def test_edit_without_changes_preserves_entire_config(setup_builder):
    client, _, config = setup_builder
    form = edit_form(client)
    assert form["schedule_type"] == "weekly"
    assert form["test_enabled"] == "false"
    result = preview(client, form)
    assert yaml.safe_load(result.textareas["yaml_content"]) == config


def test_disable_schedule_preserves_inherited_type_and_other_fields(setup_builder):
    client, path, config = setup_builder
    form = edit_form(client)
    form.pop("schedule_enabled")
    result = preview(client, form)
    updated = yaml.safe_load(result.textareas["yaml_content"])
    expected = deepcopy(config)
    expected["repos"]["debian"]["bookworm"]["main"]["schedule"] = {
        "enabled": False, "type": "weekly",
    }
    assert updated == expected
    response = client.post("/repositories/config-builder/save", data={
        "yaml_content": result.textareas["yaml_content"],
        "base_content": result.textareas["base_content"],
    })
    assert response.headers["HX-Refresh"] == "true"
    assert yaml.safe_load(path.read_text()) == expected
    form = edit_form(client)
    assert "schedule_enabled" not in form
    assert form["schedule_type"] == "weekly"


def test_edit_one_field_preserves_unknown_fields(setup_builder):
    client, _, config = setup_builder
    form = edit_form(client)
    form["mirror_archive_url"] = "https://example.org/updated"
    result = preview(client, form)
    expected = deepcopy(config)
    expected["repos"]["debian"]["bookworm"]["main"]["mirror"]["archive_url"] = form["mirror_archive_url"]
    assert yaml.safe_load(result.textareas["yaml_content"]) == expected


def test_create_without_schedule(setup_builder):
    client, _, config = setup_builder
    form = FormParser(client.get("/repositories/config-builder").text).data
    form.update(provider="debian", release="bookworm", repo_name="new",
                mirror_archive_url="https://example.org/new", mirror_distribution="bookworm",
                mirror_components="main", publish_prefix="new")
    form.pop("schedule_enabled")
    result = yaml.safe_load(preview(client, form).textareas["yaml_content"])
    new = result["repos"]["debian"]["bookworm"].pop("new")
    assert result == config
    assert new["schedule"]["enabled"] is False
    assert new["publish"]["distribution"] == "bookworm"
    assert new["test"]["checks"] == ["metadata"]


def test_create_cannot_overwrite_existing_repository(setup_builder):
    client, path, _ = setup_builder
    before = path.read_text()
    form = edit_form(client)
    form["repository_key"] = ""
    response = client.post("/repositories/config-builder/preview", data=form)
    assert "already exists" in response.text
    assert path.read_text() == before


def test_stale_preview_cannot_overwrite_changed_file(setup_builder):
    client, path, _ = setup_builder
    result = preview(client, edit_form(client))
    changed = path.read_text() + "\n# edited elsewhere\n"
    path.write_text(changed)
    response = client.post("/repositories/config-builder/save", data={
        "yaml_content": result.textareas["yaml_content"],
        "base_content": result.textareas["base_content"],
    })
    assert "Config changed since preview" in response.text
    assert path.read_text() == changed


def test_invalid_source_is_not_replaced_with_empty_config(setup_builder):
    client, path, _ = setup_builder
    form = edit_form(client)
    path.write_text("repos: [invalid")
    response = client.post("/repositories/config-builder/preview", data=form)
    assert "Cannot build config" in response.text
    assert path.read_text() == "repos: [invalid"

