"""AC-7: Private events must be protected in both detail and list endpoints."""

import pytest


@pytest.fixture
def alice_private_events(client, login):
    """Confirm Alice's private events exist before testing Bob's access."""
    login("alice")
    response = client.get("/api/events")
    assert response.status_code == 200
    private_events = [
        event for event in response.json()
        if event["owner"] == "alice" and event["private"]
    ]
    assert private_events, "Seed data must include at least one private Alice event."
    login("bob")
    return private_events


def test_ac_7_bob_cannot_get_alices_private_event_by_id(client, alice_private_events):
    """AC-7: Bob gets 404 when requesting Alice's existing private event IDs."""
    for event in alice_private_events:
        response = client.get(f"/api/events/{event['id']}")

        assert response.status_code == 404
        assert response.json() == {"detail": "Event not found."}


def test_ac_7_bobs_event_list_excludes_alices_private_events(client, alice_private_events):
    """AC-7: Alice's private events never appear in Bob's event list."""
    response = client.get("/api/events")

    assert response.status_code == 200
    visible = response.json()
    hidden_ids = {event["id"] for event in alice_private_events}
    assert hidden_ids.isdisjoint(event["id"] for event in visible)
    assert not any(event["owner"] == "alice" and event["private"] for event in visible)
    # Prevent an empty or over-restrictive list from satisfying the privacy check.
    assert any(event["owner"] == "alice" and not event["private"] for event in visible)
    assert any(event["owner"] == "bob" and event["private"] for event in visible)
