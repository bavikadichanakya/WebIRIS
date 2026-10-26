"""
CLI Model Downloader Script for Project IRIS
Downloads SmolLM3-3B GGUF model with progress reporting.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iris.setup.downloader import Downloader, DownloadProgress
from iris.setup.manifest import COMPONENTS_MANIFEST

def main():
    comp = COMPONENTS_MANIFEST["smollm3_3b_model"]
    url = comp.download_url
    dest = comp.installed_path
    expected_size = comp.approx_size_bytes

    print(f"Starting download of {comp.name}...", flush=True)
    print(f"Source URL: {url}", flush=True)
    print(f"Destination: {dest}", flush=True)
    print(f"Target Size: {expected_size / (1024*1024):.1f} MB", flush=True)

    downloader = Downloader()
    last_print_pct = -1

    def on_progress(p: DownloadProgress):
        nonlocal last_print_pct
        pct = int(p.percent)
        if pct != last_print_pct and pct % 5 == 0:
            last_print_pct = pct
            eta_str = f"{int(p.eta_seconds)}s" if p.eta_seconds > 0 else "-"
            print(f"[{pct}%] {p.downloaded_mb:.1f}/{p.total_mb:.1f} MB ({p.speed_mbps:.2f} MB/s) | ETA: {eta_str}", flush=True)

    try:
        success = downloader.download_file(
            url=url,
            dest_path=dest,
            expected_size=expected_size,
            progress_callback=on_progress,
        )
        if success:
            print("Download and verification complete!", flush=True)
            sys.exit(0)
        else:
            print("Download cancelled.", flush=True)
            sys.exit(1)
    except Exception as e:
        print(f"Download failed: {e}", flush=True)
        sys.exit(2)

if __name__ == "__main__":
    main()
