"""Built meshes for saved revisions, downloaded straight from the backend.

A mesh can be several megabytes, more than the Next.js proxy may return.
The studio therefore asks (through the proxy, as the signed-in user) for a
short-lived signed link, and the browser downloads the GLB directly from
this service. Each project keeps the mesh it last showed; another revision
rebuilds in a fraction of a second on the warm sandbox.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from execution import SandboxError, build_mesh

from .billing import SubscribedUserId
from .models import RevisionMesh
from .store import (
    ProjectNotFoundError,
    ProjectStoreProtocol,
    RevisionNotFoundError,
    StoredMesh,
    get_project_store,
)

logger = logging.getLogger(__name__)

LINK_SECONDS = 300

router = APIRouter(tags=["meshes"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]

_fallback_secret = secrets.token_bytes(32)
_warned_about_secret = False


def _secret() -> bytes:
    global _warned_about_secret
    configured = os.getenv("NFNIT_MESH_URL_SECRET", "").strip()
    if configured:
        return configured.encode()
    if not _warned_about_secret:
        _warned_about_secret = True
        logger.warning(
            "NFNIT_MESH_URL_SECRET is unset; mesh links use a per-process key "
            "and stop working after a restart or on another replica."
        )
    return _fallback_secret


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _signature(body: str) -> str:
    return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def sign_mesh_token(
    *, user_id: str, project_id: str, revision_number: int, expires_at: int
) -> str:
    body = _encode(
        {"u": user_id, "p": project_id, "r": revision_number, "e": expires_at}
    )
    return f"{body}.{_signature(body)}"


def read_mesh_token(token: str) -> tuple[str, str, int]:
    """Return (user_id, project_id, revision_number) or raise 404."""
    body, _, signature = token.partition(".")
    if not body or not hmac.compare_digest(signature, _signature(body)):
        raise HTTPException(status_code=404, detail="Mesh link not found.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        user_id, project_id = str(payload["u"]), str(payload["p"])
        revision_number, expires_at = int(payload["r"]), int(payload["e"])
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=404, detail="Mesh link not found.") from error
    if expires_at < time.time():
        raise HTTPException(status_code=410, detail="Mesh link has expired.")
    return user_id, project_id, revision_number


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _build(code: str) -> StoredMesh:
    try:
        built = build_mesh(code)
    except SandboxError as error:
        status = 408 if error.kind == "sandbox_timeout" else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
    return StoredMesh(
        code_hash=code_hash(code),
        glb=built.glb,
        inspection=built.inspection.model_dump(mode="json"),
    )


def ensure_mesh(
    store: ProjectStoreProtocol,
    *,
    user_id: str,
    project_id: str,
    revision_number: int,
) -> StoredMesh:
    """Return the revision's mesh, building and keeping it when needed."""
    try:
        revision = store.get_revision(project_id, revision_number, user_id=user_id)
        stored = store.get_mesh(project_id, user_id=user_id)
    except (ProjectNotFoundError, RevisionNotFoundError) as error:
        raise HTTPException(status_code=404, detail="Revision not found.") from error
    if stored is not None and stored.code_hash == code_hash(revision.state.code):
        return stored

    mesh = _build(revision.state.code)
    try:
        store.save_mesh(project_id, mesh, user_id=user_id)
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found.") from error
    return mesh


def store_mesh_for_code(
    store: ProjectStoreProtocol, *, user_id: str, project_id: str, code: str
) -> None:
    """Build and keep a project's mesh ahead of the first view (best effort)."""
    try:
        store.save_mesh(project_id, _build(code), user_id=user_id)
    except Exception:
        logger.warning(
            "Could not pre-build the mesh for project %s; it will build on view.",
            project_id,
            exc_info=True,
        )


@router.get(
    "/projects/{project_id}/revisions/{revision_number}/mesh",
    response_model=RevisionMesh,
)
def get_revision_mesh(
    project_id: str, revision_number: int, store: Store, user_id: SubscribedUserId
):
    mesh = ensure_mesh(
        store,
        user_id=user_id,
        project_id=project_id,
        revision_number=revision_number,
    )
    expires_at = int(time.time()) + LINK_SECONDS
    token = sign_mesh_token(
        user_id=user_id,
        project_id=project_id,
        revision_number=revision_number,
        expires_at=expires_at,
    )
    return RevisionMesh(
        url=f"/meshes/{token}",
        expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
        bytes=len(mesh.glb),
        inspection=mesh.inspection,
    )


@router.get("/meshes/{token}")
def download_mesh(token: str, store: Store):
    user_id, project_id, revision_number = read_mesh_token(token)
    mesh = ensure_mesh(
        store,
        user_id=user_id,
        project_id=project_id,
        revision_number=revision_number,
    )
    return Response(
        content=mesh.glb,
        media_type="model/gltf-binary",
        headers={"Cache-Control": f"private, max-age={LINK_SECONDS}"},
    )
