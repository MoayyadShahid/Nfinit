import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
import stripe
from fastapi.testclient import TestClient

import main
from projects import billing
from projects.auth import CurrentUser, get_current_user, get_current_user_id
from projects.models import SubscriptionRecord
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
WEBHOOK_SECRET = "whsec_test"


class FakeStripe:
    """The slice of StripeClient that billing uses, recording each call."""

    def __init__(self):
        self.subscriptions_by_id: dict[str, dict] = {}
        self.customers_created: list[dict] = []
        self.checkout_params: list[dict] = []
        self.portal_params: list[dict] = []
        real = stripe.StripeClient("sk_test_fake")
        self.construct_event = real.construct_event
        self.v1 = SimpleNamespace(
            customers=SimpleNamespace(create=self._create_customer),
            checkout=SimpleNamespace(
                sessions=SimpleNamespace(create=self._create_checkout)
            ),
            billing_portal=SimpleNamespace(
                sessions=SimpleNamespace(create=self._create_portal)
            ),
            subscriptions=SimpleNamespace(retrieve=self._retrieve_subscription),
        )

    def _create_customer(self, params, options=None):
        self.customers_created.append(params)
        return SimpleNamespace(id=f"cus_{len(self.customers_created)}")

    def _create_checkout(self, params):
        self.checkout_params.append(params)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    def _create_portal(self, params):
        self.portal_params.append(params)
        return SimpleNamespace(url="https://billing.stripe.test/portal")

    def _retrieve_subscription(self, subscription_id):
        return stripe.Subscription.construct_from(
            self.subscriptions_by_id[subscription_id], "sk_test_fake"
        )

    def add_subscription(self, subscription_id, status, *, user_id=USER_ID):
        self.subscriptions_by_id[subscription_id] = {
            "id": subscription_id,
            "object": "subscription",
            "customer": "cus_1",
            "status": status,
            "cancel_at_period_end": False,
            "metadata": {"user_id": user_id} if user_id else {},
            "items": {
                "object": "list",
                "data": [
                    {
                        "object": "subscription_item",
                        "id": "si_1",
                        "current_period_end": 1_900_000_000,
                    }
                ],
            },
        }


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def fake_stripe(monkeypatch):
    fake = FakeStripe()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_monthly")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("APP_URL", "https://nfinit.dev/")
    monkeypatch.setattr(billing, "_client", lambda: fake)
    return fake


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        USER_ID, "maker@example.com"
    )
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def subscribe(store, status="active", subscription_id="sub_1"):
    store.save_subscription(
        SubscriptionRecord(
            stripe_customer_id="cus_1",
            stripe_subscription_id=subscription_id,
            status=status,
        ),
        user_id=USER_ID,
    )


def send_webhook(client, event_type, data_object):
    payload = json.dumps(
        {
            "id": "evt_1",
            "object": "event",
            "type": event_type,
            "data": {"object": data_object},
        }
    )
    timestamp = int(time.time())
    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        f"{timestamp}.{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        "/billing/webhook",
        content=payload,
        headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
    )


def start_run(client):
    return client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "user", "content": "Make a cube"}],
            "modelId": "anthropic/claude-opus-5",
        },
    )


