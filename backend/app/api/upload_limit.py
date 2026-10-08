"""Reject oversized uploads before their body is read.

FastAPI reads the whole multipart body before the upload endpoint (or any of its
dependencies) runs, so the byte count in documents._save_upload only fires after
the full file has arrived. This middleware looks at the Content-Length header
first and answers 413 straight away. The byte count stays as the exact check,
and as the only one for requests without Content-Length.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config import settings

UPLOAD_PATH = "/documents"
# The multipart wrapping (boundaries, headers) adds a few hundred bytes to the file;
# 1 MB of slack keeps a file exactly at the limit from being rejected here.
MULTIPART_ALLOWANCE = 1024 * 1024


def too_large_message() -> str:
    return f"File is larger than {settings.max_upload_mb} MB."


def _path_in_app(request: Request) -> str:
    """The request path as this app's routes see it.

    When the API is mounted under /api (app/web.py), url.path is the full
    "/api/documents" and root_path is "/api"; directly (uvicorn app.main:app)
    root_path is empty. Removing root_path gives "/documents" in both cases.
    """
    path = request.url.path
    root_path = request.scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        return path[len(root_path):]
    return path


async def reject_oversized_uploads(request: Request, call_next):
    """HTTP middleware: 413 for a POST /documents whose Content-Length is over the limit."""
    if request.method == "POST" and _path_in_app(request) == UPLOAD_PATH:
        length = request.headers.get("content-length", "")
        limit = settings.max_upload_mb * 1024 * 1024 + MULTIPART_ALLOWANCE
        if length.isdigit() and int(length) > limit:
            return JSONResponse(
                {"detail": too_large_message()},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
    return await call_next(request)
