"""Self-service account deletion.

``DELETE /account`` deletes everything stored for the user.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .auth import get_current_user_id
from .store import ProjectStoreProtocol, get_project_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]
UserId = Annotated[str, Depends(get_current_user_id)]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(store: Store, user_id: UserId):
    try:
        await asyncio.to_thread(store.delete_account, user_id=user_id)
    except Exception as error:
        logger.exception("Could not delete the account of %s.", user_id)
        raise HTTPException(
            status_code=500,
            detail=(
                "Your data could not be deleted. Please contact us and we "
                "will delete it."
            ),
        ) from error
    logger.info("Deleted account %s.", user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
