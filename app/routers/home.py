from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["home"])
templates = Jinja2Templates(directory="app/templates/landing")


@router.get("/")
@router.get("/index.html")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/gdpr.html")
def gdpr(request: Request):
    return templates.TemplateResponse("gdpr.html", {"request": request})


@router.get("/privacy-policy.html")
def privacy_policy(request: Request):
    return templates.TemplateResponse("privacy-policy.html", {"request": request})


@router.get("/terms-and-condition.html")
def terms_and_conditions(request: Request):
    return templates.TemplateResponse("terms-and-condition.html", {"request": request})


@router.get("/about-us.html")
def about_us(request: Request):
    return templates.TemplateResponse("about-us.html", {"request": request})


@router.get("/contact-us.html")
def contact_us(request: Request):
    return templates.TemplateResponse("contact-us.html", {"request": request})


@router.get("/robots.txt")
def robots_txt():
    return FileResponse("seo/robots.txt", media_type="text/plain")


@router.get("/sitemap.xml")
def sitemap_xml():
    return FileResponse("seo/sitemap.xml", media_type="application/xml")
