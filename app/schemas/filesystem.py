from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class Position(BaseModel):
    """3D position in space"""
    x: float
    y: float
    z: float


class Folder(BaseModel):
    """Folder in filesystem layout"""
    path: str
    name: str
    depth: int
    file_count: int
    position: Optional[Position] = None
    height: Optional[float] = None


class File(BaseModel):
    """File in filesystem layout"""
    path: str
    name: str
    folder: str
    size: int
    position: Optional[Position] = None


class FilesystemLayout(BaseModel):
    """Complete filesystem layout"""
    root: str
    folders: list[Folder]
    files: list[File]
    scanned_at: datetime
