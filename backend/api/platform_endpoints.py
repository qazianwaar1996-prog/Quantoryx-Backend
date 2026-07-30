# backend/api/platform_endpoints.py
"""
Quantoryx — Platform Feature API Endpoints Router Module (v6.0).

Exposes REST routes for the alerting engine, trade journal, live signal feed,
market watch pricing, subscription billing, the visual strategy builder, and
in-app help content. Completes the surface consumed by the v6 frontend.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_db
from backend.schemas.api_schemas import (
    AlertCreateRequest,
    AlertResponse,
    AlertToggleRequest,
    BuilderBlockGroup,
    BuilderSaveRequest,
    DocResponse,
    FaqResponse,
    InvoiceResponse,
    JournalCreateRequest,
    JournalResponse,
    PlanResponse,
    SignalResponse,
    SubscribeRequest,
    TickerResponse,
    UsageResponse,
)
from backend.services.platform_services import (
    HELP_DOCS,
    HELP_FAQ,
    SUBSCRIPTION_PLANS,
    AlertService,
    BillingService,
    BuilderService,
    JournalService,
    SignalService,
)
from utils.logging_config import get_logger

logger = get_logger("backend.api.platform_endpoints")

router = APIRouter(prefix="/api", tags=["Alerts, Journal, Signals, Billing & Builder"])


# =====================================================================
# ALERT ENGINE ENDPOINTS
# =====================================================================

@router.get(
    "/alerts",
    response_model=List[AlertResponse],
    status_code=status.HTTP_200_OK,
    summary="List Alerts",
    description="Returns every market condition alert configured by the current user."
)
async def get_alerts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    AlertService.seed_defaults(user_id=current_user["id"], db=db)
    rows = AlertService.list_alerts(user_id=current_user["id"], db=db)
    return [AlertResponse.from_orm_model(a) for a in rows]


@router.post(
    "/alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Alert",
    description="Registers a new market condition alert for the current user."
)
async def create_alert(
    payload: AlertCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        alert = AlertService.create_alert(user_id=current_user["id"], payload=payload.model_dump(), db=db)
        return AlertResponse.from_orm_model(alert)
    except Exception as e:
        logger.error("Alert creation failed: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the alert."
        )


@router.patch(
    "/alerts/{alert_id}",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Arm Or Pause Alert",
    description="Toggles the armed state of an existing alert."
)
async def toggle_alert(
    alert_id: int,
    payload: AlertToggleRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alert = AlertService.set_active(
        user_id=current_user["id"], alert_id=alert_id, is_active=payload.on, db=db
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert record not found.")
    return AlertResponse.from_orm_model(alert)


@router.delete(
    "/alerts/{alert_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Alert",
    description="Permanently removes an alert owned by the current user."
)
async def delete_alert(
    alert_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not AlertService.delete_alert(user_id=current_user["id"], alert_id=alert_id, db=db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert record not found.")
    return {"status": "SUCCESS", "message": "Alert deleted."}


# =====================================================================
# TRADE JOURNAL ENDPOINTS
# =====================================================================

@router.get(
    "/journal",
    response_model=List[JournalResponse],
    status_code=status.HTTP_200_OK,
    summary="List Journal Entries",
    description="Returns all trade journal reflections authored by the current user."
)
async def get_journal(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = JournalService.list_entries(user_id=current_user["id"], db=db)
    return [JournalResponse.from_orm_model(e) for e in rows]


@router.post(
    "/journal",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Journal Entry",
    description="Logs a trade with its realised P&L, execution grade, tags, and reflection."
)
async def create_journal_entry(
    payload: JournalCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = JournalService.create_entry(user_id=current_user["id"], payload=payload.model_dump(), db=db)
    return JournalResponse.from_orm_model(entry)


@router.delete(
    "/journal/{entry_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Journal Entry",
    description="Permanently removes a journal entry owned by the current user."
)
async def delete_journal_entry(
    entry_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not JournalService.delete_entry(user_id=current_user["id"], entry_id=entry_id, db=db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found.")
    return {"status": "SUCCESS", "message": "Journal entry deleted."}


# =====================================================================
# LIVE SIGNAL & MARKET WATCH ENDPOINTS
# =====================================================================

@router.get(
    "/signals",
    response_model=List[SignalResponse],
    status_code=status.HTTP_200_OK,
    summary="List Live Signals",
    description="Returns recent entry signals generated for the current user."
)
async def get_signals(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = SignalService.list_signals(user_id=current_user["id"], db=db)
    return [SignalResponse.from_orm_model(s) for s in rows]


@router.get(
    "/market/tickers",
    response_model=List[TickerResponse],
    status_code=status.HTTP_200_OK,
    summary="Market Watch Quotes",
    description="Latest close and session change for every supported instrument."
)
async def get_tickers(current_user: dict = Depends(get_current_user)):
    return SignalService.market_tickers()


# =====================================================================
# BILLING & SUBSCRIPTION ENDPOINTS
# =====================================================================

@router.get(
    "/billing/plans",
    response_model=List[PlanResponse],
    status_code=status.HTTP_200_OK,
    summary="List Subscription Plans",
    description="Returns every purchasable subscription tier with its feature matrix."
)
async def get_plans():
    return SUBSCRIPTION_PLANS


@router.get(
    "/billing/invoices",
    response_model=List[InvoiceResponse],
    status_code=status.HTTP_200_OK,
    summary="List Invoices",
    description="Returns issued billing statements for the current user."
)
async def get_invoices(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invoices = BillingService.list_invoices(user_id=current_user["id"], db=db)
    return [
        InvoiceResponse(
            id=inv.reference,
            date=inv.issued_at.strftime("%b %d, %Y") if inv.issued_at else "",
            amt=inv.amount,
            status=inv.invoice_status,
            plan=inv.plan_label,
        )
        for inv in invoices
    ]


@router.get(
    "/billing/usage",
    response_model=List[UsageResponse],
    status_code=status.HTTP_200_OK,
    summary="Quota Consumption",
    description="Returns quota usage for the active billing cycle."
)
async def get_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return BillingService.usage(user_id=current_user["id"], db=db)


@router.post(
    "/billing/subscribe",
    status_code=status.HTTP_200_OK,
    summary="Change Subscription Plan",
    description="Switches the current user onto the requested plan and issues an invoice."
)
async def subscribe(
    payload: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    valid = {p["id"] for p in SUBSCRIPTION_PLANS}
    if payload.planId not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown plan identifier. Expected one of: {', '.join(sorted(valid))}."
        )
    sub = BillingService.subscribe(
        user_id=current_user["id"], plan_id=payload.planId, cycle=payload.cycle or "mo", db=db
    )
    return {
        "status": "SUCCESS",
        "plan": sub.plan_id,
        "cycle": sub.billing_cycle,
        "renews_at": sub.renews_at,
    }


# =====================================================================
# STRATEGY BUILDER ENDPOINTS
# =====================================================================

@router.get(
    "/builder/blocks",
    response_model=List[BuilderBlockGroup],
    status_code=status.HTTP_200_OK,
    summary="Builder Block Palette",
    description="Returns the indicator, condition, risk, and action blocks available to the builder."
)
async def get_builder_blocks():
    return BuilderService.blocks()


@router.post(
    "/builder/strategies",
    status_code=status.HTTP_201_CREATED,
    summary="Save Builder Strategy",
    description="Persists a composed block graph as a reusable strategy."
)
async def save_builder_strategy(
    payload: BuilderSaveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    saved = BuilderService.save(user_id=current_user["id"], payload=payload.model_dump(), db=db)
    return {"status": "SUCCESS", "id": saved.id, "name": saved.name}


# =====================================================================
# HELP CONTENT ENDPOINTS
# =====================================================================

@router.get(
    "/help/faq",
    response_model=List[FaqResponse],
    status_code=status.HTTP_200_OK,
    summary="Help FAQ",
    description="Returns frequently asked questions rendered by the in-app help centre."
)
async def get_faq():
    return HELP_FAQ


@router.get(
    "/help/docs",
    response_model=List[DocResponse],
    status_code=status.HTTP_200_OK,
    summary="Documentation Index",
    description="Returns the documentation article index rendered by the in-app help centre."
)
async def get_docs():
    return HELP_DOCS
