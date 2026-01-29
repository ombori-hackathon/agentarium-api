import pytest
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_directory():
    """Create a temporary directory structure for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test structure:
        # tmpdir/
        #   src/
        #     index.ts
        #     components/
        #       Button.tsx
        #   README.md

        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()

        components_dir = src_dir / "components"
        components_dir.mkdir()

        # Create files
        (src_dir / "index.ts").write_text("console.log('hello');")
        (components_dir / "Button.tsx").write_text("export const Button = () => {};")
        (Path(tmpdir) / "README.md").write_text("# Test Project")

        yield tmpdir


def test_get_filesystem_structure(client, temp_directory):
    """Test getting filesystem structure"""
    response = client.get(f"/api/filesystem?path={temp_directory}")

    assert response.status_code == 200
    data = response.json()

    # Check root
    assert data["root"] == temp_directory

    # Check folders
    assert len(data["folders"]) == 2  # src and src/components
    folder_paths = [f["path"] for f in data["folders"]]
    assert any("src" in path for path in folder_paths)
    assert any("components" in path for path in folder_paths)

    # Check files
    assert len(data["files"]) == 3  # index.ts, Button.tsx, README.md
    file_names = [f["name"] for f in data["files"]]
    assert "index.ts" in file_names
    assert "Button.tsx" in file_names
    assert "README.md" in file_names

    # Check timestamp
    assert "scanned_at" in data


def test_get_filesystem_folder_depths(client, temp_directory):
    """Test that folder depths are calculated correctly"""
    response = client.get(f"/api/filesystem?path={temp_directory}")

    assert response.status_code == 200
    data = response.json()

    # Find folders by name
    folders_by_name = {f["name"]: f for f in data["folders"]}

    assert folders_by_name["src"]["depth"] == 1
    assert folders_by_name["components"]["depth"] == 2


def test_get_filesystem_file_sizes(client, temp_directory):
    """Test that file sizes are included"""
    response = client.get(f"/api/filesystem?path={temp_directory}")

    assert response.status_code == 200
    data = response.json()

    # Check that all files have size > 0
    for file in data["files"]:
        assert file["size"] > 0


def test_get_filesystem_invalid_path(client):
    """Test getting filesystem with invalid path"""
    response = client.get("/api/filesystem?path=/nonexistent/path/12345")

    assert response.status_code == 404


def test_get_filesystem_missing_path(client):
    """Test getting filesystem without path parameter"""
    response = client.get("/api/filesystem")

    assert response.status_code == 422  # Validation error


def test_get_filesystem_file_folders(client, temp_directory):
    """Test that files correctly reference their parent folders"""
    response = client.get(f"/api/filesystem?path={temp_directory}")

    assert response.status_code == 200
    data = response.json()

    # Find files
    files_by_name = {f["name"]: f for f in data["files"]}

    # index.ts should be in /src
    assert "src" in files_by_name["index.ts"]["folder"]

    # Button.tsx should be in /src/components
    assert "components" in files_by_name["Button.tsx"]["folder"]

    # README.md should be in root
    assert files_by_name["README.md"]["folder"] == temp_directory


@pytest.fixture
def temp_directory_with_excluded():
    """Create a temporary directory with excluded directories"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test structure:
        # tmpdir/
        #   src/
        #     index.ts
        #   node_modules/
        #     package/
        #       index.js
        #   .git/
        #     config
        #   dist/
        #     bundle.js

        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        (src_dir / "index.ts").write_text("export default {};")

        node_modules = Path(tmpdir) / "node_modules"
        node_modules.mkdir()
        package_dir = node_modules / "package"
        package_dir.mkdir()
        (package_dir / "index.js").write_text("module.exports = {};")

        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")

        dist_dir = Path(tmpdir) / "dist"
        dist_dir.mkdir()
        (dist_dir / "bundle.js").write_text("bundled code")

        yield tmpdir


def test_get_filesystem_excludes_node_modules(client, temp_directory_with_excluded):
    """Test that node_modules is excluded from scanning"""
    response = client.get(f"/api/filesystem?path={temp_directory_with_excluded}")

    assert response.status_code == 200
    data = response.json()

    # Check that node_modules folders are not included
    folder_names = [f["name"] for f in data["folders"]]
    assert "node_modules" not in folder_names
    assert "package" not in folder_names  # nested inside node_modules

    # Check that files inside node_modules are not included
    file_paths = [f["path"] for f in data["files"]]
    assert not any("node_modules" in path for path in file_paths)


def test_get_filesystem_excludes_git(client, temp_directory_with_excluded):
    """Test that .git is excluded from scanning"""
    response = client.get(f"/api/filesystem?path={temp_directory_with_excluded}")

    assert response.status_code == 200
    data = response.json()

    # Check that .git folders are not included
    folder_names = [f["name"] for f in data["folders"]]
    assert ".git" not in folder_names

    # Check that files inside .git are not included
    file_paths = [f["path"] for f in data["files"]]
    assert not any(".git" in path for path in file_paths)


def test_get_filesystem_excludes_dist(client, temp_directory_with_excluded):
    """Test that dist is excluded from scanning"""
    response = client.get(f"/api/filesystem?path={temp_directory_with_excluded}")

    assert response.status_code == 200
    data = response.json()

    # Check that dist folders are not included
    folder_names = [f["name"] for f in data["folders"]]
    assert "dist" not in folder_names


def test_get_filesystem_includes_src(client, temp_directory_with_excluded):
    """Test that src folder is still included"""
    response = client.get(f"/api/filesystem?path={temp_directory_with_excluded}")

    assert response.status_code == 200
    data = response.json()

    # Check that src folder IS included
    folder_names = [f["name"] for f in data["folders"]]
    assert "src" in folder_names

    # Check that index.ts in src is included
    file_names = [f["name"] for f in data["files"]]
    assert "index.ts" in file_names


@pytest.fixture
def temp_directory_deep():
    """Create a deeply nested directory structure"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create 7 levels deep: root/a/b/c/d/e/f/g
        current = Path(tmpdir)
        for level in ['a', 'b', 'c', 'd', 'e', 'f', 'g']:
            current = current / level
            current.mkdir()
            (current / f"{level}.txt").write_text(f"level {level}")

        yield tmpdir


def test_get_filesystem_respects_depth_limit(client, temp_directory_deep):
    """Test that directories beyond MAX_DEPTH are not included"""
    response = client.get(f"/api/filesystem?path={temp_directory_deep}")

    assert response.status_code == 200
    data = response.json()

    # Check folder depths - should only go to depth 5
    folder_depths = [f["depth"] for f in data["folders"]]
    assert all(d <= 5 for d in folder_depths), f"Found folders deeper than 5: {folder_depths}"

    # Should have folders a, b, c, d, e (depths 1-5) but not f, g (depths 6, 7)
    folder_names = [f["name"] for f in data["folders"]]
    assert "a" in folder_names
    assert "e" in folder_names  # depth 5
    assert "f" not in folder_names  # depth 6 - should be excluded
    assert "g" not in folder_names  # depth 7 - should be excluded
