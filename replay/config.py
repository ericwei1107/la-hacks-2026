import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    version: str
    mode: str
    api_key: str = field(repr=False)
    model: str

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser()
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        version = os.getenv("KUMITE_VERSION", "").strip()
        if not version:
            try:
                version = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT,
                    text=True, stderr=subprocess.DEVNULL, timeout=2,
                ).strip()
            except (OSError, subprocess.SubprocessError):
                version = "unknown"
        mode = os.getenv("KUMITE_COACH_MODE", "auto").strip().lower()
        if mode not in {"auto", "local"}:
            raise ValueError("KUMITE_COACH_MODE must be auto or local")
        return cls(
            data_dir=data_dir.resolve(),
            version=version,
            mode=mode,
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_COACH_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini",
        )
