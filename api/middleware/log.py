from datetime import datetime
import json
import logging
import sys
from fastapi import BackgroundTasks, HTTPException, Request, Response, status

from fastapi.responses import JSONResponse
from requests import Session
from starlette.middleware.base import BaseHTTPMiddleware

from api.constant.log import LENGTH_MAX_RESPONSE
from api.schema.log import LogModel
from api.utils.logger import write_log

#get logger 
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class APIGatewayMiddleware(BaseHTTPMiddleware):
    def print_log_request(self, 
        request : Request, 
        request_body, 
        original_path, 
        start_time
    ):
        formatted_time = datetime.fromtimestamp(start_time)
        formatted_time = formatted_time.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(
            f"\nREQUEST\n"
            f"\nStart time: {formatted_time}"
            f"\n{request.method} request to {request.url} metadata\n"
            f"\tBody: {request_body}\n"
            f"\tPath Params: {request.path_params}\n"
            f"\tQuery Params: {request.query_params}\n"
            f"\tOriginal path: {original_path}\n"
        )
    
    def get_ip(self, request: Request) -> str:
        headers_to_check = [
            "X-Forwarded-For",
            "X-Real-IP"
        ]
        for header in headers_to_check:
            if header in request.headers:
                return request.headers[header].split(",")[0].strip()
        return request.client.host # falls back to the IP of the immediate client (might be proxy)
    
    def write_log(self,
        request: Request,
        request_body: str,
        original_path: str,
        status_code: int,
        body_str: str,
        process_time: float, 
        error_message = None
    ):
        path_params = request.path_params
        query_params = dict(request.query_params)
        request_params = str({
            "path": path_params,
            "query": query_params
        })
        client_ip = self.get_ip(request=request)
        
        try:
            decoded_request_body = request_body
        except UnicodeDecodeError:
            decoded_request_body = str(request_body)
        log_entry = LogModel(
            action_date= datetime.now(),
            path_name=original_path,
            method=request.method,
            ip = client_ip,
            status_response= status_code,
            response=body_str,
            duration=round(process_time, 3),
            request_body=decoded_request_body,
            request_query = request_params,
            description = None if error_message is None else error_message
        )
        
        write_log(request=log_entry)
        
    def print_log_response(self, status_code:int, response, error_message: str):
        logger.info(
            f"\nRESPONSE \n"
            f"Status Code: {status_code}\n"
            f"Response: {response}\n"
            f"Error message: {error_message}\n"
        )
        
    async def handle_log(self,
        request: Request,
        request_body: str,
        status_code: int,
        error_message:str,
        original_path:str,
        start_time, 
        process_time, 
        body_str: str
    ):
        self.print_log_request(
            request=request, 
            request_body=request_body, 
            original_path=original_path, 
            start_time=start_time
        )
        
        self.write_log(
            request=request, 
            request_body=request_body, 
            original_path=original_path, 
            status_code=status_code,
            body_str=body_str, 
            process_time=process_time, 
            error_message=error_message
        )
        self.print_log_response(
            status_code=status_code, 
            response=body_str[:LENGTH_MAX_RESPONSE], 
            error_message=error_message
        )
    
    async def dispatch(self, request: Request, call_next):
        response_time = 0
        error_message = None
        body_str = ""
        response = None
        
        try:
            original_path = request.url.path
            start_time = datetime.now().timestamp()
            
            # Get request body
            request_body = await request.body()
            content_type = request.headers.get('Content-Type', '')
            
            # Parse JSON request body if applicable
            if 'application/json' in content_type and request_body:
                try:
                    request_body_json = json.loads(request_body)
                    request_body = json.dumps(request_body_json)
                except json.JSONDecodeError:
                    error_message = "Invalid JSON format"
                    response = JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": error_message}
                    )
                    # Calculate response time and process logging
                    response_time = datetime.now().timestamp() - start_time
                    
                    # Run background task to write log
                    background_tasks = BackgroundTasks()
                    body_str = json.dumps({"detail": error_message})
                    # background_tasks.add_task(
                    #     self.handle_log,
                    #     request,
                    #     request_body,
                    #     status.HTTP_400_BAD_REQUEST,
                    #     error_message,
                    #     original_path,
                    #     start_time,
                    #     response_time,
                    #     body_str
                    # )
                    response.background = background_tasks
                    return response
            
            # Process the request if JSON was valid or not JSON
            if not response:  # Only call next if we don't have an error response already
                response = await call_next(request)
                response_time = datetime.now().timestamp() - start_time
                
                # Capture the response body without consuming the stream
                orig_response = response
                response_body = b""
                
                # Only process the body for non-streaming responses
                if not hasattr(response, "body_iterator"):
                    # Response is already complete, like JSONResponse
                    if hasattr(response, "body"):
                        response_body = response.body
                else:
                    # Stream response body
                    async for chunk in response.body_iterator:
                        response_body += chunk
                    
                    # Create a new response with the same content
                    response = Response(
                        content=response_body,
                        status_code=orig_response.status_code,
                        headers=dict(orig_response.headers),
                        media_type=orig_response.media_type
                    )
                
                # Try to decode response body as string
                try:
                    body_str = response_body.decode("utf-8")
                    
                    # If it's JSON, try to parse it for better logging
                    if response.media_type == "application/json":
                        try:
                            body_json = json.loads(body_str)
                            if "detail" in body_json and body_json["detail"]:
                                error_message = body_json["detail"]
                        except json.JSONDecodeError:
                            # Not valid JSON, leave as is
                            pass
                except UnicodeDecodeError:
                    body_str = f"<Binary data: {len(response_body)} bytes>"
        
        # Catch HTTP exceptions
        except HTTPException as http_exception:
            response_time = datetime.now().timestamp() - start_time
            error_message = http_exception.detail
            
            response = JSONResponse(
                status_code=http_exception.status_code,
                content={"detail": error_message}
            )
            
            body_str = json.dumps({"detail": error_message})
        
        # Catch other exception types
        except Exception as e:
            response_time = datetime.now().timestamp() - start_time
            error_message = str(e)
            
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": error_message}
            )
            
            body_str = json.dumps({"detail": error_message})
        
        finally:
            if not response:
                # Fallback if something went wrong
                error_message = "Unexpected error in middleware"
                response = JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": error_message}
                )
                body_str = json.dumps({"detail": error_message})
            
            # Run background task to write log
            # background_tasks = BackgroundTasks()
            # background_tasks.add_task(
            #     self.handle_log,
            #     request,
            #     request_body,
            #     response.status_code,
            #     error_message,
            #     original_path,
            #     start_time,
            #     response_time,
            #     body_str
            # )
            # response.background = background_tasks
            
            return response
            