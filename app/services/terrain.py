"""
Terrain calculation service for Agentarium.

This service calculates 3D positions for folders and files in a filesystem layout.
Folders are positioned in a spiral pattern, with elevation based on depth and file count.
Files are positioned around their parent folders.
"""

import math
from collections import defaultdict

from app.schemas.filesystem import Position, Folder, File, FilesystemLayout


def calculate_elevation(depth: int, file_count: int) -> float:
    """
    Calculate elevation (y-coordinate) for a folder based on depth and file count.

    Formula: elevation = (depth × 3.0) + log(file_count + 1) × 2.0

    Args:
        depth: How deep the folder is in the tree (root = 0)
        file_count: Number of files directly in the folder

    Returns:
        float: Elevation value (y-coordinate)
    """
    return (depth * 3.0) + math.log(file_count + 1) * 2.0


def calculate_folder_position(
    depth: int,
    folder_index: int,
    total_folders_at_depth: int,
    elevation: float
) -> Position:
    """
    Calculate position for a folder using spiral layout.

    Folders at the same depth are positioned in a circle around the origin.
    The radius increases with depth to spread out the folders.

    Args:
        depth: Folder depth in tree
        folder_index: Index of this folder among siblings at same depth
        total_folders_at_depth: Total number of folders at this depth
        elevation: Y-coordinate (from calculate_elevation)

    Returns:
        Position: 3D position for the folder
    """
    # Root folder is at origin
    if depth == 0:
        return Position(x=0.0, y=elevation, z=0.0)

    # Calculate angle for spiral distribution
    angle = folder_index * (2 * math.pi / total_folders_at_depth)

    # Radius increases with depth to spread out folders
    radius = depth * 15.0

    # Calculate x, z coordinates
    x = math.cos(angle) * radius
    z = math.sin(angle) * radius

    return Position(x=x, y=elevation, z=z)


def calculate_file_position(
    parent_position: Position,
    file_index: int,
    total_files_in_folder: int
) -> Position:
    """
    Calculate position for a file around its parent folder.

    Files are positioned in a circle around their parent folder.

    Args:
        parent_position: Position of the parent folder
        file_index: Index of this file among siblings
        total_files_in_folder: Total number of files in the folder

    Returns:
        Position: 3D position for the file
    """
    # Calculate angle for circular distribution around parent
    angle = file_index * (2 * math.pi / total_files_in_folder)

    # Fixed radius around parent folder
    file_radius = 3.0

    # Calculate offset from parent
    x_offset = math.cos(angle) * file_radius
    z_offset = math.sin(angle) * file_radius

    # Position file slightly above parent (0.5 units)
    return Position(
        x=parent_position.x + x_offset,
        y=parent_position.y + 0.5,
        z=parent_position.z + z_offset
    )


def calculate_folder_height(file_count: int) -> float:
    """
    Calculate the height (size) of a folder pyramid based on file count.

    Formula: height = 2.0 + log(file_count + 1)

    Args:
        file_count: Number of files in the folder

    Returns:
        float: Height value for rendering the pyramid
    """
    return 2.0 + math.log(file_count + 1)


def calculate_positions_for_layout(layout: FilesystemLayout) -> FilesystemLayout:
    """
    Calculate positions for all folders and files in a filesystem layout.

    This function:
    1. Groups folders by depth
    2. Calculates positions for each folder using spiral layout
    3. Calculates positions for each file around its parent folder

    Args:
        layout: Filesystem layout without positions

    Returns:
        FilesystemLayout: Layout with positions calculated for all folders and files
    """
    # Group folders by depth for spiral layout
    folders_by_depth: dict[int, list[Folder]] = defaultdict(list)
    for folder in layout.folders:
        folders_by_depth[folder.depth].append(folder)

    # Calculate positions for folders
    positioned_folders: list[Folder] = []
    folder_positions: dict[str, Position] = {}  # path -> position mapping

    # Add root position for files in root directory
    folder_positions[layout.root] = Position(x=0.0, y=0.0, z=0.0)

    for depth in sorted(folders_by_depth.keys()):
        folders_at_depth = folders_by_depth[depth]
        total_at_depth = len(folders_at_depth)

        for index, folder in enumerate(folders_at_depth):
            # Calculate elevation
            elevation = calculate_elevation(folder.depth, folder.file_count)

            # Calculate position
            position = calculate_folder_position(
                depth=folder.depth,
                folder_index=index,
                total_folders_at_depth=total_at_depth,
                elevation=elevation
            )

            # Calculate height for rendering
            height = calculate_folder_height(folder.file_count)

            # Store position for file placement
            folder_positions[folder.path] = position

            # Create updated folder with position and height
            positioned_folder = Folder(
                path=folder.path,
                name=folder.name,
                depth=folder.depth,
                file_count=folder.file_count,
                position=position,
                height=height
            )
            positioned_folders.append(positioned_folder)

    # Group files by parent folder
    files_by_folder: dict[str, list[File]] = defaultdict(list)
    for file in layout.files:
        files_by_folder[file.folder].append(file)

    # Calculate positions for files
    positioned_files: list[File] = []
    for folder_path, files in files_by_folder.items():
        # Get parent folder position
        parent_position = folder_positions.get(folder_path)

        # If parent folder not found (shouldn't happen), skip these files
        if parent_position is None:
            continue

        total_files = len(files)
        for index, file in enumerate(files):
            # Calculate position around parent
            position = calculate_file_position(
                parent_position=parent_position,
                file_index=index,
                total_files_in_folder=total_files
            )

            # Create updated file with position
            positioned_file = File(
                path=file.path,
                name=file.name,
                folder=file.folder,
                size=file.size,
                position=position
            )
            positioned_files.append(positioned_file)

    # Return updated layout
    return FilesystemLayout(
        root=layout.root,
        folders=positioned_folders,
        files=positioned_files,
        scanned_at=layout.scanned_at
    )
