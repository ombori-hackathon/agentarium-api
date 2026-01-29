import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from app.schemas.filesystem import FilesystemLayout, Folder, File
from app.services.terrain import calculate_positions_for_layout
from app.services.agent import agent_service

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])

# Directories to exclude from filesystem scanning for performance
EXCLUDED_DIRS = {
    # Package managers
    'node_modules', '.pnpm', 'bower_components', 'vendor', 'packages',

    # Version control
    '.git', '.svn', '.hg',

    # Build outputs
    'dist', 'build', 'out', 'target', '.next', '.nuxt', '.output',

    # Caches
    '.cache', '__pycache__', '.pytest_cache', '.mypy_cache', '.tox',

    # Virtual environments
    '.venv', 'venv', 'env', '.env',

    # IDE/Editor
    '.idea', '.vscode',

    # Logs/temp
    'logs', 'tmp', 'temp', '.tmp',

    # Coverage/reports
    'coverage', '.nyc_output', 'htmlcov',
}

# Maximum depth to traverse (prevents deep recursion in nested projects)
MAX_DEPTH = 5


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

        # Filter out excluded directories (modifying in-place affects os.walk traversal)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        # Stop descending if we've reached max depth (but still process this folder)
        if current_depth >= MAX_DEPTH:
            dirnames.clear()  # Don't descend further

        # Add subdirectories as folders (skip root itself)
        if current_path != root_path:
            # Count files using filenames from os.walk (no extra filesystem call)
            file_count = len(filenames)

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

    # Create initial layout without positions
    layout = FilesystemLayout(
        root=str(root_path),
        folders=folders,
        files=files,
        scanned_at=datetime.now(timezone.utc)
    )

    # Calculate positions for all folders and files
    layout_with_positions = calculate_positions_for_layout(layout)

    # Store terrain layout in agent service for position lookups
    agent_service.set_terrain_layout(layout_with_positions)

    return layout_with_positions
