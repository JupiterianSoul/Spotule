from fastapi import APIRouter

from app.api.v1 import auth, automations, banhammer, imports, me, playlists, stats, tools

api_router = APIRouter(prefix="/api/v1")
for r in (
    auth.router,
    me.router,
    stats.router,
    banhammer.router,
    playlists.router,
    imports.router,
    tools.router,
    automations.router,
):
    api_router.include_router(r)
