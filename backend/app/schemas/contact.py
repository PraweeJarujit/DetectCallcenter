import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import ContactPhone


class ContactCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    phone_number: ContactPhone = Field(examples=["081-555-1234"])


class ContactUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: ContactPhone | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone_number: str
    created_at: datetime
    updated_at: datetime
