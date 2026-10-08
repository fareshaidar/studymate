"""One server for users: the API under /api and the built frontend at / (Phase 10).

During development, Vite serves the frontend and its proxy forwards /api/... to the
API (uvicorn app.main:app). For users there is no Vite: this site does both jobs
on one port, so the browser keeps calling /api/... exactly as in development, and
there is still no CORS (everything comes from the same origin).

Run with: uvicorn app.web:site --host 127.0.0.1 --port 8000 (from backend/).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.main import app as api
from app.main import lifespan

# backend/app/web.py -> the repository root -> frontend/dist (made by `npm run build`).
DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

NOT_BUILT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>StudyMate</title></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 3rem auto;">
<h1>StudyMate</h1>
<p>The frontend is not built yet. In PowerShell, in the project folder, run:</p>
<pre>powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1</pre>
<p>The API is running: <a href="/api/health">/api/health</a></p>
</body></html>
"""


def create_site(dist_dir: Path = DEFAULT_DIST) -> FastAPI:
    """The API mounted under /api, and the built frontend (or a hint page) at /.

    A mounted app doesn't run its own startup, so the site reuses the API's
    lifespan: tables, the foreign-key check and the optional cleanup still run.
    The site's own docs pages are off; the API's are at /api/docs.
    """
    site = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Mounted first, so /api/... always reaches the API and never the static files.
    site.mount("/api", api)
    if (dist_dir / "index.html").is_file():
        # html=True: "/" serves index.html.
        site.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
    else:

        @site.get("/", response_class=HTMLResponse, include_in_schema=False)
        def frontend_not_built() -> str:
            return NOT_BUILT_PAGE

    return site


site = create_site()
