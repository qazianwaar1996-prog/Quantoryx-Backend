# backend/api/portfolio_endpoints.py
"""
Quantoryx — Portfolio, Watchlists & Notifications API Endpoints Router Module.

Exposes REST routes for real-time active positions state retrieval, watchlist CRUD actions,
custom settings preferences, and alert notification management.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

# Import dependencies and schemas
from backend.api.deps import get_current_user, get_db
from backend.schemas.api_schemas import (
    UserSettingsResponse,
    UserSettingsUpdateRequest,
    ActivePositionResponse,
    WatchlistResponse,
    WatchlistCreateRequest,
    WatchlistItemResponse,
    WatchlistItemCreateRequest,
    NotificationResponse,
)
from backend.services.user_service import UserService
from backend.services.portfolio_services import PortfolioService

# Initialize Router
router = APIRouter(prefix="/api/portfolio", tags=["Portfolio, Watchlists & Notifications"])


# =====================================================================
# USER SETTINGS CONFIGURATION ENDPOINTS
# =====================================================================

@router.get(
    "/settings",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User Settings",
    description="Returns customizable operational configurations per user profile."
)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = UserService.get_user_settings(user_id=current_user["id"], db=db)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="UserSettings profile records could not be resolved."
        )
    return settings


@router.put(
    "/settings",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Update User Settings",
    description="Modifies customizable operational configurations per user profile."
)
async def update_settings(
    payload: UserSettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    settings = UserService.update_user_settings(
        user_id=current_user["id"],
        update_request=payload,
        db=db
    )
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configuration update transaction aborted."
        )
    return settings


# =====================================================================
# ACTIVE HOLDINGS ENDPOINTS
# =====================================================================

@router.get(
    "/holdings",
    response_model=List[ActivePositionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Active Positions",
    description="Retrieves persistent active holdings representing open transactions."
)
async def get_holdings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return PortfolioService.get_active_positions(user_id=current_user["id"], db=db)


# =====================================================================
# WATCHLIST ENDPOINTS
# =====================================================================

@router.get(
    "/watchlists",
    response_model=List[WatchlistResponse],
    status_code=status.HTTP_200_OK,
    summary="Get User Watchlists",
    description="Retrieves watchlist groupings configured by a user."
)
async def get_watchlists(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return PortfolioService.get_watchlists_by_user(user_id=current_user["id"], db=db)


@router.post(
    "/watchlists",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Watchlist",
    description="Instantiates a new named watchlist grouping."
)
async def post_watchlist(
    payload: WatchlistCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    watchlist = PortfolioService.create_watchlist(
        user_id=current_user["id"],
        name=payload.name,
        db=db
    )
    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Watchlist creation failed."
        )
    return watchlist


@router.delete(
    "/watchlists/{watchlist_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Watchlist",
    description="Deletes a designated watchlist grouping after confirming ownership."
)
async def delete_watchlist(
    watchlist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = PortfolioService.delete_watchlist(
        user_id=current_user["id"],
        watchlist_id=watchlist_id,
        db=db
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist missing or unauthorized access."
        )
    return {"status": "SUCCESS", "message": "Watchlist deleted successfully."}


@router.post(
    "/watchlists/{watchlist_id}/items",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Symbol to Watchlist",
    description="Appends a tracking symbol ticker into an authorized watchlist."
)
async def post_watchlist_item(
    watchlist_id: int,
    payload: WatchlistItemCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = PortfolioService.add_symbol_to_watchlist(
        user_id=current_user["id"],
        watchlist_id=watchlist_id,
        symbol=payload.symbol,
        db=db
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item append transaction rejected. Symbol may already exist inside watchlist."
        )
    return item


@router.delete(
    "/watchlists/{watchlist_id}/items/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove Symbol from Watchlist",
    description="Removes a symbol record from an authorized watchlist."
)
async def delete_watchlist_item(
    watchlist_id: int,
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = PortfolioService.remove_symbol_from_watchlist(
        user_id=current_user["id"],
        watchlist_id=watchlist_id,
        item_id=item_id,
        db=db
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item missing or unauthorized access."
        )
    return {"status": "SUCCESS", "message": "Symbol removed from watchlist successfully."}


# =====================================================================
# NOTIFICATION ENDPOINTS
# =====================================================================

@router.get(
    "/notifications",
    response_model=List[NotificationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get User Notifications",
    description="Retrieves generated unread risk alert and warning notifications."
)
async def get_notifications(
    unread_only: bool = Query(True, description="Filter only unread alert indices"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return PortfolioService.get_notifications_by_user(
        user_id=current_user["id"],
        unread_only=unread_only,
        db=db
    )


@router.put(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark Notification as Read",
    description="Dismisses an authorized notification record."
)
async def put_notification_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = PortfolioService.mark_notification_read(
        user_id=current_user["id"],
        notification_id=notification_id,
        db=db
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification missing or unauthorized access."
        )
    return {"status": "SUCCESS", "message": "Notification marked as read."}


@router.put(
    "/notifications/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark All Notifications as Read",
    description="Dismisses all unread notification records for a user."
)
async def put_read_all_notifications(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    PortfolioService.dismiss_all_notifications(user_id=current_user["id"], db=db)
    return {"status": "SUCCESS", "message": "All notifications marked as read."}
