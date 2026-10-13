"""Stripe subscription billing.

Stripe is the source of truth: the webhook mirrors each subscription into the
store, and `require_subscription` gates every endpoint that spends model
tokens or sandbox time. Without STRIPE_SECRET_KEY billing is off and everyone
has access, so a deploy before Stripe is set up does not lock users out.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import CurrentUser, get_current_user, get_current_user_id
from .models import SubscriptionRecord
from .store import ProjectStoreProtocol, get_project_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]
UserId = Annotated[str, Depends(get_current_user_id)]
User = Annotated[CurrentUser, Depends(get_current_user)]

# The frontend matches on this detail to open the paywall.
SUBSCRIPTION_REQUIRED = "subscription_required"

SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


def billing_enabled() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def _setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=503, detail=f"{name} is not configured on the backend."
        )
    return value


def _client() -> stripe.StripeClient:
    return stripe.StripeClient(_setting("STRIPE_SECRET_KEY"))


def require_subscription(store: Store, user_id: UserId) -> str:
    """The signed-in user's id, if they may generate, preview or export."""
    if not billing_enabled():
        return user_id
    record = store.get_subscription(user_id=user_id)
    if record is None or not record.active:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=SUBSCRIPTION_REQUIRED,
        )
    return user_id


SubscribedUserId = Annotated[str, Depends(require_subscription)]


