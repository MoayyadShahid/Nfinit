"""Built meshes for saved revisions, downloaded straight from the backend.

A mesh can be several megabytes, more than the Next.js proxy may return.
The studio therefore asks (through the proxy, as the signed-in user) for a
short-lived signed link, and the browser downloads the GLB directly from
this service. Each project keeps the mesh it last showed; another revision
rebuilds in a fraction of a second on the warm sandbox.
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from execution import SandboxError, build_mesh

from .limits import SandboxUserId, check_sandbox_rate
from .models import RevisionMesh
from .signed_links import read_token, sign_token
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

def sign_mesh_token(
    *, user_id: str, project_id: str, revision_number: int, expires_at: int
) -> str:
    return sign_token(
        "mesh",
        {"u": user_id, "p": project_id, "r": revision_number},
        expires_at=expires_at,
    )


def read_mesh_token(token: str) -> tuple[str, str, int]:
    """Return (user_id, project_id, revision_number) or raise 404/410."""
    payload = read_token("mesh", token, label="Mesh link")
    try:
        return str(payload["u"]), str(payload["p"]), int(payload["r"])
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=404, detail="Mesh link not found.") from error


# Bump when the GLB layout changes, so stored meshes are rebuilt once.
MESH_FORMAT = "nfinit-brep-2"


def code_hash(code: str) -> str:
    """Names a stored mesh: the code it was built from, in the current format."""
    return hashlib.sha256(f"{MESH_FORMAT}\n{code}".encode()).hexdigest()


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
    count_build: bool = False,
) -> StoredMesh:
    """Return the revision's mesh, building and keeping it when needed.

    Mesh storage is a cache: if it fails (for example, before the
    project_meshes migration is applied), the mesh is built and served anyway.
    """
    try:
        revision = store.get_revision(project_id, revision_number, user_id=user_id)
    except (ProjectNotFoundError, RevisionNotFoundError) as error:
        raise HTTPException(status_code=404, detail="Revision not found.") from error
    try:
        stored = store.get_mesh(project_id, user_id=user_id)
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found.") from error
    except Exception:
        logger.warning("Could not read the stored mesh.", exc_info=True)
        stored = None
    if stored is not None and stored.code_hash == code_hash(revision.state.code):
        return stored

    if count_build:
        check_sandbox_rate(user_id)
    mesh = _build(revision.state.code)
    try:
        store.save_mesh(project_id, mesh, user_id=user_id)
    except ProjectNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found.") from error
    except Exception:
        logger.warning("Could not store the mesh; serving it anyway.", exc_info=True)
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
    project_id: str, revision_number: int, store: Store, user_id: SandboxUserId
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
    # A link is reusable until it expires, and alternating two links forces a
    # rebuild each time, so a rebuild here counts against the sandbox limit.
    mesh = ensure_mesh(
        store,
        user_id=user_id,
        project_id=project_id,
        revision_number=revision_number,
        count_build=True,
    )
    return Response(
        content=mesh.glb,
        media_type="model/gltf-binary",
        headers={"Cache-Control": f"private, max-age={LINK_SECONDS}"},
    )
