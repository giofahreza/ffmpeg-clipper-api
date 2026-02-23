"""Google Drive service layer for file operations."""

import io
import logging
from pathlib import Path
from typing import Tuple

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuth2Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def create_drive_client(credentials: dict) -> Resource:
    """
    Create Google Drive API client from credentials.

    Args:
        credentials: Service account or OAuth2 credentials dict

    Returns:
        Google Drive API v3 Resource

    Raises:
        ValueError: If credentials type is unsupported
    """
    cred_type = credentials.get("type")

    if cred_type == "service_account":
        creds = service_account.Credentials.from_service_account_info(
            credentials,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
    elif cred_type == "oauth2":
        creds = OAuth2Credentials(
            token=None,
            refresh_token=credentials["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"]
        )
    else:
        raise ValueError(f"Unsupported credential type: {cred_type}")

    return build("drive", "v3", credentials=creds)


def validate_google_drive(credentials: dict, folder_id: str) -> None:
    """
    Validate Drive credentials and folder access.

    Args:
        credentials: Credentials dictionary
        folder_id: Target folder ID to verify access

    Raises:
        HttpError: If validation fails
    """
    drive = create_drive_client(credentials)

    # Verify folder exists and is accessible
    try:
        drive.files().get(fileId=folder_id, fields="id,name").execute()
        logger.info(f"Validated access to Drive folder: {folder_id}")
    except HttpError as e:
        logger.error(f"Drive validation failed: {e}")
        raise


def download_from_google_drive(
    drive: Resource,
    file_id: str,
    dest_path: str
) -> None:
    """
    Download file from Google Drive.

    Args:
        drive: Drive API client
        file_id: Source file ID
        dest_path: Local destination path

    Raises:
        HttpError: If download fails
    """
    request = drive.files().get_media(fileId=file_id)

    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request, chunksize=32 * 1024 * 1024)
        done = False

        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"Download {int(status.progress() * 100)}%")

    logger.info(f"Downloaded {file_id} to {dest_path}")


def upload_to_google_drive(
    drive: Resource,
    local_path: str,
    folder_id: str,
    mime_type: str = None
) -> Tuple[str, str]:
    """
    Upload file to Google Drive with public sharing.

    Args:
        drive: Drive API client
        local_path: Path to local file
        folder_id: Target Drive folder ID
        mime_type: Optional MIME type (auto-detected if None)

    Returns:
        Tuple of (drive_url, drive_file_id)

    Raises:
        HttpError: If upload fails
    """
    file_name = Path(local_path).name

    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    media = MediaFileUpload(
        local_path,
        mimetype=mime_type,
        resumable=True
    )

    # Upload file
    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file["id"]

    # Set public read permissions
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    drive_url = f"https://drive.google.com/file/d/{file_id}/view"

    logger.info(f"Uploaded {file_name} to Drive: {drive_url}")

    return drive_url, file_id
