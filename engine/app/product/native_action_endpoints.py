"""FastAPI router for the V7 native macOS action path.

Routes (all return the underlying NativeResult.to_dict() shape):

  POST /api/native/calendar/event
    Body: {"title","start","end","location","notes","calendar_name"}

  GET  /api/native/calendar/events?start=&end=
    Lists events between start and end (ISO dates).

  POST /api/native/reminders
    Body: {"title","due","list_name","notes"}

  POST /api/native/notes
    Body: {"title","body","folder"}

  POST /api/native/finder/reveal
    Body: {"path"}

  GET  /api/native/finder/search?q=

  POST /api/native/messages/draft
    Body: {"recipient","body","send"}
    send defaults to false. The endpoint NEVER sends unless callers
    explicitly set send=true.

This router does not touch frozen modules. Caller authentication is
delegated to the engine's existing perimeter (loopback-only port). No
em-dashes. Under 200 lines.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.native_action_macos import NativeMacOS


router = APIRouter()

_DRIVER = NativeMacOS()


class CalendarEventBody(BaseModel):
    title: str
    start: str
    end: str
    location: Optional[str] = ""
    notes: Optional[str] = ""
    calendar_name: Optional[str] = ""


@router.post("/api/native/calendar/event")
def native_calendar_event(body: CalendarEventBody) -> JSONResponse:
    if not body.title or not body.start or not body.end:
        raise HTTPException(
            status_code=400,
            detail="title, start, and end are required",
        )
    result = _DRIVER.calendar_create_event(
        title=body.title, start=body.start, end=body.end,
        location=body.location or "", notes=body.notes or "",
        calendar_name=body.calendar_name or "",
    )
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


@router.get("/api/native/calendar/events")
def native_calendar_events(
    start: str = Query(...),
    end: str = Query(...),
) -> JSONResponse:
    result = _DRIVER.calendar_list_events(start, end)
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


class ReminderBody(BaseModel):
    title: str
    due: Optional[str] = ""
    list_name: Optional[str] = "Reminders"
    notes: Optional[str] = ""


@router.post("/api/native/reminders")
def native_reminders_add(body: ReminderBody) -> JSONResponse:
    if not body.title:
        raise HTTPException(status_code=400, detail="title required")
    result = _DRIVER.reminders_add(
        title=body.title, due=body.due or "",
        list_name=body.list_name or "Reminders",
        notes=body.notes or "",
    )
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


class NoteBody(BaseModel):
    title: str
    body: str
    folder: Optional[str] = "Notes"


@router.post("/api/native/notes")
def native_notes_create(body: NoteBody) -> JSONResponse:
    if not (body.title or body.body):
        raise HTTPException(status_code=400,
                            detail="title or body required")
    result = _DRIVER.notes_create(
        title=body.title or "", body=body.body or "",
        folder=body.folder or "Notes",
    )
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


class FinderRevealBody(BaseModel):
    path: str


@router.post("/api/native/finder/reveal")
def native_finder_reveal(body: FinderRevealBody) -> JSONResponse:
    if not body.path:
        raise HTTPException(status_code=400, detail="path required")
    result = _DRIVER.finder_reveal(body.path)
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


@router.get("/api/native/finder/search")
def native_finder_search(q: str = Query(...)) -> JSONResponse:
    if not q:
        raise HTTPException(status_code=400, detail="q required")
    result = _DRIVER.finder_search(q)
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


class MessagesDraftBody(BaseModel):
    recipient: str
    body: str
    send: Optional[bool] = False


@router.post("/api/native/messages/draft")
def native_messages_draft(body: MessagesDraftBody) -> JSONResponse:
    if not body.recipient or not body.body:
        raise HTTPException(
            status_code=400,
            detail="recipient and body required",
        )
    result = _DRIVER.messages_draft(
        recipient=body.recipient, body=body.body,
        send=bool(body.send),
    )
    return JSONResponse(result.to_dict(),
                        status_code=200 if result.ok else 502)


__all__ = ["router"]
