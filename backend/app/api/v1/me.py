from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.models import SpotifyCredential, UserPreference
from app.schemas.user import MeOut, PreferencesOut, PreferencesUpdate, UserOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(user: CurrentUser, db: DB):
    pref = await db.get(UserPreference, user.id) or UserPreference(user_id=user.id)
    cred = await db.get(SpotifyCredential, user.id)
    return MeOut(
        user=UserOut(
            id=str(user.id),
            spotify_id=user.spotify_id,
            display_name=user.display_name,
            email=user.email,
            avatar_url=user.avatar_url,
            country=user.country,
            product=user.product,
            role=user.role.value,
        ),
        preferences=PreferencesOut.model_validate(pref),
        spotify_linked=bool(cred and not cred.revoked_at),
        scopes=(cred.scopes.split() if cred else []),
    )


@router.patch("/preferences", response_model=PreferencesOut)
async def update_preferences(user: CurrentUser, db: DB, body: PreferencesUpdate):
    pref = await db.get(UserPreference, user.id)
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "settings":
            pref.settings = {**pref.settings, **v}
        else:
            setattr(pref, k, v)
    await db.commit()
    return PreferencesOut.model_validate(pref)


@router.delete("", status_code=204)
async def delete_account(user: CurrentUser, db: DB):
    """GDPR: wipes tokens, streams, everything (ON DELETE CASCADE)."""
    await db.delete(user)
    await db.commit()
