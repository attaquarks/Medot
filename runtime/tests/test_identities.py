"""Identity registry (M2b): specialists as data, versioned instructions."""
import pytest
from test_whatsapp_manager import FakeClient

from medot.identities import registry


def test_create_identity_slugs_and_versions():
    client = FakeClient()
    a = registry.create_identity(client, "u1", name="Garden Coach", instructions_md="water the plants")
    assert a["slug"] == "garden-coach"
    b = registry.create_identity(client, "u1", name="Garden Coach", instructions_md="more")
    assert b["slug"] == "garden-coach-2"
    instructions = client.tables["identity_instructions"]
    assert [i["version"] for i in instructions] == [1, 1]
    assert all(i["is_active"] and i["user_id"] == "u1" for i in instructions)


def test_create_identity_requires_name_and_instructions():
    client = FakeClient()
    with pytest.raises(ValueError, match="name"):
        registry.create_identity(client, "u1", name="  ", instructions_md="x")
    with pytest.raises(ValueError, match="instructions"):
        registry.create_identity(client, "u1", name="Coach", instructions_md="  ")


def test_update_identity_patches_only_given_fields_and_validates_status():
    client = FakeClient()
    created = registry.create_identity(client, "u1", name="Coach", instructions_md="hi")
    registry.update_identity(
        client, "u1", created["id"], description="plants", status="deactivated", model_profile_id="prof-9"
    )
    row = client.tables["identities"][0]
    assert row["description"] == "plants"
    assert row["status"] == "deactivated"
    assert row["model_profile_id"] == "prof-9"
    assert row["name"] == "Coach"  # untouched
    with pytest.raises(ValueError, match="status"):
        registry.update_identity(client, "u1", created["id"], status="zombie")
    with pytest.raises(ValueError, match="nothing to update"):
        registry.update_identity(client, "u1", created["id"])


def test_save_instructions_bumps_version_and_deactivates_old():
    client = FakeClient()
    created = registry.create_identity(client, "u1", name="Coach", instructions_md="v1 text")
    saved = registry.save_instructions(client, "u1", created["id"], "v2 text")
    assert saved["version"] == 2
    versions = {r["version"]: r["is_active"] for r in client.tables["identity_instructions"]}
    assert versions == {1: False, 2: True}
    with pytest.raises(ValueError, match="empty"):
        registry.save_instructions(client, "u1", created["id"], "  ")


def test_list_identities_merges_active_instructions():
    client = FakeClient()
    created = registry.create_identity(client, "u1", name="Coach", instructions_md="v1")
    registry.save_instructions(client, "u1", created["id"], "v2")
    rows = registry.list_identities(client, "u1")
    assert len(rows) == 1
    assert rows[0]["instructions_md"] == "v2"
    assert rows[0]["instructions_version"] == 2
