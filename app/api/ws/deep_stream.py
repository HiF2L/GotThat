import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.database import async_session_maker
from app.services.tutor.tutor_state_machine import tutor_state_machine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws/deep/{session_id}")
async def deep_learning_websocket_stream(websocket: WebSocket, session_id: str):
    """
    Real-time streaming WebSocket connection for Deep Learning Mode.
    Pushes:
    - 'dag:update': live updates to the Mermaid DAG as concepts are mastered
    - 'step:explanation': streamed atomic explanation chunks with LaTeX
    - 'artifact:render': generated SVG diagrams
    - 'quiz:challenge': locks step until answer received
    """
    await websocket.accept()
    logger.info(f"WebSocket client connected for Deep Session: {session_id}")

    try:
        while True:
            # Receive client actions (e.g. request next step, send voice yap note)
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("action")
            user_notes = payload.get("user_notes", "")

            async with async_session_maker() as db:
                if action == "get_next_action":
                    action_result = await tutor_state_machine.get_next_action(
                        session=db,
                        deep_session_id=session_id,
                        user_notes=user_notes,
                    )
                    await websocket.send_text(json.dumps({
                        "event": f"tutor:{action_result.get('phase', 'action')}",
                        "payload": action_result,
                    }, default=str))

                elif action == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for Deep Session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error in Deep Session {session_id}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
