from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import require_login
from app.config import SECRET_KEY
from app.routers import (
    campaigns,
    dashboard,
    landing_pages,
    login,
    offers,
    reports,
    traffic_sources,
    tracking,
    tracking_domains,
)

# Schema is owned by Alembic migrations (alembic/versions/) — bring the database up to
# date on startup rather than requiring a manual `alembic upgrade head` step.
command.upgrade(Config("alembic.ini"), "head")

app = FastAPI(title="Tracker")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Public: traffic sources and offers hit these directly, and the login page itself.
app.include_router(login.router)
app.include_router(tracking.router)

# Everything else requires a logged-in session.
protected = [Depends(require_login)]
app.include_router(dashboard.router, dependencies=protected)
app.include_router(reports.router, dependencies=protected)
app.include_router(campaigns.router, dependencies=protected)
app.include_router(traffic_sources.router, dependencies=protected)
app.include_router(landing_pages.router, dependencies=protected)
app.include_router(offers.router, dependencies=protected)
app.include_router(tracking_domains.router, dependencies=protected)
