from types import SimpleNamespace

import pytest
import stripe
from fastapi.testclient import TestClient

import main
from projects import billing
from projects.auth import get_current_user_id
from projects.models import CadRunResult, ProjectCreate, ProjectState, SubscriptionRecord
from projects.store import ProjectStore, StoredMesh, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def client(store):
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


@pytest.fixture
def fake_stripe(monkeypatch):
    """Billing on, with a Stripe client whose cancel each test sets."""
    fake = SimpleNamespace(
        v1=SimpleNamespace(subscriptions=SimpleNamespace()), at_stripe=[]
    )
    fake.v1.subscriptions.list = lambda params: SimpleNamespace(
        auto_paging_iter=lambda: iter(fake.at_stripe)
    )
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(billing, "_client", lambda: fake)
    return fake


def subscribe(store, status="active", subscription_id="sub_1"):
    store.save_subscription(
        SubscriptionRecord(
            stripe_customer_id="cus_1",
            stripe_subscription_id=subscription_id,
            status=status,
        ),
        user_id=USER_ID,
    )


def fill(store, user_id):
    project = store.create_project(
        ProjectCreate(name="Bracket", state=ProjectState(code="result = Box(1, 1, 1)")),
        user_id=user_id,
    )
    store.add_revision(
        project.id, ProjectState(code="result = Box(2, 1, 1)"), user_id=user_id
    )
    store.set_thumbnail(project.id, b"webp", "image/webp", user_id=user_id)
    store.save_mesh(
        project.id,
        StoredMesh(code_hash="h", glb=b"glTF", inspection={"valid": True}),
        user_id=user_id,
    )
    run = store.create_run(
        f"run-{user_id[-2:]}",
        user_id=user_id,
        project_id=project.id,
        prompt="A bracket",
        model_id="anthropic/claude-sonnet-5.5",
    )
    store.finish_run(
        run.id,
        user_id=user_id,
        status="succeeded",
        result=CadRunResult(code="result = Box(2, 1, 1)"),
        error=None,
        project_id=project.id,
    )
    return project.id, run.id


def everything_of(store, user_id):
    with store._connect() as connection:
        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            for table in ("projects", "cad_runs", "project_meshes", "subscriptions")
        }


def test_deleting_the_account_removes_all_data_and_cancels_billing(
    client, store, fake_stripe
):
    cancelled = []
    fake_stripe.v1.subscriptions.cancel = lambda sub_id: cancelled.append(sub_id)
    fill(store, USER_ID)
    other_project, _ = fill(store, OTHER_USER_ID)
    subscribe(store, status="active")

    response = client.delete("/account")

    assert response.status_code == 204
    assert cancelled == ["sub_1"]
    assert everything_of(store, USER_ID) == {
        "projects": 0,
        "cad_runs": 0,
        "project_meshes": 0,
        "subscriptions": 0,
    }
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM project_revisions").fetchone()[
            0
        ] == 2  # only the other user's two revisions remain
    # Nobody else is touched.
    assert store.get_project(other_project, user_id=OTHER_USER_ID).name == "Bracket"


def test_failed_cancellation_deletes_nothing(client, store, fake_stripe):
    def refuse(_sub_id):
        raise stripe.APIConnectionError("Stripe is unreachable")

    fake_stripe.v1.subscriptions.cancel = refuse
    fill(store, USER_ID)
    subscribe(store, status="active")

    response = client.delete("/account")

    assert response.status_code == 502
    assert "nothing was deleted" in response.json()["detail"]
    assert everything_of(store, USER_ID)["projects"] == 1


def test_subscription_already_gone_at_stripe_still_deletes(client, store, fake_stripe):
    def missing(_sub_id):
        raise stripe.InvalidRequestError(
            "No such subscription", "id", code="resource_missing"
        )

    fake_stripe.v1.subscriptions.cancel = missing
    fill(store, USER_ID)
    subscribe(store, status="active")

    assert client.delete("/account").status_code == 204
    assert everything_of(store, USER_ID)["projects"] == 0


@pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
def test_ended_subscription_is_not_cancelled_again(client, store, fake_stripe, status):
    def forbidden(_sub_id):
        raise AssertionError("an ended subscription must not be cancelled")

    fake_stripe.v1.subscriptions.cancel = forbidden
    subscribe(store, status=status)

    assert client.delete("/account").status_code == 204
    assert store.get_subscription(user_id=USER_ID) is None


def test_deletion_works_without_billing(client, store):
    fill(store, USER_ID)

    assert client.delete("/account").status_code == 204
    assert everything_of(store, USER_ID)["projects"] == 0


def test_every_active_subscription_at_stripe_is_cancelled(client, store, fake_stripe):
    cancelled = []
    fake_stripe.v1.subscriptions.cancel = lambda sub_id: cancelled.append(sub_id)
    # A double checkout left a second subscription the local record does not know.
    fake_stripe.at_stripe = [
        {"id": "sub_1", "status": "active"},
        {"id": "sub_2", "status": "active"},
        {"id": "sub_old", "status": "canceled"},
    ]
    subscribe(store, status="active")

    assert client.delete("/account").status_code == 204
    assert cancelled == ["sub_1", "sub_2"]
