"""Google Drive API client for kindle2md."""
import io
import json
import re
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveClient:
    """Client for downloading PDFs from Google Drive."""

    def __init__(self, credentials_path: Path | str):
        self.credentials_path = Path(credentials_path)
        if not self.credentials_path.exists():
            raise FileNotFoundError(f"Credentials not found: {self.credentials_path}")

        self._credentials = self._authenticate()
        self._service = build("drive", "v3", credentials=self._credentials)

    def _authenticate(self) -> Credentials:
        """Authenticate via OAuth2 with token caching."""
        token_path = self.credentials_path.parent / "token.json"

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Detect port from credentials redirect_uris
                port = self._detect_port()
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=port)

            token_path.write_text(creds.to_json())

        return creds

    def _detect_port(self) -> int:
        """Read redirect_uris from credentials to find the right port."""
        data = json.loads(self.credentials_path.read_text())
        # Handle both "web" and "installed" credential types
        config = data.get("web") or data.get("installed") or {}
        uris = config.get("redirect_uris", [])
        for uri in uris:
            m = re.search(r"localhost:(\d+)", uri)
            if m:
                return int(m.group(1))
        return 8080  # fallback

    @staticmethod
    def parse_folder_id(folder_input: str) -> str:
        """Extract folder ID from Drive URL or return as-is."""
        m = re.search(
            r"drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)",
            folder_input,
        )
        return m.group(1) if m else folder_input

    def get_folder_name(self, folder_id: str) -> str:
        """Get folder name by ID."""
        result = self._service.files().get(
            fileId=folder_id, fields="name"
        ).execute()
        return result.get("name", "")

    def list_files(
        self,
        folder_id: str,
        mime_filter: str = "application/pdf",
        recursive: bool = False,
    ) -> list[dict]:
        """List files in a Drive folder, optionally recursive.

        Args:
            folder_id: Root folder ID
            mime_filter: MIME type to filter (e.g. "application/pdf", "text/markdown")
            recursive: Search subfolders

        Returns:
            List of dicts with keys: id, name, mimeType, path, parent_folder_id
        """
        files: list[dict] = []
        self._list_files_recursive(folder_id, files, "", mime_filter, recursive)
        return files

    def _list_files_recursive(
        self,
        folder_id: str,
        files: list[dict],
        current_path: str,
        mime_filter: str,
        recursive: bool,
    ) -> None:
        query = f"'{folder_id}' in parents and trashed = false"
        page_token = None

        while True:
            response = self._service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            ).execute()

            for item in response.get("files", []):
                if item["mimeType"] == mime_filter:
                    item["path"] = current_path
                    item["parent_folder_id"] = folder_id
                    files.append(item)
                elif item["mimeType"] == "application/vnd.google-apps.folder":
                    if recursive:
                        sub = f"{current_path}/{item['name']}" if current_path else item["name"]
                        self._list_files_recursive(
                            item["id"], files, sub, mime_filter, recursive
                        )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def list_pdfs(self, folder_id: str, recursive: bool = False) -> list[dict]:
        """List all PDF files."""
        return self.list_files(folder_id, "application/pdf", recursive)

    def list_markdowns(self, folder_id: str, recursive: bool = False) -> list[dict]:
        """List all Markdown files."""
        return self.list_files(folder_id, "text/markdown", recursive)

    def download_file(self, file_id: str, destination: Path) -> Path:
        """Download a file from Drive to local path."""
        request = self._service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fh.getvalue())
        return destination

    def upload_file(
        self, local_path: Path, folder_id: str, name: Optional[str] = None
    ) -> str:
        """Upload a file to a Drive folder.

        Returns:
            ID of uploaded file.
        """
        file_metadata = {
            "name": name or local_path.name,
            "parents": [folder_id],
        }
        media = MediaFileUpload(str(local_path), mimetype="text/markdown")
        result = self._service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
        return result.get("id")
