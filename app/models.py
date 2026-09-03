import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TrafficSource(Base):
    __tablename__ = "traffic_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cost_model: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # cost charged per click when cost_model == "cpc"
    default_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="traffic_source")


class LandingPage(Base):
    __tablename__ = "landing_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    campaign_links: Mapped[list["CampaignLandingPage"]] = relationship(back_populates="landing_page")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    payout: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    campaign_links: Mapped[list["CampaignOffer"]] = relationship(back_populates="offer")


class TrackingDomain(Base):
    """A domain the operator has pointed at this app (via their own DNS/reverse proxy),
    so campaigns can display tracking links on more than one hostname."""

    __tablename__ = "tracking_domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    # full origin, e.g. "https://track.example.com" — no path or trailing slash
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="tracking_domain")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    traffic_source_id: Mapped[int] = mapped_column(ForeignKey("traffic_sources.id"))
    tracking_domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracking_domains.id"), nullable=True
    )

    # overrides the traffic source's default cost-per-click when set
    cost_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    # if set, clicks flagged as bot traffic are sent here instead of the real offer
    bot_redirect_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    traffic_source: Mapped["TrafficSource"] = relationship(back_populates="campaigns")
    tracking_domain: Mapped["TrackingDomain | None"] = relationship(back_populates="campaigns")
    clicks: Mapped[list["Click"]] = relationship(back_populates="campaign")

    # split-test variants: each campaign rotates across these by weight
    campaign_landing_pages: Mapped[list["CampaignLandingPage"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    campaign_offers: Mapped[list["CampaignOffer"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    @property
    def cost_per_click(self) -> float:
        if self.cost_override is not None:
            return self.cost_override
        if self.traffic_source and self.traffic_source.cost_model == "cpc":
            return self.traffic_source.default_cost
        return 0.0


class CampaignLandingPage(Base):
    """A landing page variant in a campaign's split test, with its rotation weight."""

    __tablename__ = "campaign_landing_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    landing_page_id: Mapped[int] = mapped_column(ForeignKey("landing_pages.id"))
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    campaign: Mapped["Campaign"] = relationship(back_populates="campaign_landing_pages")
    landing_page: Mapped["LandingPage"] = relationship(back_populates="campaign_links")


class CampaignOffer(Base):
    """An offer variant in a campaign's split test, with its rotation weight."""

    __tablename__ = "campaign_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    campaign: Mapped["Campaign"] = relationship(back_populates="campaign_offers")
    offer: Mapped["Offer"] = relationship(back_populates="campaign_links")


class Click(Base):
    __tablename__ = "clicks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))

    # the specific split-test variants that were actually served for this click
    landing_page_id: Mapped[int | None] = mapped_column(ForeignKey("landing_pages.id"), nullable=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"), nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    os: Mapped[str | None] = mapped_column(String(60), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(60), nullable=True)

    sub1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub3: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub4: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sub5: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # excluded from stats/cost when either is true, but still logged for audit
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    campaign: Mapped["Campaign"] = relationship(back_populates="clicks")
    landing_page: Mapped["LandingPage | None"] = relationship()
    offer: Mapped["Offer | None"] = relationship()
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="click")


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[int] = mapped_column(primary_key=True)
    click_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clicks.id"))
    payout: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    click: Mapped["Click"] = relationship(back_populates="conversions")
