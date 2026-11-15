"""Read-only campaign views; operator mutations use the local campaign CLI."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Engine, select

from coldguard_backend.campaign_integrity import live_integrity, run_closures
from coldguard_backend.campaign_store import CampaignNotFound, get_campaign
from coldguard_backend.experiment_store import RunConflict


def campaign_router(get_engine) -> APIRouter:
    router = APIRouter()

    @router.get("/api/campaigns/{campaign_id}")
    def read_campaign(campaign_id: str, engine: Engine = Depends(get_engine)) -> dict:
        try:
            with engine.connect() as connection:
                return get_campaign(connection, campaign_id)
        except CampaignNotFound as exc:
            raise HTTPException(status_code=404, detail="Campaign not found") from exc

    @router.get("/api/campaigns/{campaign_id}/integrity")
    def read_integrity(campaign_id: str, request: Request, engine: Engine = Depends(get_engine)) -> dict:
        consumer = request.app.state.mqtt_consumer
        try:
            return live_integrity(engine, campaign_id, ingestion=consumer.snapshot() if consumer else None)
        except CampaignNotFound as exc:
            raise HTTPException(status_code=404, detail="Campaign not found") from exc
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/campaigns/{campaign_id}/closures")
    def read_closures(campaign_id: str, limit: int = 100, offset: int = 0, engine: Engine = Depends(get_engine)) -> dict:
        if not 1 <= limit <= 500 or offset < 0:
            raise HTTPException(status_code=422, detail="limit must be 1..500 and offset non-negative")
        try:
            with engine.connect() as connection:
                get_campaign(connection, campaign_id)
                rows = [dict(row) for row in connection.execute(select(run_closures).where(
                    run_closures.c.campaign_id == campaign_id,
                ).order_by(run_closures.c.recorded_at, run_closures.c.closure_id).limit(limit + 1).offset(offset)).mappings()]
            return {"items": rows[:limit], "next_offset": offset + limit if len(rows) > limit else None}
        except CampaignNotFound as exc:
            raise HTTPException(status_code=404, detail="Campaign not found") from exc

    return router
