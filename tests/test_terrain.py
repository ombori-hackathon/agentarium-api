import math
import pytest

from app.services.terrain import (
    calculate_elevation,
    calculate_folder_position,
    calculate_file_position,
    calculate_positions_for_layout,
)
from app.schemas.filesystem import Folder, File, FilesystemLayout, Position
from datetime import datetime, timezone


class TestElevationFormula:
    """Tests for elevation calculation"""

    def test_root_folder_elevation(self):
        """Root folder (depth=0) should be at ground level"""
        elevation = calculate_elevation(depth=0, file_count=0)
        assert elevation == 0.0

    def test_depth_increases_elevation(self):
        """Deeper folders should be higher"""
        elev_depth_1 = calculate_elevation(depth=1, file_count=0)
        elev_depth_2 = calculate_elevation(depth=2, file_count=0)
        elev_depth_3 = calculate_elevation(depth=3, file_count=0)

        assert elev_depth_1 == 3.0  # 1 * 3.0 + log(1) * 2.0 = 3.0 + 0.0 = 3.0
        assert elev_depth_2 == 6.0  # 2 * 3.0 + log(1) * 2.0 = 6.0 + 0.0 = 6.0
        assert elev_depth_3 == 9.0  # 3 * 3.0 + log(1) * 2.0 = 9.0 + 0.0 = 9.0

    def test_file_count_increases_elevation(self):
        """More files should increase elevation slightly"""
        elev_0_files = calculate_elevation(depth=1, file_count=0)
        elev_10_files = calculate_elevation(depth=1, file_count=10)
        elev_100_files = calculate_elevation(depth=1, file_count=100)

        # All should be > 3.0 (base depth)
        assert elev_0_files == 3.0
        assert elev_10_files > elev_0_files
        assert elev_100_files > elev_10_files

        # Check specific values
        # 1 * 3.0 + log(11) * 2.0 ≈ 3.0 + 2.398 * 2.0 ≈ 7.796
        assert math.isclose(elev_10_files, 3.0 + math.log(11) * 2.0, rel_tol=1e-5)

    def test_elevation_formula_exact(self):
        """Test exact formula: elevation = (depth × 3.0) + log(file_count + 1) × 2.0"""
        depth = 2
        file_count = 50
        expected = (depth * 3.0) + math.log(file_count + 1) * 2.0

        result = calculate_elevation(depth, file_count)
        assert math.isclose(result, expected, rel_tol=1e-9)


class TestCoordinateCalculation:
    """Tests for coordinate positioning"""

    def test_root_folder_at_origin(self):
        """Root folder should be at origin"""
        position = calculate_folder_position(
            depth=0,
            folder_index=0,
            total_folders_at_depth=1,
            elevation=0.0
        )

        assert position.x == 0.0
        assert position.y == 0.0
        assert position.z == 0.0

    def test_depth_1_folders_form_circle(self):
        """Folders at depth 1 should form a circle at radius 15"""
        depth = 1
        elevation = 3.0
        radius = 15.0  # depth * 15

        # Test 4 folders at cardinal directions
        positions = [
            calculate_folder_position(depth, 0, 4, elevation),  # 0°
            calculate_folder_position(depth, 1, 4, elevation),  # 90°
            calculate_folder_position(depth, 2, 4, elevation),  # 180°
            calculate_folder_position(depth, 3, 4, elevation),  # 270°
        ]

        # All should be at same elevation
        for pos in positions:
            assert pos.y == elevation

        # Check distances from origin (should all be ~15)
        for pos in positions:
            distance = math.sqrt(pos.x**2 + pos.z**2)
            assert math.isclose(distance, radius, rel_tol=1e-5)

    def test_spiral_layout_no_overlap(self):
        """Folders at same depth should be evenly distributed"""
        total = 8
        positions = [
            calculate_folder_position(1, i, total, 3.0)
            for i in range(total)
        ]

        # Check angular spacing
        for i in range(total):
            expected_angle = i * (2 * math.pi / total)
            actual_angle = math.atan2(positions[i].z, positions[i].x)

            # Normalize angles to [0, 2π]
            if actual_angle < 0:
                actual_angle += 2 * math.pi

            assert math.isclose(actual_angle, expected_angle, rel_tol=1e-5)

    def test_file_positions_around_parent(self):
        """Files should be positioned around their parent folder"""
        parent_pos = Position(x=10.0, y=5.0, z=20.0)
        file_radius = 3.0

        # Test 4 files around parent
        positions = [
            calculate_file_position(parent_pos, 0, 4),
            calculate_file_position(parent_pos, 1, 4),
            calculate_file_position(parent_pos, 2, 4),
            calculate_file_position(parent_pos, 3, 4),
        ]

        # All files should be 0.5 units above parent
        for pos in positions:
            assert pos.y == parent_pos.y + 0.5

        # All files should be ~3 units from parent (x,z plane)
        for pos in positions:
            dx = pos.x - parent_pos.x
            dz = pos.z - parent_pos.z
            distance = math.sqrt(dx**2 + dz**2)
            assert math.isclose(distance, file_radius, rel_tol=1e-5)


