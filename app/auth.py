from fastapi import HTTPException, Request


def require_login(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": f"/login?next={request.url.path}"})
