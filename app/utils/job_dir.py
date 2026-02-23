"""Context manager for temporary job directories with guaranteed cleanup."""

import os
import shutil
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def job_directory(job_id: str):
    """
    Create a temporary job directory and ensure cleanup.

    Args:
        job_id: Unique job identifier (UUID)

    Yields:
        Path to the job directory

    Example:
        with job_directory(job_id) as job_dir:
            # Process files in job_dir
            pass
        # Directory is automatically deleted
    """
    job_dir = Path(f"/tmp/job_{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        yield str(job_dir)
    finally:
        # Always cleanup, even on exception
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
