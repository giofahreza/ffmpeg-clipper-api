"""Shared models used across all endpoints."""

from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict


class ServiceAccountCredentials(BaseModel):
    """Google Cloud service account credentials."""

    model_config = ConfigDict(extra="allow")

    type: Literal["service_account"]
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str


class OAuth2Credentials(BaseModel):
    """OAuth2 credentials for Google Drive."""

    type: Literal["oauth2"]
    client_id: str
    client_secret: str
    refresh_token: str


GoogleDriveCredentials = Annotated[
    ServiceAccountCredentials | OAuth2Credentials,
    Field(discriminator="type")
]


class AcceptedResponse(BaseModel):
    """Standard 202 Accepted response."""

    status: Literal["accepted"] = "accepted"
    job_id: str
    message: str = "Job accepted and processing in background"


class ErrorPayload(BaseModel):
    """Standard error webhook payload."""

    status: Literal["error"] = "error"
    error_message: str
