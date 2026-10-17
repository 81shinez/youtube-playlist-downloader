"""Read only the legal documents shipped with the application, without network access."""
import sys
from pathlib import Path


PRIMARY_FILES = (
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'licenses/LGPL-3.0.txt',
    'licenses/GPL-3.0.txt',
    'licenses/SOURCES.md',
    'docs/DISTRIBUTION.md',
)


def resource_root() -> Path:
    if getattr(sys, 'frozen', False) and getattr(sys, '_MEIPASS', None):
        root = Path(sys._MEIPASS).resolve()
        # PyInstaller macOS bundles separate data from binaries in Frameworks.
        if sys.platform == 'darwin' and root.name == 'Frameworks' and root.parent.name == 'Contents':
            resources = root.parent / 'Resources'
            if resources.is_dir():
                return resources
        return root
    return Path(__file__).resolve().parents[2]


class LegalResources:
    def __init__(self, root: Path | None = None):
        self.root = (Path(root) if root is not None else resource_root()).resolve()

    def _path(self, name: str) -> Path | None:
        relative = Path(name)
        if relative.is_absolute() or relative.drive or relative.root or '..' in relative.parts:
            return None
        if ':' in name or '\x00' in name:
            return None
        in_licenses = bool(relative.parts) and relative.parts[0] == 'licenses'
        if not in_licenses and relative.as_posix() not in PRIMARY_FILES:
            return None
        path = (self.root / relative).resolve()
        if in_licenses:
            if not path.is_relative_to(self.root / 'licenses'):
                return None
        elif path != self.root / relative:
            return None
        return path

    def names(self) -> list[str]:
        names = set(PRIMARY_FILES)
        pending = ['licenses']
        visited = set()
        while pending:
            name = pending.pop()
            try:
                directory = self._path(name)
                if directory is None or directory in visited:
                    continue
                visited.add(directory)
                for child in directory.iterdir():
                    try:
                        child_name = child.relative_to(self.root).as_posix()
                        path = self._path(child_name)
                        if path is None:
                            continue
                        if path.is_dir():
                            pending.append(child_name)
                        elif path.is_file():
                            names.add(child_name)
                    except (OSError, RuntimeError):
                        continue
            except (OSError, RuntimeError):
                continue
        return list(PRIMARY_FILES) + sorted(names.difference(PRIMARY_FILES), key=str.casefold)

    def read(self, name: str) -> str:
        unavailable = f'Legal resource unavailable: {name}\nThe file is missing, unreadable, or not a bundled plain-text legal document.'
        try:
            path = self._path(name)
            if path is None or not path.is_file():
                return unavailable
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            return unavailable if '\x00' in text else text
        except (OSError, RuntimeError, ValueError):
            return unavailable
