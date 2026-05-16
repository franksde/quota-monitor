from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProbeResult:
    """Output of a probe scan. Pure data; no decisions."""
    source: str                                  # "claude" | "codex"
    timestamps: tuple[float, ...]                # epoch seconds, sorted ascending
    extra: dict[str, object] = field(default_factory=dict)
