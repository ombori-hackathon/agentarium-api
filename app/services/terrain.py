"""
Terrain calculation service for Agentarium.

This service calculates 3D positions for folders and files in a filesystem layout.
Folders are positioned in a spiral pattern, with elevation based on depth and file count.
Files are positioned around their parent folders.
"""

import math
import random
from collections import defaultdict

from app.schemas.filesystem import Position, Folder, File, FilesystemLayout


def calculate_elevation(depth: int, file_count: int) -> float:
    """
    Calculate elevation (y-coordinate) for a folder.

    All folders sit on the floor (y=0). Height varies by depth/file_count
    but position is always ground level.

    Args:
        depth: How deep the folder is in the tree (root = 0)
        file_count: Number of files directly in the folder

    Returns:
        float: Elevation value (y-coordinate) - always 0
    """
    return 0.0


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
    total_files_in_folder: int,
    seed: int
) -> Position:
    """
    Calculate organic file position around parent folder.
    Uses deterministic randomness based on seed (hash of file path).

    Args:
        parent_position: Position of the parent folder
        file_index: Index of this file among siblings
        total_files_in_folder: Total number of files in the folder
        seed: Seed for deterministic randomness

    Returns:
        Position: 3D position for the file
    """
    # Set random seed for deterministic positioning
    random.seed(seed)

    # Calculate angle with jitter for organic look
    angle = file_index * (2 * math.pi / max(total_files_in_folder, 1)) + random.uniform(-0.3, 0.3)

    # Radius with slight variation
    radius = 3.0 + random.uniform(-1.0, 1.0)

    # Calculate offset from parent
    x_offset = math.cos(angle) * radius
    z_offset = math.sin(angle) * radius

    # Y position with slight variation
    y_position = random.uniform(0.3, 0.7)

    return Position(
        x=parent_position.x + x_offset,
        y=y_position,
        z=parent_position.z + z_offset
    )


def calculate_total_contents(
    folder_path: str,
    folder_children: dict[str, list[Folder]],
    files_by_folder: dict[str, list[File]]
) -> int:
    """
    Calculate total files + subfolders recursively.

    Args:
        folder_path: Path of the folder to calculate for
        folder_children: Map of folder paths to their child folders
        files_by_folder: Map of folder paths to their files

    Returns:
        int: Total count of all files and subfolders recursively
    """
    direct_files = len(files_by_folder.get(folder_path, []))
    children = folder_children.get(folder_path, [])
    recursive_total = direct_files + len(children)

    for child in children:
        recursive_total += calculate_total_contents(child.path, folder_children, files_by_folder)

    return recursive_total


def calculate_folder_height(total_contents: int, max_contents: int) -> float:
    """
    Calculate height based on total contents.
    Range: 2.0 (empty) to 10.0 (root/largest)
    Uses logarithmic scale for visual balance.

    Args:
        total_contents: Total recursive count of files + folders
        max_contents: Maximum total_contents value (typically root folder)

    Returns:
        float: Height value for rendering the pyramid (2.0 to 10.0)
    """
    if max_contents <= 0:
        return 2.0
    normalized = math.log(total_contents + 1) / math.log(max_contents + 1)
    return 2.0 + 8.0 * normalized


def calculate_positions_for_layout(layout: FilesystemLayout) -> FilesystemLayout:
    """
    Calculate positions for all folders and files in a filesystem layout.

    This function implements mountain range clustering:
    1. Top-level folders (depth 1) form a ring around origin
    2. Nested folders (depth 2+) cluster near their parent (mountain ranges)
    3. Deeper nesting creates higher elevation (mountain peaks)

    Args:
        layout: Filesystem layout without positions

    Returns:
        FilesystemLayout: Layout with positions calculated for all folders and files
    """
    # Build parent-child relationships
    folder_children: dict[str, list[Folder]] = defaultdict(list)
    folders_by_path: dict[str, Folder] = {}

    for folder in layout.folders:
        folders_by_path[folder.path] = folder

        # Determine parent path
        parent_path = "/".join(folder.path.rsplit("/", 1)[:-1])
        if not parent_path:
            parent_path = layout.root
        folder_children[parent_path].append(folder)

    # Group files by parent folder (needed for total_contents calculation)
    files_by_folder: dict[str, list[File]] = defaultdict(list)
    for file in layout.files:
        files_by_folder[file.folder].append(file)

    # Calculate total_contents for all folders
    folder_total_contents: dict[str, int] = {}
    for folder in layout.folders:
        folder_total_contents[folder.path] = calculate_total_contents(
            folder.path, folder_children, files_by_folder
        )

    # Find max_contents for logarithmic height calculation
    max_contents = max(folder_total_contents.values()) if folder_total_contents else 1

    # Calculate positions depth-first
    positioned_folders: list[Folder] = []
    folder_positions: dict[str, Position] = {}  # path -> position mapping

    # Add root position for files in root directory
    folder_positions[layout.root] = Position(x=0.0, y=0.0, z=0.0)

    def position_folder_and_children(folder: Folder, parent_position: Position, sibling_index: int, sibling_count: int, parent_folder_path: str):
        """Recursively position a folder and its children"""
        # Calculate elevation
        elevation = calculate_elevation(folder.depth, folder.file_count)

        # Calculate position based on depth
        if folder.depth == 1:
            # Top-level folders in circle around origin
            angle = sibling_index * (2 * math.pi / sibling_count)
            radius = 20.0
            position = Position(
                x=math.cos(angle) * radius,
                y=elevation,
                z=math.sin(angle) * radius
            )
        else:
            # Nested folders: cluster near parent
            angle = sibling_index * (2 * math.pi / sibling_count) if sibling_count > 0 else 0
            cluster_radius = 5.0
            position = Position(
                x=parent_position.x + math.cos(angle) * cluster_radius,
                y=elevation,
                z=parent_position.z + math.sin(angle) * cluster_radius
            )

        # Get total contents and calculate height using logarithmic formula
        total_contents = folder_total_contents.get(folder.path, 0)
        height = calculate_folder_height(total_contents, max_contents)

        # Store position for file placement and children
        folder_positions[folder.path] = position

        # Create positioned folder with new fields
        positioned_folder = Folder(
            path=folder.path,
            name=folder.name,
            depth=folder.depth,
            file_count=folder.file_count,
            position=position,
            height=height,
            total_contents=total_contents,
            parent_path=parent_folder_path if parent_folder_path != layout.root else None
        )
        positioned_folders.append(positioned_folder)

        # Recursively position children
        children = folder_children.get(folder.path, [])
        for child_index, child in enumerate(children):
            position_folder_and_children(child, position, child_index, len(children), folder.path)

    # Start with top-level folders (depth 1)
    top_level = folder_children.get(layout.root, [])
    for index, folder in enumerate(top_level):
        position_folder_and_children(folder, folder_positions[layout.root], index, len(top_level), layout.root)

    # Calculate positions for files using organic scattering
    positioned_files: list[File] = []
    for folder_path, files in files_by_folder.items():
        # Get parent folder position
        parent_position = folder_positions.get(folder_path)

        # If parent folder not found (shouldn't happen), skip these files
        if parent_position is None:
            continue

        total_files = len(files)
        for index, file in enumerate(files):
            # Use file path hash as seed for deterministic randomness
            seed = hash(file.path)

            # Calculate position around parent with organic scattering
            position = calculate_file_position(
                parent_position=parent_position,
                file_index=index,
                total_files_in_folder=total_files,
                seed=seed
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
