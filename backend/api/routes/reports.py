"""
reports.py — Report generation endpoint

STATUS: IMPLEMENTED
"""
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.api.routes.investigate import investigate as _investigate
from backend.services.report_generator import generate_pdf_report

router = APIRouter(prefix="/api", tags=["reports"])


@router.post("/reports/{account_id}")
def generate_report(account_id: str):
    """
    Generate a PDF investigation report.
    Returns the PDF file as a download.
    """
    result = _investigate(account_id)
    output_path = generate_pdf_report(result)
    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename=f"investigation_{account_id}.pdf",
    )
