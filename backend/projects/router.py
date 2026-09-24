from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from execution import RevisionComparison, compare_code

from .auth import get_current_user_id
from .models import (
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    ProjectSummary,
    ProjectUpdate,
    RevisionCreate,
)
from .store import (
    ProjectNotFoundError,
    ProjectStoreProtocol,
    RevisionNotFoundError,
    get_project_store,
)

router = APIRouter(prefix="/projects", tags=["projects"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]
UserId = Annotated[str, Depends(get_current_user_id)]


def _not_found(error: LookupError) -> HTTPException:
    resource = "Revision" if isinstance(error, RevisionNotFoundError) else "Project"
    return HTTPException(status_code=404, detail=f"{resource} not found.")


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(request: ProjectCreate, store: Store, user_id: UserId):
    return store.create_project(request, user_id=user_id)


@router.get("", response_model=list[ProjectSummary])
def list_projects(
    store: Store,
    user_id: UserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return store.list_projects(user_id=user_id, limit=limit, offset=offset)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, store: Store, user_id: UserId):
    try:
        return store.get_project(project_id, user_id=user_id)
    except ProjectNotFoundError as error:
        raise _not_found(error) from error


@router.patch("/{project_id}", response_model=ProjectDetail)
def rename_project(
    project_id: str, request: ProjectUpdate, store: Store, user_id: UserId
):
    try:
        return store.rename_project(project_id, request.name, user_id=user_id)
    except ProjectNotFoundError as error:
        raise _not_found(error) from error


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, store: Store, user_id: UserId):
    try:
        store.delete_project(project_id, user_id=user_id)
    except ProjectNotFoundError as error:
        raise _not_found(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/revisions",
    response_model=ProjectRevision,
    status_code=status.HTTP_201_CREATED,
)
def create_revision(
    project_id: str, request: RevisionCreate, store: Store, user_id: UserId
):
    try:
        return store.add_revision(project_id, request.state, user_id=user_id)
    except ProjectNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{project_id}/revisions", response_model=list[ProjectRevision])
def list_revisions(
    project_id: str,
    store: Store,
    user_id: UserId,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        return store.list_revisions(
            project_id, user_id=user_id, limit=limit, offset=offset
        )
    except ProjectNotFoundError as error:
        raise _not_found(error) from error


@router.get(
    "/{project_id}/compare",
    response_model=RevisionComparison,
)
def compare_revisions(
    project_id: str,
    previous_revision: Annotated[int, Query(alias="previousRevision", ge=1)],
    current_revision: Annotated[int, Query(alias="currentRevision", ge=1)],
    store: Store,
    user_id: UserId,
):
    try:
        previous = store.get_revision(
            project_id, previous_revision, user_id=user_id
        )
        current = store.get_revision(
            project_id, current_revision, user_id=user_id
        )
    except (ProjectNotFoundError, RevisionNotFoundError) as error:
        raise _not_found(error) from error
    previous_face_id = (
        previous.state.selection.entity_id
        if previous.state.selection is not None
        else None
    )
    return compare_code(
        previous.state.code,
        current.state.code,
        previous_face_id=previous_face_id,
    )


@router.get(
    "/{project_id}/revisions/{revision_number}",
    response_model=ProjectRevision,
)
def get_revision(
    project_id: str,
    revision_number: Annotated[int, Path(ge=1)],
    store: Store,
    user_id: UserId,
):
    try:
        return store.get_revision(project_id, revision_number, user_id=user_id)
    except (ProjectNotFoundError, RevisionNotFoundError) as error:
        raise _not_found(error) from error