class TestDeterminism:
    """Tests for deterministic position calculation"""

    def test_same_input_same_output(self):
        """Same inputs should always produce same positions"""
        depth, file_count = 2, 10
        elev1 = calculate_elevation(depth, file_count)
        elev2 = calculate_elevation(depth, file_count)
        assert elev1 == elev2

        pos1 = calculate_folder_position(1, 5, 10, 5.0)
        pos2 = calculate_folder_position(1, 5, 10, 5.0)
        assert pos1.x == pos2.x
        assert pos1.y == pos2.y
        assert pos1.z == pos2.z


class TestMountainClustering:
    """Tests for mountain range clustering behavior"""

    def test_nested_folders_cluster_near_parent(self):
        """Nested folders (depth 2+) should cluster near their parent, not in separate rings"""
        # Create a parent folder at depth 1 and two children at depth 2
        folders = [
            Folder(path="/src", name="src", depth=1, file_count=0),
            Folder(path="/src/utils", name="utils", depth=2, file_count=0),
            Folder(path="/src/models", name="models", depth=2, file_count=0),
        ]

        layout = FilesystemLayout(
            root="/",
            folders=folders,
            files=[],
            scanned_at=datetime.now(timezone.utc)
        )

        result = calculate_positions_for_layout(layout)

        # Get positions
        parent = next(f for f in result.folders if f.path == "/src")
        child1 = next(f for f in result.folders if f.path == "/src/utils")
        child2 = next(f for f in result.folders if f.path == "/src/models")

        # Children should be NEAR parent (within cluster radius ~5.0), not far away (30+ units)
        parent_to_child1 = math.sqrt(
            (child1.position.x - parent.position.x)**2 +
            (child1.position.z - parent.position.z)**2
        )
        parent_to_child2 = math.sqrt(
            (child2.position.x - parent.position.x)**2 +
            (child2.position.z - parent.position.z)**2
        )

        # Should be clustered within radius ~5.0, not scattered at radius 30
        assert parent_to_child1 <= 6.0, f"Child1 too far from parent: {parent_to_child1}"
        assert parent_to_child2 <= 6.0, f"Child2 too far from parent: {parent_to_child2}"

        # Children should be higher than parent (mountain peak effect)
        assert child1.position.y > parent.position.y
        assert child2.position.y > parent.position.y

    def test_depth_1_folders_form_outer_ring(self):
        """Top-level folders (depth 1) should form a ring at radius ~20"""
        folders = [
            Folder(path="/src", name="src", depth=1, file_count=0),
            Folder(path="/docs", name="docs", depth=1, file_count=0),
            Folder(path="/tests", name="tests", depth=1, file_count=0),
            Folder(path="/config", name="config", depth=1, file_count=0),
        ]

        layout = FilesystemLayout(
            root="/",
            folders=folders,
            files=[],
            scanned_at=datetime.now(timezone.utc)
        )

        result = calculate_positions_for_layout(layout)

        # All depth 1 folders should be at radius ~20 from origin
        for folder in result.folders:
            distance_from_origin = math.sqrt(
                folder.position.x**2 + folder.position.z**2
            )
            assert math.isclose(distance_from_origin, 20.0, rel_tol=0.1), \
                f"{folder.name} at distance {distance_from_origin}, expected ~20"

    def test_three_level_nesting_creates_mountain_peak(self):
        """Three levels of nesting should create progressively higher elevation (mountain peak)"""
        folders = [
            Folder(path="/src", name="src", depth=1, file_count=0),
            Folder(path="/src/components", name="components", depth=2, file_count=0),
            Folder(path="/src/components/ui", name="ui", depth=3, file_count=0),
        ]

        layout = FilesystemLayout(
            root="/",
            folders=folders,
            files=[],
            scanned_at=datetime.now(timezone.utc)
        )

        result = calculate_positions_for_layout(layout)

        # Get positions
        level1 = next(f for f in result.folders if f.path == "/src")
        level2 = next(f for f in result.folders if f.path == "/src/components")
        level3 = next(f for f in result.folders if f.path == "/src/components/ui")

        # Each level should be progressively higher
        assert level2.position.y > level1.position.y, "Level 2 should be higher than level 1"
        assert level3.position.y > level2.position.y, "Level 3 should be higher than level 2"

        # Level 2 should cluster near level 1
        dist_1_to_2 = math.sqrt(
            (level2.position.x - level1.position.x)**2 +
            (level2.position.z - level1.position.z)**2
        )
        assert dist_1_to_2 <= 6.0, f"Level 2 too far from level 1: {dist_1_to_2}"

        # Level 3 should cluster near level 2
        dist_2_to_3 = math.sqrt(
            (level3.position.x - level2.position.x)**2 +
            (level3.position.z - level2.position.z)**2
        )
        assert dist_2_to_3 <= 6.0, f"Level 3 too far from level 2: {dist_2_to_3}"


