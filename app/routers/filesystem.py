import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from app.schemas.filesystem import FilesystemLayout, Folder, File

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])


@router.get("", response_model=FilesystemLayout)
async def get_filesystem(path: str = Query(..., description="Root path to scan")):
    """
    Scan a directory and return its structure
    """
    root_path = Path(path)

    # Validate path exists
    if not root_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if not root_path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory")

    folders: list[Folder] = []
    files: list[File] = []

    # Calculate depth of root for relative depth calculation
    root_depth = len(root_path.parts)

    # Walk the directory tree
    for dirpath, dirnames, filenames in os.walk(root_path):
        current_path = Path(dirpath)
        current_depth = len(current_path.parts) - root_depth

        # Add subdirectories as folders (skip root itself)
        if current_path != root_path:
            # Count files in this directory only (not recursive)
            file_count = len([f for f in current_path.iterdir() if f.is_file()])

            folders.append(Folder(
                path=str(current_path),
                name=current_path.name,
                depth=current_depth,
                file_count=file_count
            ))

        # Add files
        for filename in filenames:
            file_path = current_path / filename
            try:
                file_size = file_path.stat().st_size

                files.append(File(
                    path=str(file_path),
                    name=filename,
                    folder=str(current_path),
                    size=file_size
                ))
            except (OSError, PermissionError):
                # Skip files we can't access
                continue

    return FilesystemLayout(
        root=str(root_path),
        folders=folders,
        files=files,
        scanned_at=datetime.now(timezone.utc)
    )
