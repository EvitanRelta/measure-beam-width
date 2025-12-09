import time


class NewportStage:
    """Mock implementation of NewportStage for testing without hardware."""

    def __init__(
        self, port: str, baud_rate: int, *, initial_position: float = 0.0
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.axis: int = 1
        self.position: float = float(initial_position)
        self._error: str = ""
        print(f"[MockStage] Pretending to connect to {port} at {baud_rate} baud.")

    def get_error(self) -> str:
        """Return any stored error message; empty string means no error."""
        return self._error

    def get_position(self) -> float:
        """Return the current mock position."""
        return self.position

    def move_absolute(self, target_mm: float) -> None:
        """Move directly to the requested position and store it."""
        try:
            target = float(target_mm)
        except (TypeError, ValueError):
            self._error = "Error Code: INVALID_TARGET"
            print("[MockStage] Move aborted. Target must be numeric.")
            return

        self._error = ""
        print(f"[MockStage] Moving from {self.position:.4f} mm to {target:.4f} mm...")
        time.sleep(1)
        self.position = target
        print(f"[MockStage] Reached {self.position:.4f} mm.")
