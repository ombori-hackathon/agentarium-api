from datetime import datetime
from pydantic import BaseModel


class Folder(BaseModel):
    """Folder in filesystem layout"""
    path: str
    name: str
    depth: int
    file_count: int


class File(BaseModel):
    """File in filesystem layout"""
    path: str
    name: str
    folder: str
    size: int


class FilesystemLayout(BaseModel):
    """Complete filesystem layout"""
    root: str
    folders: list[Folder]
    files: list[File]
    scanned_at: datetime
