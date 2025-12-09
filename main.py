import sys
import time
import clr  # Requires: pip install pythonnet
from stage import NewportStage
from typing import List

# ==========================================
# CONFIGURATION
# ==========================================
MOTOR_PORT: str = "COM5"
MOTOR_BAUD: int = 921600  # according to "CONEX-CC Single-Axis DC Motion Controller Documentation"

# TODO: Verify this path matches your installed version of BeamGage.
BEAMGAGE_DLL_PATH: str = r"C:\Program Files\Spiricon\BeamGage Professional\Automation\Spiricon.Automation.dll"

# Number of frames to average per position
READINGS_TO_AVERAGE: int = 100




class BeamGageCamera:
    """Handles Ophir BeamGage Automation via .NET interop."""

    def __init__(self, dll_path: str) -> None:
        print("[Camera] Initializing BeamGage Automation...")
        if not self._load_dotnet(dll_path):
            sys.exit(1)

        try:
            import Spiricon.Automation as SA  # type: ignore

            # True = launch application if not running
            self.bg = SA.AutomatedBeamGage(True)
            self.bg.Instance.Start()
            print("[Camera] Connected.")
        except Exception as e:
            print(f"[Camera] Connection Failed: {e}")
            sys.exit(1)

    def _load_dotnet(self, path: str) -> bool:
        try:
            sys.path.append(path)
            clr.AddReference(path)  # type: ignore
            return True
        except Exception:
            print(f"[Camera] Failed to load DLL at: {path}")
            return False

    def perform_ultracal(self) -> None:
        """
        Runs the Ultracal routine to zero background noise.
        Requres user interaction.
        """
        print("\n--- CALIBRATION REQUIRED ---")
        input("1. BLOCK the laser beam.\n2. Press [Enter]...")

        print("[Camera] Running Ultracal...")
        self.bg.Instance.Calibration.Ultracal()

        input("3. UNBLOCK the laser beam.\n4. Press [Enter]...")
        print("--- CALIBRATION COMPLETE ---\n")

    def get_average_reading(self, count: int) -> float:
        """
        Collects 'count' valid frames and returns average D4Sigma Width.
        """
        print(f"[Camera] Acquiring {count} frames...")
        readings: List[float] = []

        # Ensure stream is active
        self.bg.Instance.Start()

        while len(readings) < count:
            try:
                # D4SigmaWidth is the ISO standard calculation
                val = self.bg.Instance.Results.Simple.D4SigmaWidth
                if val > 0:
                    readings.append(val)
            except Exception:
                pass  # Ignore frames where calculation failed

            time.sleep(0.05)

        return sum(readings) / len(readings)


# ==========================================
# MAIN
# ==========================================


def main() -> None:
    print("--- Laser Characterization Script ---")

    stage = NewportStage(MOTOR_PORT, MOTOR_BAUD)
    cam = BeamGageCamera(BEAMGAGE_DLL_PATH)

    # 1. Manual Setup (Gain/Exposure)
    # TODO: This relies on the user looking at the BeamGage GUI window manually
    print("\n[Setup] Please adjust Gain/Exposure in BeamGage now.")
    print("Ensure beam is visible but not saturated.")
    input("Press [Enter] when settings are ready...")

    # 2. Calibration
    cam.perform_ultracal()

    # 3. Measurement Loop
    print("\n[System] Ready for measurements.")

    while True:
        try:
            val = input("\n>> Enter Target Position (mm) or 'q' to quit: ")
            if val.lower() == "q":
                break

            target_mm = float(val)

            # Move
            stage.move_absolute(target_mm)

            # Wait for mechanical vibration to settle
            time.sleep(1.0)

            # Measure
            avg = cam.get_average_reading(READINGS_TO_AVERAGE)

            print(f"RESULT: Pos={target_mm}mm | AvgSize={avg:.4f}um")

        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break

    print("[System] Exiting.")


if __name__ == "__main__":
    main()
