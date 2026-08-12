"""Dedicated internship-board endpoints. This is intentionally not a search API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import InternshipBoardResponse
from app.services.internship_boards import load_internship_board

router = APIRouter(prefix="/api/internship-boards", tags=["internship-boards"])


@router.get("/{board}", response_model=InternshipBoardResponse)
async def internship_board(
    board: Literal["ashby", "greenhouse"], db: Session = Depends(get_db)
) -> InternshipBoardResponse:
    return await load_internship_board(db, board)
