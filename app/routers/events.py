from fastapi import APIRouter

from app.schemas.events import HookEvent, EventResponse
from app.services.agent import agent_service
from app.websocket import manager

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", response_model=EventResponse)
async def receive_event(event: HookEvent):
    """
    Receive hook events from Claude and broadcast to WebSocket clients
    """
    # Process hook event through agent service
    message_type, message_data = agent_service.process_hook_event(event)

    # Broadcast to all connected WebSocket clients if message generated
    if message_type and message_data:
        await manager.broadcast(message_type, message_data)

    return EventResponse(status="ok")