class BillingStatus(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    enabled: bool
    active: bool
    status: str
    current_period_end: datetime | None = Field(
        default=None, serialization_alias="currentPeriodEnd"
    )
    cancel_at_period_end: bool = Field(
        default=False, serialization_alias="cancelAtPeriodEnd"
    )


class ReturnTo(BaseModel):
    """Where Stripe sends the user back to, as a path on the app."""

    model_config = ConfigDict(populate_by_name=True)

    return_path: str = Field(default="/studio", alias="returnPath", max_length=500)

    @field_validator("return_path")
    @classmethod
    def same_site(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "\\" in value:
            raise ValueError("returnPath must be a path on this site.")
        return value

    def url(self, **query: str) -> str:
        app_url = _setting("APP_URL").rstrip("/")
        if not query:
            return f"{app_url}{self.return_path}"
        separator = "&" if "?" in self.return_path else "?"
        params = "&".join(f"{key}={value}" for key, value in query.items())
        return f"{app_url}{self.return_path}{separator}{params}"


class RedirectUrl(BaseModel):
    url: str


def _stripe_failed(error: stripe.StripeError) -> HTTPException:
    logger.error("Stripe request failed: %s", error)
    return HTTPException(
        status_code=502,
        detail=error.user_message or "Could not reach the payment provider.",
    )


def _record_of(subscription: dict[str, Any]) -> SubscriptionRecord:
    # Since API version 2025-03-31 the billing period lives on each item.
    items = subscription.get("items", {}).get("data") or []
    period_end = items[0].get("current_period_end") if items else None
    period_end = period_end or subscription.get("current_period_end")
    customer = subscription["customer"]
    return SubscriptionRecord(
        stripe_customer_id=customer if isinstance(customer, str) else customer["id"],
        stripe_subscription_id=subscription["id"],
        status=subscription["status"],
        current_period_end=(
            datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
        ),
        cancel_at_period_end=bool(
            subscription.get("cancel_at_period_end") or subscription.get("cancel_at")
        ),
    )


def _sync_subscription(
    client: stripe.StripeClient, store: ProjectStoreProtocol, subscription_id: str
) -> None:
    # Re-read instead of trusting the event body: events can arrive out of
    # order, and the fresh object is always the current state.
    subscription = client.v1.subscriptions.retrieve(subscription_id).to_dict()
    user_id = (subscription.get("metadata") or {}).get("user_id")
    if not user_id:
        logger.warning(
            "Subscription %s has no user_id metadata; it was not created by "
            "Checkout, so it is not linked to a user.",
            subscription_id,
        )
        return
    record = _record_of(subscription)
    current = store.get_subscription(user_id=user_id)
    if (
        current is not None
        and current.active
        and current.stripe_subscription_id not in (None, record.stripe_subscription_id)
        and not record.active
    ):
        # A late event for an old, ended subscription must not cancel the
        # user's current one.
        logger.info(
            "Ignoring %s (%s): user %s has active %s.",
            subscription_id,
            record.status,
            user_id,
            current.stripe_subscription_id,
        )
        return
    store.save_subscription(record, user_id=user_id)


@router.get("/status", response_model=BillingStatus)
def billing_status(store: Store, user_id: UserId):
    if not billing_enabled():
        return BillingStatus(enabled=False, active=True, status="billing_disabled")
    record = store.get_subscription(user_id=user_id)
    if record is None:
        return BillingStatus(enabled=True, active=False, status="none")
    return BillingStatus(
        enabled=True,
        active=record.active,
        status=record.status,
        current_period_end=record.current_period_end,
        cancel_at_period_end=record.cancel_at_period_end,
    )


@router.post("/checkout", response_model=RedirectUrl)
def start_checkout(request: ReturnTo, store: Store, user: User):
    client = _client()
    price_id = _setting("STRIPE_PRICE_ID")
    record = store.get_subscription(user_id=user.id)
    if record is not None and record.active:
        raise HTTPException(status_code=409, detail="already_subscribed")

    try:
        if record is None:
            customer_params: dict[str, Any] = {"metadata": {"user_id": user.id}}
            if user.email:
                customer_params["email"] = user.email
            customer = client.v1.customers.create(
                params=customer_params,
                # A double click must not create two Stripe customers.
                options={"idempotency_key": f"nfinit-customer-{user.id}"},
            )
            record = SubscriptionRecord(stripe_customer_id=customer.id)
            store.save_subscription(record, user_id=user.id)

        session = client.v1.checkout.sessions.create(
            params={
                "mode": "subscription",
                "customer": record.stripe_customer_id,
                "client_reference_id": user.id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "subscription_data": {"metadata": {"user_id": user.id}},
                "allow_promotion_codes": True,
                # Auto-renewal laws require the renewal and cancellation terms
                # next to the button that starts the subscription.
                "custom_text": {
                    "submit": {
                        "message": (
                            "Your subscription renews every month until you "
                            "cancel. Cancel anytime with the Billing button in "
                            "the Nfinit studio. By subscribing, you agree to the "
                            "Terms "
                            f"of Service: {_setting('APP_URL').rstrip('/')}/terms"
                        )
                    }
                },
                "success_url": request.url(checkout="success"),
                "cancel_url": request.url(checkout="cancel"),
            }
        )
    except stripe.StripeError as error:
        raise _stripe_failed(error) from error
    return RedirectUrl(url=session.url)


@router.post("/portal", response_model=RedirectUrl)
def open_portal(request: ReturnTo, store: Store, user_id: UserId):
    client = _client()
    record = store.get_subscription(user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No billing account yet.")
    try:
        session = client.v1.billing_portal.sessions.create(
            params={"customer": record.stripe_customer_id, "return_url": request.url()}
        )
    except stripe.StripeError as error:
        raise _stripe_failed(error) from error
    return RedirectUrl(url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, store: Store):
    payload = await request.body()
    client = _client()
    try:
        event = client.construct_event(
            payload,
            request.headers.get("stripe-signature"),
            _setting("STRIPE_WEBHOOK_SECRET"),
        )
    except (ValueError, stripe.SignatureVerificationError) as error:
        raise HTTPException(
            status_code=400, detail="Invalid Stripe webhook signature."
        ) from error

    data = event.data.object.to_dict()
    if event.type == "checkout.session.completed":
        if data.get("mode") != "subscription" or not data.get("subscription"):
            return {"received": True}
        subscription = data["subscription"]
        subscription_id = (
            subscription if isinstance(subscription, str) else subscription["id"]
        )
    elif event.type in SUBSCRIPTION_EVENTS:
        subscription_id = data["id"]
    else:
        return {"received": True}

    try:
        await asyncio.to_thread(_sync_subscription, client, store, subscription_id)
    except stripe.StripeError as error:
        # A non-2xx makes Stripe retry the event later.
        raise _stripe_failed(error) from error
    return {"received": True}
