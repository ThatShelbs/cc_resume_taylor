"""The project trash: list deleted projects and restore one."""

from fastapi import APIRouter

from ..context import Ctx

router = APIRouter(prefix="/api/trash", tags=["projects"])


@router.get("")
def trash(ctx: Ctx):
    return ctx.store.list_trash()


@router.post("/{tid}/restore")
def restore(ctx: Ctx, tid: str):
    return ctx.project_summary(ctx.store.restore(tid), ctx.current_hashes())
