"""Self-service account deletion.

``DELETE /account`` first cancels the user's Stripe subscription, so nobody
is charged for an account that no longer exists, and then deletes everything
stored for the user. If the cancellation fails, nothing is deleted.
Stripe keeps its own payment and tax records, as the Privacy Policy says.
"""

import asyncio
import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Response, status

from . import billing
from .auth import get_current_user_id
from .store import ProjectStoreProtocol, get_project_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]
UserId = Annotated[str, Depends(get_current_user_id)]

# Stripe statuses after which the subscription can no longer charge anyone.
ENDED_STATUSES = frozenset({"none", "canceled", "incomplete_expired"})


def _cancel_subscription(store: ProjectStoreProtocol, user_id: str) -> None:
    """Cancel every subscription of the user's Stripe customer that can still
    charge. The local record holds only the latest one, and a double checkout
    can have created another."""
    if not billing.billing_enabled():
        return
    record = store.get_subscription(user_id=user_id)
    if record is None:
        return
    client = billing._client()
    subscription_ids = {
        subscription["id"]
        for subscription in client.v1.subscriptions.list(
            params={"customer": record.stripe_customer_id, "status": "all", "limit": 100}
        ).auto_paging_iter()
        if subscription["status"] not in ENDED_STATUSES
    }
    if record.stripe_subscription_id and record.status not in ENDED_STATUSES:
        subscription_ids.add(record.stripe_subscription_id)
    for subscription_id in sorted(subscription_ids):
        try:
            client.v1.subscriptions.cancel(subscription_id)
        except stripe.InvalidRequestError as error:
            if error.code != "resource_missing":
                raise
            # Already gone at Stripe: nothing left to charge.


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(store: Store, user_id: UserId):
    try:
        await asyncio.to_thread(_cancel_subscription, store, user_id)
    except stripe.StripeError as error:
        logger.error("Could not cancel the subscription of %s: %s", user_id, error)
        raise HTTPException(
            status_code=502,
            detail=(
                "Your subscription could not be cancelled, so nothing was "
                "deleted. Please try again, or contact us."
            ),
        ) from error

    try:
        await asyncio.to_thread(store.delete_account, user_id=user_id)
    except Exception as error:
        logger.exception("Could not delete the account of %s.", user_id)
        raise HTTPException(
            status_code=500,
            detail=(
                "Your subscription is cancelled, but your data could not be "
                "deleted. Please contact us and we will delete it."
            ),
        ) from error
    logger.info("Deleted account %s.", user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
