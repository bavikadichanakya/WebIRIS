"""
Project IRIS - Resumable Model & Asset Downloader
Provides chunked, resumable HTTP downloads with speed, ETA, and cancellation support.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("iris.setup.downloader")


class DownloadProgress:
    """Snapshot of current download progress."""

    def __init__(
        self,
        downloaded_bytes: int,
        total_bytes: int,
        speed_bps: float,
        eta_seconds: float,
        percent: float,
    ) -> None:
        self.downloaded_bytes = downloaded_bytes
        self.total_bytes = total_bytes
        self.speed_bps = speed_bps
        self.eta_seconds = eta_seconds
        self.percent = percent

    @property
    def speed_mbps(self) -> float:
        return self.speed_bps / (1024 * 1024)

    @property
    def downloaded_mb(self) -> float:
        return self.downloaded_bytes / (1024 * 1024)

    @property
    def total_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)


class Downloader:
    """Manages downloading large files with progress reporting and cancellation."""

    def __init__(self) -> None:
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True
        logger.info("Download cancellation requested.")

    def download_file(
        self,
        url: str,
        dest_path: str,
        expected_size: Optional[int] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        chunk_size: int = 1024 * 64,  # 64 KB chunks
    ) -> bool:
        """
        Download a file from url to dest_path.
        Supports resume if destination directory has a .part file.
        """
        self._is_cancelled = False
        dest_file = Path(dest_path).resolve()
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        part_file = dest_file.with_suffix(dest_file.suffix + ".part")

        # 1. Check disk space
        free_bytes = shutil.disk_usage(dest_file.parent).free
        needed = expected_size or (2 * 1024 * 1024 * 1024)  # Default ~2GB check
        if free_bytes < needed:
            msg = f"Insufficient disk space. Needed: {needed / 1024 / 1024:.1f}MB, Free: {free_bytes / 1024 / 1024:.1f}MB"
            logger.error(msg)
            raise OSError(msg)

        # 2. Check if already downloaded and matches expected size
        if dest_file.exists():
            existing_size = dest_file.stat().st_size
            if expected_size and existing_size == expected_size:
                logger.info(f"File already completely downloaded: {dest_file}")
                if progress_callback:
                    progress_callback(
                        DownloadProgress(existing_size, existing_size, 0.0, 0.0, 100.0)
                    )
                return True

        # 3. Resume partial file if exists
        downloaded_bytes = 0
        if part_file.exists():
            downloaded_bytes = part_file.stat().st_size

        retries = 0
        max_retries = 10

        while retries < max_retries and not self._is_cancelled:
            downloaded_bytes = part_file.stat().st_size if part_file.exists() else 0
            if expected_size and downloaded_bytes >= expected_size:
                break

            headers = {"User-Agent": "IRIS-Desktop-Assistant/1.0"}
            if downloaded_bytes > 0:
                headers["Range"] = f"bytes={downloaded_bytes}-"
                logger.info(f"Connecting/resuming download from byte {downloaded_bytes}...")

            req = urllib.request.Request(url, headers=headers)

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content_range = resp.headers.get("Content-Range")
                    content_len = resp.headers.get("Content-Length")

                    total_bytes = 0
                    if content_range:
                        try:
                            total_bytes = int(content_range.split("/")[-1])
                        except Exception:
                            pass
                    elif content_len:
                        total_bytes = downloaded_bytes + int(content_len)
                    elif expected_size:
                        total_bytes = expected_size

                    mode = "ab" if downloaded_bytes > 0 else "wb"
                    with open(part_file, mode) as f:
                        t_start = time.time()
                        t_last_calc = t_start
                        bytes_since_calc = 0
                        speed_bps = 0.0

                        while not self._is_cancelled:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            bytes_since_calc += len(chunk)

                            now = time.time()
                            dt = now - t_last_calc
                            if dt >= 0.5:
                                speed_bps = bytes_since_calc / dt
                                bytes_since_calc = 0
                                t_last_calc = now

                                remaining_bytes = max(0, total_bytes - downloaded_bytes)
                                eta = (remaining_bytes / speed_bps) if speed_bps > 0 else 0.0
                                percent = (downloaded_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0

                                if progress_callback:
                                    progress_callback(
                                        DownloadProgress(
                                            downloaded_bytes=downloaded_bytes,
                                            total_bytes=total_bytes,
                                            speed_bps=speed_bps,
                                            eta_seconds=eta,
                                            percent=percent,
                                        )
                                    )

                # If download completed, exit retry loop
                if total_bytes > 0 and downloaded_bytes >= total_bytes:
                    break
                elif self._is_cancelled:
                    return False
                else:
                    retries += 1
                    logger.warning(f"Connection closed at {downloaded_bytes}/{total_bytes} bytes. Resuming (attempt {retries}/{max_retries})...")
                    time.sleep(1.0)

            except Exception as e:
                retries += 1
                if retries >= max_retries or self._is_cancelled:
                    logger.error(f"Download failed after {retries} attempts: {e}")
                    raise
                logger.warning(f"Download interrupted ({e}). Resuming in 2s (attempt {retries}/{max_retries})...")
                time.sleep(2.0)

        if self._is_cancelled:
            logger.warning("Download cancelled by user.")
            return False

        # Verify completed before renaming
        actual_size = part_file.stat().st_size if part_file.exists() else 0
        if expected_size and actual_size < expected_size:
            raise IOError(f"Incomplete download: {actual_size} of {expected_size} bytes received.")

        # Safe rename with retry for Windows indexer/antivirus locks
        if part_file.exists():
            for attempt in range(10):
                try:
                    if dest_file.exists():
                        dest_file.unlink()
                    os.replace(str(part_file), str(dest_file))
                    logger.info(f"Download completed and verified: {dest_file}")
                    return True
                except PermissionError:
                    time.sleep(0.5)

            # Fallback copy and remove
            shutil.copy2(str(part_file), str(dest_file))
            try:
                part_file.unlink()
            except Exception:
                pass
            return True

        return False
