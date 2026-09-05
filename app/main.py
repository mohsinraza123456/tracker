from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SECRET_KEY
from app.routers import (
    campaigns,
    collect,
    dashboard,
    home,
    landing_pages,
    login,
    offers,
    reports,
    sites,
    traffic_sources,
    tracking,
    tracking_domains,
    users_admin,
)

# Schema is owned by Alembic migrations (alembic/versions/) — bring the database up to
# date on startup rather than requiring a manual `alembic upgrade head` step.
command.upgrade(Config("alembic.ini"), "head")

app = FastAPI(title="Yourselfmedia Tracker")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Public: the landing page, login/register, and the tracking endpoints traffic
# sources and offers hit directly.
app.include_router(home.router)
app.include_router(login.router)
app.include_router(tracking.router)
app.include_router(collect.router)

# Everything else enforces login (and, for users_admin, admin rights) via a
# Depends(get_current_user)/Depends(require_admin) parameter on each handler —
# that's also how each handler gets the User row it needs to scope owned data.
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(campaigns.router)
app.include_router(sites.router)
app.include_router(traffic_sources.router)
app.include_router(landing_pages.router)
app.include_router(offers.router)
app.include_router(tracking_domains.router)
app.include_router(users_admin.router)
