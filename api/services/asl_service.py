import csv
import copy
import itertools
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import numpy as np
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from api.constant.config import ENABLE_TRACING
from model import KeyPointClassifier
from motor.motor_asyncio import AsyncIOMotorDatabase
import os
from bson import ObjectId

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

class ASLService:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        """Initialize the ASL service with the keypoint classifier and labels."""
        self.db = db
        self.keypoint_classifier = None
        self.keypoint_classifier_labels = []
        self.model_initialized = False
        
        # Only initialize tracer if tracing is enabled
        self.tracing_enabled = ENABLE_TRACING.lower() == "true"
        if self.tracing_enabled:
            self.tracer = trace.get_tracer(__name__)
        else:
            self.tracer = None
            
        self._initialize_model()
    
    def _create_span(self, name: str):
        """Create a span only if tracing is enabled, otherwise return a no-op context manager."""
        if self.tracing_enabled and self.tracer:
            return self.tracer.start_as_current_span(name)
        else:
            # Return a no-op context manager
            from contextlib import nullcontext
            return nullcontext()
    
    def _serialize_response(self, obj: Dict) -> Dict:
        """Convert datetime and ObjectId objects to strings"""
        serialized = {}
        for key, value in obj.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, ObjectId):
                serialized[key] = str(value)
            elif isinstance(value, dict):
                serialized[key] = self._serialize_response(value)
            else:
                serialized[key] = value
        return serialized
    
    def _initialize_model(self):
        """Initialize the keypoint classifier and load labels."""
        with self._create_span("asl_model_initialization") as span:
            try:
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("model.type", "keypoint_classifier")
                
                # Initialize the keypoint classifier
                self.keypoint_classifier = KeyPointClassifier()
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("model.classifier.initialized", True)
                
                # Load labels
                label_path = 'model/keypoint_classifier/keypoint_classifier_label.csv'
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("model.label_path", label_path)
                
                if os.path.exists(label_path):
                    with open(label_path, encoding='utf-8-sig') as f:
                        keypoint_classifier_labels = csv.reader(f)
                        self.keypoint_classifier_labels = [
                            row[0] for row in keypoint_classifier_labels
                        ]
                    if span and hasattr(span, 'set_attribute'):
                        span.set_attribute("model.labels.source", "file")
                else:
                    # Fallback labels if file doesn't exist
                    self.keypoint_classifier_labels = [
                        "ASL 0", "ASL 1", "ASL 2", "ASL 3", "ASL 4", "ASL 5", "ASL 6", "ASL 7", "ASL 8", "ASL 9",
                        "ASL A", "ASL B", "ASL C", "ASL D", "ASL E", "ASL F", "ASL G", "ASL H", "ASL I", "ASL J",
                        "ASL K", "ASL L", "ASL M", "ASL N", "ASL O", "ASL P", "ASL Q", "ASL R", "ASL S", "ASL T",
                        "ASL U", "ASL V", "ASL W", "ASL X", "ASL Y", "ASL Z", "ASL _"
                    ]
                    if span and hasattr(span, 'set_attribute'):
                        span.set_attribute("model.labels.source", "fallback")
                
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("model.labels.count", len(self.keypoint_classifier_labels))
                self.model_initialized = True
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("model.initialization.success", True)
                
            except Exception as e:
                if span and hasattr(span, 'record_exception'):
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("model.initialization.success", False)
                print(f"Error initializing ASL model: {str(e)}")
                self.model_initialized = False
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize ASL model: {str(e)}"
                )
    
    def pre_process_landmark(self, landmark_list: List[List[float]]) -> List[float]:
        """
        Pre-process landmark coordinates for model prediction.
        Converts to relative coordinates and normalizes.
        
        Args:
            landmark_list: List of [x, y] landmark coordinates
            
        Returns:
            List of normalized coordinate values
        """
        with self._create_span("landmark_preprocessing") as span:
            if span and hasattr(span, 'set_attribute'):
                span.set_attribute("landmarks.input.count", len(landmark_list))
            
            temp_landmark_list = copy.deepcopy(landmark_list)

            # Convert to relative coordinates
            base_x, base_y = 0, 0
            for index, landmark_point in enumerate(temp_landmark_list):
                if index == 0:
                    base_x, base_y = landmark_point[0], landmark_point[1]
                    if span and hasattr(span, 'set_attribute'):
                        span.set_attribute("landmarks.base.x", base_x)
                        span.set_attribute("landmarks.base.y", base_y)

                temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
                temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

            # Convert to a one-dimensional list
            temp_landmark_list = list(
                itertools.chain.from_iterable(temp_landmark_list)) 

            # Normalization
            # max_value is the maximum absolute value in the list
            max_value = max(list(map(abs, temp_landmark_list)))
            if span and hasattr(span, 'set_attribute'):
                span.set_attribute("landmarks.normalization.max_value", max_value)

            def normalize_(n):
                return n / max_value if max_value != 0 else 0

            temp_landmark_list = list(map(normalize_, temp_landmark_list))
            if span and hasattr(span, 'set_attribute'):
                span.set_attribute("landmarks.output.count", len(temp_landmark_list))

            return temp_landmark_list
    
    async def predict_from_landmarks(
        self, 
        landmarks_list: List[List[float]], 
        user_id: Optional[str] = None
    ) -> JSONResponse:
        """
        Predict ASL sign from pre-processed and normalized landmark data.
        
        Args:
            pre_processed_landmarks: List of 42 pre-processed landmark coordinates
            user_id: Optional user ID for tracking
            
        Returns:
            JSONResponse containing prediction results
        """
        with self._create_span("asl_prediction") as span:
            start_time = datetime.now(timezone.utc)
            
            # Add span attributes for tracking
            if span and hasattr(span, 'set_attribute'):
                span.set_attribute("prediction.user_id", user_id or "anonymous")
                span.set_attribute("prediction.input.landmarks_count", len(landmarks_list))
                span.set_attribute("prediction.timestamp", start_time.isoformat())
            
            try:
                if not self.model_initialized:
                    if span and hasattr(span, 'set_attribute'):
                        span.set_attribute("prediction.error", "model_not_initialized")
                        span.set_status(Status(StatusCode.ERROR, "ASL model not initialized"))
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="ASL model not initialized"
                    )
                
                # Pre-process landmarks with tracing
                pre_processed_landmarks = self.pre_process_landmark(landmarks_list)
                
                # Validate input data
                if len(pre_processed_landmarks) != 42:
                    if span and hasattr(span, 'set_attribute'):
                        span.set_attribute("prediction.error", "invalid_input_length")
                        span.set_attribute("prediction.input.expected_length", 42)
                        span.set_attribute("prediction.input.actual_length", len(pre_processed_landmarks))
                        span.set_status(Status(StatusCode.ERROR, "Invalid input length"))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Expected 42 pre-processed landmark coordinates"
                    )
                
                # Model prediction with tracing
                with self._create_span("model_inference") as inference_span:
                    if inference_span and hasattr(inference_span, 'set_attribute'):
                        inference_span.set_attribute("model.input.features", len(pre_processed_landmarks))
                    
                    # Data is already pre-processed, pass it directly to the model
                    hand_sign_id = self.keypoint_classifier(pre_processed_landmarks)
                    
                    if inference_span and hasattr(inference_span, 'set_attribute'):
                        inference_span.set_attribute("model.output.class_id", hand_sign_id)
                        inference_span.set_attribute("model.output.valid", 0 <= hand_sign_id < len(self.keypoint_classifier_labels))
                
                # Get the predicted label
                if 0 <= hand_sign_id < len(self.keypoint_classifier_labels):
                    prediction = self.keypoint_classifier_labels[hand_sign_id]
                    confidence = 0.95  # High confidence for valid predictions
                else:
                    prediction = "Unknown"
                    confidence = 0.1   # Low confidence for unknown predictions
                
                # Calculate processing time
                end_time = datetime.now(timezone.utc)
                processing_time_ms = (end_time - start_time).total_seconds() * 1000
                
                # Add prediction results to span
                if span and hasattr(span, 'set_attribute'):
                    span.set_attribute("prediction.result", prediction)
                    span.set_attribute("prediction.confidence", confidence)
                    span.set_attribute("prediction.processing_time_ms", round(processing_time_ms, 2))
                    span.set_attribute("prediction.success", True)
                
                response_data = {
                    "prediction": prediction,
                    "confidence": confidence,
                    "timestamp": end_time,
                    "processing_time_ms": round(processing_time_ms, 2),
                    "user_id": user_id
                }
                
                # Serialize response
                serialized_data = self._serialize_response(response_data)
                
                return JSONResponse(
                    content=serialized_data,
                    status_code=status.HTTP_200_OK
                )
                
            except HTTPException as e:
                if span and hasattr(span, 'record_exception'):
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e.detail)))
                    span.set_attribute("prediction.success", False)
                raise e
            except Exception as e:
                end_time = datetime.now(timezone.utc)
                processing_time_ms = (end_time - start_time).total_seconds() * 1000
                
                if span and hasattr(span, 'record_exception'):
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("prediction.success", False)
                    span.set_attribute("prediction.processing_time_ms", round(processing_time_ms, 2))
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Prediction failed: {str(e)}"
                )
    
    async def get_available_signs(self) -> JSONResponse:
        """
        Get list of available ASL signs that can be predicted.
        
        Returns:
            JSONResponse with list of ASL sign labels
        """
        try:
            if not self.model_initialized:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="ASL model not initialized"
                )
            
            response_data = {
                "signs": self.keypoint_classifier_labels.copy(),
                "total_count": len(self.keypoint_classifier_labels),
                "timestamp": datetime.now(timezone.utc)
            }
            
            serialized_data = self._serialize_response(response_data)
            
            return JSONResponse(
                content=serialized_data,
                status_code=status.HTTP_200_OK
            )
            
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get available signs: {str(e)}"
            )
    
    async def health_check(self) -> JSONResponse:
        """
        Check if the service is ready to make predictions.
        
        Returns:
            JSONResponse with health status
        """
        try:
            response_data = {
                "status": "healthy" if self.model_initialized else "not_ready",
                "model_initialized": self.model_initialized,
                "available_signs_count": len(self.keypoint_classifier_labels) if self.model_initialized else 0,
                "timestamp": datetime.now(timezone.utc)
            }
            
            serialized_data = self._serialize_response(response_data)
            
            return JSONResponse(
                content=serialized_data,
                status_code=status.HTTP_200_OK if self.model_initialized else status.HTTP_503_SERVICE_UNAVAILABLE
            )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Health check failed: {str(e)}"
            )
    
    def is_ready(self) -> bool:
        """
        Check if the service is ready to make predictions.
        
        Returns:
            True if model is initialized and ready
        """
        return self.model_initialized