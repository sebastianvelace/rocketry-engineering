"""Persistent, local artifacts produced by agent-facing engineering tools."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Artifact:
    id: str
    kind: str
    created_at: str
    media_type: str
    path: str
    metadata: dict[str, Any]


class ArtifactStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent / ".rocketry" / "artifacts"

    def save(
        self,
        *,
        kind: str,
        content: str | bytes,
        suffix: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        self.root.mkdir(parents=True, exist_ok=True)
        artifact_id = uuid.uuid4().hex
        data_path = self.root / f"{artifact_id}{suffix}"
        manifest_path = self.root / f"{artifact_id}.meta.json"
        payload = content.encode("utf-8") if isinstance(content, str) else content

        fd, temporary = tempfile.mkstemp(prefix=f".{artifact_id}-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, data_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

        artifact = Artifact(
            id=artifact_id,
            kind=kind,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            media_type=media_type,
            path=str(data_path.resolve()),
            metadata=metadata or {},
        )
        manifest_path.write_text(
            json.dumps(asdict(artifact), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        if not artifact_id or any(character not in "0123456789abcdef" for character in artifact_id):
            return None
        manifest_path = self.root / f"{artifact_id}.meta.json"
        if not manifest_path.is_file():
            return None
        try:
            return Artifact(**json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def list(self, *, limit: int = 100) -> list[Artifact]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if not self.root.is_dir():
            return []
        artifacts = []
        manifests = sorted(
            self.root.glob("*.meta.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for manifest_path in manifests:
            try:
                artifact = Artifact(
                    **json.loads(manifest_path.read_text(encoding="utf-8"))
                )
                data_path = Path(artifact.path).resolve()
                if self.root.resolve() not in data_path.parents or not data_path.is_file():
                    continue
                artifacts.append(artifact)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if len(artifacts) >= limit:
                break
        return artifacts
