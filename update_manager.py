"""A friendly concierge for checking and applying project updates.

It talks to GitHub on the user's behalf, figures out whether a fresher build is
available, downloads it, and swaps files while preserving local state.
"""

from __future__ import annotations

import json
import logging
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Represents a lightweight snapshot of a Git commit."""

    branch: str
    sha: str
    timestamp: str
    url: str


class UpdateError(Exception):
    """Raised when an update operation fails."""


class UpdateManager:
    """Coordinate remote update checks, downloads, backups, and installs."""

    _GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
    _GITHUB_ARCHIVE = "https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip"

    def __init__(self, owner: str, repo: str, project_root: Path) -> None:
        self.owner = owner
        self.repo = repo
        self.project_root = project_root
        self.updates_dir = project_root / "updates"
        self.backup_dir = project_root / "backups"
        self.updates_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
        self._certifi_context: Optional[ssl.SSLContext] = None

    @staticmethod
    def channel_to_branch(channel: str) -> str:
        """Translate a launcher channel selection into a Git branch name."""
        channel = (channel or "stable").lower()
        return "main" if channel == "stable" else "testing"

    def check_for_update(
        self,
        branch: str,
        last_known_commit: Optional[str] = None,
    ) -> Dict[str, Optional[object]]:
        """Ask GitHub whether there's a newer build than the one we're running."""

        latest = self._fetch_latest_commit(branch)
        current_commit = self._get_local_commit() or last_known_commit
        update_available = (
            bool(latest and current_commit) and latest.sha != current_commit
        )
        return {
            "branch": branch,
            "latest": latest,
            "local_commit": current_commit,
            "update_available": update_available,
        }

    # ---------------------------------------------------------------------
    # Remote helpers
    def _fetch_latest_commit(self, branch: str) -> CommitInfo:
        """Pull the tip commit for ``branch`` and narrate errors in plain English."""
        url = self._GITHUB_API.format(owner=self.owner, repo=self.repo, ref=branch)
        request = urllib.request.Request(
            url, headers={"User-Agent": "Automated-Followspot-Updater"}
        )
        try:
            with self._open_url(request, timeout=10) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:  # pragma: no cover - defensive
            if exc.code == 422:
                raise UpdateError(
                    f"Release branch '{branch}' was not found on GitHub. "
                    "Create the branch or switch to the Stable channel."
                ) from exc
            raise UpdateError(
                f"GitHub returned HTTP {exc.code} while retrieving {branch}"
            ) from exc
        except UpdateError:
            raise
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise UpdateError(f"Invalid JSON payload from GitHub: {exc}") from exc

        commit = payload.get("commit", {})
        return CommitInfo(
            branch=branch,
            sha=payload.get("sha", ""),
            timestamp=commit.get("committer", {}).get("date", ""),
            url=payload.get("html_url", ""),
        )

    def _get_local_commit(self) -> Optional[str]:
        """Return the current git SHA if the project lives in a Git checkout."""
        try:
            result = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return result.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

    # ---------------------------------------------------------------------
    # Apply helpers
    def apply_update(
        self,
        branch: str,
        components: Optional[Sequence[str]] = None,
        preserve: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Download and apply updates from the specified branch.

        Args:
            branch: Branch name in the remote repository.
            components: Optional iterable of top-level paths within the archive
                that should be installed (defaults to entire repo).
            preserve: Optional set of top-level directories/files that should
                never be overwritten.
        Returns:
            Dictionary containing backup metadata (e.g., backup path).
        """

        preserve_set = set(preserve or {"config", "identity_gallery", "logs", "updates", "backups"})
        archive_root = self._download_and_extract(branch)
        try:
            payload_root = self._find_archive_root(archive_root, branch)
            selected_paths = (
                [payload_root / comp for comp in components]
                if components
                else list(payload_root.iterdir())
            )

            backup_path = self._create_backup_dir(branch)
            for src in selected_paths:
                if not src.exists():
                    continue
                relative = src.relative_to(payload_root)
                if relative.parts and relative.parts[0] in preserve_set:
                    continue
                destination = self.project_root / relative
                backup_target = backup_path / relative
                self._backup_then_replace(src, destination, backup_target)

            return {
                "backup_path": str(backup_path),
                "installed_paths": [str(path.relative_to(payload_root)) for path in selected_paths],
            }
        finally:
            shutil.rmtree(archive_root, ignore_errors=True)

    def _download_and_extract(self, branch: str) -> Path:
        """Grab the zip archive for ``branch`` and expand it into a temp folder."""
        archive_url = self._GITHUB_ARCHIVE.format(
            owner=self.owner, repo=self.repo, ref=branch
        )
        temp_dir = Path(tempfile.mkdtemp(prefix="afs_update_"))
        archive_path = temp_dir / f"{self.repo}-{branch}.zip"

        request = urllib.request.Request(
            archive_url, headers={"User-Agent": "Automated-Followspot-Updater"}
        )
        try:
            with self._open_url(request, timeout=30) as response:
                with open(archive_path, "wb") as handle:
                    shutil.copyfileobj(response, handle)
        except urllib.error.HTTPError as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise UpdateError(
                f"GitHub returned HTTP {exc.code} while downloading archive for {branch}"
            ) from exc
        except UpdateError:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(temp_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise UpdateError(f"Downloaded archive was invalid: {exc}") from exc

        return temp_dir

    # ------------------------------------------------------------------
    # Networking helpers
    def _open_url(self, request: urllib.request.Request, *, timeout: int):
        """Open a URL with a helpful retry that explains certificate errors."""
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.URLError as exc:
            if isinstance(exc, urllib.error.HTTPError):
                raise

            if self._is_certificate_error(exc):
                context = self._get_certifi_context()
                if context is None:
                    raise UpdateError(
                        "SSL verification failed when contacting GitHub. Install system certificates "
                        "(on macOS run 'Install Certificates.command') or install certifi via 'pip install certifi'."
                        f" Original error: {exc}"
                    ) from exc

                try:
                    return urllib.request.urlopen(
                        request, timeout=timeout, context=context
                    )
                except urllib.error.URLError as retry_exc:
                    if isinstance(retry_exc, urllib.error.HTTPError):
                        raise
                    raise UpdateError(
                        "Network error while contacting GitHub even after retrying with bundled certificates: "
                        f"{retry_exc}"
                    ) from retry_exc

            raise UpdateError(f"Network error while contacting GitHub: {exc}") from exc

    @staticmethod
    def _is_certificate_error(error: urllib.error.URLError) -> bool:
        """Detect whether the given URLError was caused by certificate issues."""
        reason = getattr(error, "reason", None)
        if isinstance(reason, ssl.SSLError):
            return True
        message = str(reason or error)
        return "CERTIFICATE_VERIFY_FAILED" in message or "certificate verify failed" in message.lower()

    def _get_certifi_context(self) -> Optional[ssl.SSLContext]:
        """Lazily build and cache an SSL context backed by certifi if installed."""
        if self._certifi_context is not None:
            return self._certifi_context

        try:
            import certifi  # type: ignore
        except ImportError:
            return None

        self._certifi_context = ssl.create_default_context(cafile=certifi.where())
        logger.debug("Using certifi CA bundle for GitHub requests")
        return self._certifi_context

    def _find_archive_root(self, extracted_dir: Path, branch: str) -> Path:
        """Locate the actual project directory inside GitHub's zip wrapper."""
        prefix = f"{self.repo}-{branch}"
        for child in extracted_dir.iterdir():
            if child.is_dir() and child.name.startswith(prefix):
                return child
        raise UpdateError("Unable to locate extracted archive root")

    def _create_backup_dir(self, branch: str) -> Path:
        """Create a timestamped backup directory for files we're about to replace."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.backup_dir / f"{branch}_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def _backup_then_replace(self, src: Path, dest: Path, backup_target: Path) -> None:
        """Copy ``dest`` into the backup folder before overwriting it with ``src``."""
        if dest.exists():
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_dir():
                shutil.copytree(dest, backup_target, dirs_exist_ok=True)
                shutil.rmtree(dest)
            else:
                shutil.copy2(dest, backup_target)
                dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)