class TestLayoutIntegration:
    """Tests for full layout position calculation"""

    def test_calculate_positions_adds_positions_to_layout(self):
        """Ensure positions are added to all folders and files"""
        # Create a simple filesystem layout
        folders = [
            Folder(path="/src", name="src", depth=1, file_count=2),
            Folder(path="/tests", name="tests", depth=1, file_count=1),
        ]
        files = [
            File(path="/src/main.py", name="main.py", folder="/src", size=100),
            File(path="/src/utils.py", name="utils.py", folder="/src", size=200),
            File(path="/tests/test_main.py", name="test_main.py", folder="/tests", size=50),
        ]

        layout = FilesystemLayout(
            root="/",
            folders=folders,
            files=files,
            scanned_at=datetime.now(timezone.utc)
        )

        # Calculate positions
        result = calculate_positions_for_layout(layout)

        # Check all folders have positions
        assert len(result.folders) == 2
        for folder in result.folders:
            assert hasattr(folder, 'position')
            assert folder.position is not None
            assert hasattr(folder, 'height')
            assert folder.height > 0

        # Check all files have positions
        assert len(result.files) == 3
        for file in result.files:
            assert hasattr(file, 'position')
            assert file.position is not None

    def test_root_excluded_from_folders(self):
        """Root folder (depth=0) should not be in the folders list"""
        layout = FilesystemLayout(
            root="/",
            folders=[
                Folder(path="/src", name="src", depth=1, file_count=0),
            ],
            files=[],
            scanned_at=datetime.now(timezone.utc)
        )

        result = calculate_positions_for_layout(layout)

        # No depth=0 folders should exist
        for folder in result.folders:
            assert folder.depth > 0

    def test_files_grouped_by_folder(self):
        """Files should be positioned around their parent folder"""
        folders = [
            Folder(path="/src", name="src", depth=1, file_count=2),
        ]
        files = [
            File(path="/src/a.py", name="a.py", folder="/src", size=100),
            File(path="/src/b.py", name="b.py", folder="/src", size=100),
        ]

        layout = FilesystemLayout(
            root="/",
            folders=folders,
            files=files,
            scanned_at=datetime.now(timezone.utc)
        )

        result = calculate_positions_for_layout(layout)

        # Get parent folder position
        parent_folder = result.folders[0]
        parent_pos = parent_folder.position

        # Check files are near parent
        for file in result.files:
            dx = file.position.x - parent_pos.x
            dz = file.position.z - parent_pos.z
            distance = math.sqrt(dx**2 + dz**2)

            # Files should be ~3 units away
            assert math.isclose(distance, 3.0, rel_tol=1e-5)

            # Files should be 0.5 units above parent
            assert file.position.y == parent_pos.y + 0.5
