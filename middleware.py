import time
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.orm import Session

from database import SessionLocal
from models import CallLog


class CallLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        request_body = await request.body()
        request_data = {}
        if request_body:
            try:
                request_data = json.loads(request_body.decode("utf-8"))
            except:
                request_data = {"raw": request_body.decode("utf-8", errors="ignore")[:1000]}

        case_id = None
        path_params = request.path_params
        if "case_id" in path_params:
            try:
                case_id = int(path_params["case_id"])
            except:
                pass
        if not case_id and request_data and "case_id" in request_data:
            try:
                case_id = int(request_data["case_id"])
            except:
                pass

        response = await call_next(request)

        processing_time_ms = int((time.time() - start_time) * 1000)

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        response_data = {}
        if response_body:
            try:
                response_data = json.loads(response_body.decode("utf-8"))
            except:
                response_data = {"raw": response_body.decode("utf-8", errors="ignore")[:1000]}

        error_message = None
        if response.status_code >= 400:
            error_message = str(response_data.get("detail", str(response.status_code)))

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")

        db: Session = SessionLocal()
        try:
            call_log = CallLog(
                case_id=case_id,
                api_endpoint=request.url.path,
                api_method=request.method,
                request_data=request_data,
                response_data=response_data if response.status_code < 400 else {},
                status_code=response.status_code,
                processing_time_ms=processing_time_ms,
                caller_ip=client_ip,
                caller_agent=user_agent,
                error_message=error_message
            )
            db.add(call_log)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Failed to log call: {e}")
        finally:
            db.close()

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
