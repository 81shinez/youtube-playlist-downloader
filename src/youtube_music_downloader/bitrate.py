from enum import Enum


class OutputMode(str, Enum):
    MP3_192 = "192"
    MP3_MAX = "max"

    @classmethod
    def from_api_value(cls, value: str) -> "OutputMode":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unsupported output mode: {value}") from exc


def choose_target_bitrate(mode: OutputMode, source_bitrate_kbps: int | None) -> int:
    if mode is OutputMode.MP3_192:
        return 192
    if mode is OutputMode.MP3_MAX:
        if source_bitrate_kbps is None:
            return 256
        return min(source_bitrate_kbps, 320)
    raise ValueError(f"Unsupported output mode: {mode}")