def test_billing_disabled_lets_everyone_generate(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    status = client.get("/billing/status").json()
    assert status == {
        "enabled": False,
        "active": True,
        "status": "billing_disabled",
        "currentPeriodEnd": None,
        "cancelAtPeriodEnd": False,
    }
    assert billing.require_subscription(None, USER_ID) == USER_ID


def test_unsubscribed_user_cannot_generate_or_export(client, fake_stripe):
    response = start_run(client)
    assert response.status_code == 402
    assert response.json()["detail"] == billing.SUBSCRIPTION_REQUIRED

    for path, body in (
        ("/export-model", {"code": "result = Box(1, 1, 1)", "format": "stl"}),
        ("/generate-mesh", {"code": "result = Box(1, 1, 1)"}),
        ("/inspect-model", {"code": "result = Box(1, 1, 1)"}),
        ("/analyze-model", {"code": "result = Box(1, 1, 1)"}),
    ):
        response = client.post(path, json=body)
        assert response.status_code == 402, path
    assert client.get("/billing/status").json()["active"] is False


def test_canceled_subscription_loses_access(client, store, fake_stripe):
    subscribe(store, status="canceled")
    assert start_run(client).status_code == 402


def test_active_subscription_can_start_a_run(client, store, fake_stripe, monkeypatch):
    async def never_finishes(*_args, **_kwargs):
        raise RuntimeError("not under test")

    monkeypatch.setattr("projects.runs.run_cad_agent", never_finishes)
    subscribe(store, status="past_due")
    assert start_run(client).status_code == 202


def test_checkout_creates_one_customer_and_returns_to_the_studio(
    client, store, fake_stripe
):
    for _ in range(2):
        response = client.post(
            "/billing/checkout", json={"returnPath": "/studio?demo=gear"}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"url": "https://checkout.stripe.test/session"}

    assert fake_stripe.customers_created == [
        {"metadata": {"user_id": USER_ID}, "email": "maker@example.com"}
    ]
    params = fake_stripe.checkout_params[-1]
    assert params["customer"] == "cus_1"
    assert params["client_reference_id"] == USER_ID
    assert params["subscription_data"] == {"metadata": {"user_id": USER_ID}}
    assert params["line_items"] == [{"price": "price_monthly", "quantity": 1}]
    assert params["success_url"] == (
        "https://nfinit.dev/studio?demo=gear&checkout=success"
    )
    assert params["cancel_url"] == "https://nfinit.dev/studio?demo=gear&checkout=cancel"
    assert store.get_subscription(user_id=USER_ID).status == "none"


def test_checkout_rejects_subscribed_users_and_foreign_return_paths(
    client, store, fake_stripe
):
    response = client.post("/billing/checkout", json={"returnPath": "//evil.test"})
    assert response.status_code == 422

    subscribe(store)
    response = client.post("/billing/checkout", json={})
    assert response.status_code == 409
    assert fake_stripe.checkout_params == []


def test_portal_needs_a_billing_account(client, store, fake_stripe):
    assert client.post("/billing/portal", json={}).status_code == 404

    subscribe(store)
    response = client.post("/billing/portal", json={"returnPath": "/parts"})
    assert response.json() == {"url": "https://billing.stripe.test/portal"}
    assert fake_stripe.portal_params == [
        {"customer": "cus_1", "return_url": "https://nfinit.dev/parts"}
    ]


def test_webhook_rejects_a_bad_signature(client, fake_stripe):
    response = client.post(
        "/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=nope"},
    )
    assert response.status_code == 400


def test_completed_checkout_activates_the_subscription(client, store, fake_stripe):
    fake_stripe.add_subscription("sub_1", "active")

    response = send_webhook(
        client,
        "checkout.session.completed",
        {
            "id": "cs_1",
            "object": "checkout.session",
            "mode": "subscription",
            "subscription": "sub_1",
        },
    )

    assert response.status_code == 200, response.text
    record = store.get_subscription(user_id=USER_ID)
    assert record.active
    assert record.stripe_subscription_id == "sub_1"
    assert record.current_period_end.year == 2030
    status = client.get("/billing/status").json()
    assert status["active"] is True
    assert status["currentPeriodEnd"].startswith("2030-03-17")


def test_subscription_events_use_the_current_state_from_stripe(
    client, store, fake_stripe
):
    subscribe(store)
    # The event body is stale; Stripe now says the subscription ended.
    fake_stripe.add_subscription("sub_1", "canceled")

    send_webhook(
        client,
        "customer.subscription.updated",
        {"id": "sub_1", "object": "subscription", "status": "active"},
    )

    assert store.get_subscription(user_id=USER_ID).status == "canceled"


def test_late_event_for_an_old_subscription_keeps_the_current_one(
    client, store, fake_stripe
):
    subscribe(store, subscription_id="sub_new")
    fake_stripe.add_subscription("sub_old", "canceled")

    send_webhook(
        client,
        "customer.subscription.deleted",
        {"id": "sub_old", "object": "subscription"},
    )

    record = store.get_subscription(user_id=USER_ID)
    assert record.stripe_subscription_id == "sub_new"
    assert record.active


def test_subscription_without_a_user_is_ignored(client, store, fake_stripe):
    fake_stripe.add_subscription("sub_manual", "active", user_id=None)

    response = send_webhook(
        client,
        "customer.subscription.created",
        {"id": "sub_manual", "object": "subscription"},
    )

    assert response.status_code == 200
    assert store.get_subscription(user_id=USER_ID) is None
