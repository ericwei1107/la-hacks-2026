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
    llm: str = "local"
    anthropic_round_model: str = "claude-haiku-5-5"
    anthropic_chat_model: str = "claude-opus-5-5"

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
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()
        wanted = os.getenv("KUMITE_LLM", "auto").strip().lower()
        if wanted not in {"auto", "openai", "anthropic", "claude", "local"}:
            raise ValueError("KUMITE_LLM must be auto, openai, anthropic or local")
        llm = "local"
        if mode == "auto" and wanted != "local":
            if wanted in {"anthropic", "claude"} and anthropic_key:
                llm = "anthropic"
            elif wanted == "openai" and api_key:
                llm = "openai"
            elif wanted == "auto":
                llm = "anthropic" if anthropic_key else "openai" if api_key else "local"
        return cls(
            data_dir=data_dir.resolve(),
            version=version,
            mode=mode,
            api_key=api_key,
            model=os.getenv("OPENAI_COACH_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini",
            llm=llm,
            anthropic_round_model=os.getenv("ANTHROPIC_COACH_MODEL", "").strip() or "claude-haiku-5-5",
            anthropic_chat_model=os.getenv("ANTHROPIC_CHAT_MODEL", "").strip() or "claude-opus-5-5",
        )
