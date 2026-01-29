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
