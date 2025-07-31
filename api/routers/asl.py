from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer
import json
import logging
from datetime import datetime
from typing import Dict
from api.services.asl_service import ASLService
from api.middleware.auth import get_optional_user
from api.schema.user import UserProfile
from api.database.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asl", tags=["ASL Prediction"])
security = HTTPBearer()

class ConnectionManager:
    """Manages WebSocket connections for ASL prediction"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and store it"""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected to ASL WebSocket")
    
    def disconnect(self, user_id: str):
        """Remove WebSocket connection"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected from ASL WebSocket")
    
    async def send_message(self, user_id: str, message: dict):
        """Send message to specific user"""
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)


manager = ConnectionManager()

def get_asl_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> ASLService:
    return ASLService(db)

@router.websocket("/predict")
async def websocket_asl_predict(
    websocket: WebSocket, 
    user: UserProfile = Depends(get_optional_user),
    asl_service: ASLService = Depends(get_asl_service)
):
    """
    WebSocket endpoint for real-time ASL prediction.
    """
    user_id = user.id if user else "anonymous"
    
    try:
        await manager.connect(websocket, user_id)
        
        # Check if ASL service is ready
        if not asl_service.is_ready():
            await websocket.send_json({
                "error": "ASL model not initialized",
                "error_code": "MODEL_NOT_READY",
                "timestamp": datetime.now().isoformat()
            })
            return
        
        while True:
            try:
                # Receive message from client
                message = await websocket.receive()
                
                # Handle close frame
                if message["type"] == "websocket.disconnect":
                    logger.info(f"Received disconnect from {user_id}")
                    break
                
                # Handle regular message
                if message["type"] == "websocket.receive":
                    data = json.loads(message["text"])
                    logger.info(f"Received data from {user_id}: {type(data)}")
                    
                    # Validate message format
                    if not isinstance(data, dict):
                        await websocket.send_json({
                            "error": "Invalid data format: expected JSON object",
                            "error_code": "INVALID_FORMAT",
                            "timestamp": datetime.now().isoformat()
                        })
                        continue
                    
                    if "data" not in data:
                        await websocket.send_json({
                            "error": "Invalid data format: missing 'data' field",
                            "error_code": "INVALID_FORMAT", 
                            "timestamp": datetime.now().isoformat()
                        })
                        continue
                    
                    landmarks_data = data["data"]
                    
                    # Make prediction - this now returns a JSONResponse
                    # For WebSocket, we need to extract the content from the response
                    try:
                        result_response = await asl_service.predict_from_landmarks(landmarks_data, user_id)
                        result = result_response.body.decode('utf-8')
                        result_data = json.loads(result)
                        
                        # Send prediction result back to client
                        await websocket.send_json(result_data)
                        
                    except HTTPException as e:
                        await websocket.send_json({
                            "error": e.detail,
                            "error_code": "PREDICTION_ERROR",
                            "timestamp": datetime.now().isoformat()
                        })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "error": "Invalid JSON format",
                    "error_code": "INVALID_JSON",
                    "timestamp": datetime.now().isoformat()
                })
                
            except ValueError as e:
                await websocket.send_json({
                    "error": str(e),
                    "error_code": "VALIDATION_ERROR",
                    "timestamp": datetime.now().isoformat()
                })
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for {user_id}")
                break
                
            except Exception as e:
                logger.error(f"Error processing ASL prediction: {str(e)}")
                await websocket.send_json({
                    "error": f"Internal server error: {str(e)}",
                    "error_code": "INTERNAL_ERROR",
                    "timestamp": datetime.now().isoformat()
                })
                break
    
    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        manager.disconnect(user_id)


@router.get("/signs")
async def get_available_signs(
    asl_service: ASLService = Depends(get_asl_service)
):
    """
    Get list of available ASL signs that can be predicted.
    """
    return await asl_service.get_available_signs()


@router.get("/health")
async def asl_health_check(
    asl_service: ASLService = Depends(get_asl_service)
):
    """
    Health check endpoint for ASL service.
    """
    return await asl_service.health_check()
