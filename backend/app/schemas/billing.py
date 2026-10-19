import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import strip_text
from app.models.contact_message import ContactStatus
from app.models.payment import PaymentStatus


class PlanOut(BaseModel):
    code: str
    name: str
    price_baht: int
    period: str
    features: list[str]


class Usage(BaseModel):
    number_checks_today: int
    free_daily_limit: int


class BillingStatus(BaseModel):
    plan: str
    is_premium: bool
    premium_until: datetime | None
    auto_renew: bool
    price_baht: int
    usage: Usage


class CheckoutRequest(BaseModel):
    method: Literal["promptpay", "card"] = "promptpay"


class CheckoutOut(BaseModel):
    payment_id: uuid.UUID
    amount_baht: int
    method: str
    reference: str
    provider: str
    expires_at: datetime
    is_test_mode: bool


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_baht: int
    status: PaymentStatus
    method: str
    provider: str
    provider_ref: str
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime
    paid_at: datetime | None


class ContactRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    topic: Literal["general", "billing", "report", "partnership", "bug"] = "general"
    message: str = Field(min_length=10, max_length=3000)

    @field_validator("name", "message")
    @classmethod
    def _strip(cls, v: str) -> str:
        return strip_text(v) or ""


class ContactMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    topic: str
    message: str
    status: ContactStatus
    created_at: datetime
    handled_at: datetime | None


class ContactUpdate(BaseModel):
    status: ContactStatus


class PaginatedContactMessages(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ContactMessageOut]


class AccountSummary(BaseModel):
    checks_today: int
    checks_total: int
    risky_found: int
    reports_sent: int
    emergency_contacts: int


class AdminOverview(BaseModel):
    members: int
    premium_members: int
    revenue_this_month_baht: int
    paid_this_month: int
    new_contact_messages: int
    checks_today: int
    blacklist_numbers: int
