from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.modules.arbitrage.execution import ExecutionLeg
from app.modules.arbitrage.execution.service import execution_service


router = APIRouter(
    prefix="/execution",
    tags=["execution"],
)


class OpenSessionRequest(BaseModel):
    bookmaker: str = Field(min_length=1)
    headless: bool = False
    replace: bool = False


class LoginCheckRequest(BaseModel):
    bookmaker: str = Field(min_length=1)


class ResetSessionRequest(BaseModel):
    bookmaker: str = Field(min_length=1)
    reopen_home: bool = True


class CloseSessionRequest(BaseModel):
    bookmaker: str = Field(min_length=1)


class PrepareLegRequest(BaseModel):
    bookmaker: str = Field(min_length=1)
    event_name: str = Field(min_length=1)
    selection_name: str = Field(min_length=1)
    stake: float = Field(gt=0)

    market_name: str = "Win"
    event_url: str | None = None
    decimal_odds: float | None = Field(
        default=None,
        gt=1.0,
    )
    race_time: str | None = None
    course: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


@router.get("/health")
def execution_health():
    try:
        return execution_service.health()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post("/session/open")
def open_execution_session(
    payload: OpenSessionRequest,
):
    try:
        return execution_service.open_session(
            payload.bookmaker,
            headless=payload.headless,
            replace=payload.replace,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post("/session/login-check")
def check_execution_login(
    payload: LoginCheckRequest,
):
    try:
        return execution_service.login_check(
            payload.bookmaker
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post("/prepare")
def prepare_execution_leg(
    payload: PrepareLegRequest,
):
    leg = ExecutionLeg(
        bookmaker=payload.bookmaker,
        event_name=payload.event_name,
        selection_name=payload.selection_name,
        stake=payload.stake,
        market_name=payload.market_name,
        event_url=payload.event_url,
        decimal_odds=payload.decimal_odds,
        race_time=payload.race_time,
        course=payload.course,
        metadata=payload.metadata,
    )

    try:
        result = execution_service.prepare_leg(
            leg
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    if not result.get("successful"):
        raise HTTPException(
            status_code=409,
            detail=result,
        )

    return result


@router.post("/session/reset")
def reset_execution_session(
    payload: ResetSessionRequest,
):
    try:
        return execution_service.reset_session(
            payload.bookmaker,
            reopen_home=payload.reopen_home,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post("/session/close")
def close_execution_session(
    payload: CloseSessionRequest,
):
    try:
        return execution_service.close_session(
            payload.bookmaker
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc