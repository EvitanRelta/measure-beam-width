import sys
import time
import clr  # Requires: pip install pythonnet
import serial  # Requires: pip install pyserial
from typing import Any, Final, List

# ==========================================
# CONFIGURATION
# ==========================================

# TODO: Check Windows Device Manager -> Ports to confirm the correct COM number.
MOTOR_PORT: Final[str] = "COM3"
MOTOR_BAUD: Final[int] = 57600

# TODO: Verify this path matches your installed version of BeamGage.
BEAMGAGE_DLL_PATH: Final[str] = r"C:\Program Files\Spiricon\BeamGage Professional\Automation\Spiricon.Automation.dll"

# Number of frames to average per position
READINGS_TO_AVERAGE: Final[int] = 100


class NewportStage:
    """
    Handles communication with Newport SMC100CC via Serial.
    """

    def __init__(self, port: str, baud_rate: int) -> None:
        self.axis: int = 1
        print(f"[Stage] Connecting to {port}...")

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=True,
                timeout=0.1,
            )
            self.ser.read_all()  # Flush garbage from buffer
        except serial.SerialException as e:
            print(f"[Stage] Critical Error: {e}")
            sys.exit(1)

    def _send_command(self, cmd_str: str) -> str:
        """
        Sends command formatted as [Axis][Command][Value].
        e.g., Input 'PA10.0' -> Sends '1PA10.0\\r\\n'
        """
        full_cmd = f"{self.axis}{cmd_str}\r\n"

        try:
            self.ser.write(full_cmd.encode("ascii"))
            # Small sleep required for controller processing time
            time.sleep(0.02)
            response = self.ser.readline().decode("ascii").strip()
            return response
        except Exception as e:
            print(f"[Stage] Comms Error: {e}")
            return ""

    def _get_controller_state(self) -> str:
        """
        Parses 'TS' command to determine controller state.
        Returns the last 2 hex characters of the response.
        """
        resp = self._send_command("TS")
        # Response format: 1TSxxxxxx (where last 2 chars are the state in Hex)
        clean_resp = resp.replace(f"{self.axis}TS", "").strip()

        if len(clean_resp) < 6:
            return "00"

        return clean_resp[-2:]

    def _wait_for_ready(self, timeout: float = 30.0) -> None:
        """
        Blocks until state returns to a READY code (32-35).
        """
        start = time.time()
        while (time.time() - start) < timeout:
            state = self._get_controller_state()

            # 32: Ready from Homing
            # 33: Ready from Moving
            # 34: Ready from Disable
            # 35: Ready from Jogging
            if state in ["32", "33", "34", "35"]:
                return

            # Check for Disable/Configuration states which imply failure
            if state in ["3C", "3D", "3E", "14"]:
                print(f"[Stage] Error: Controller entered state {state} during operation.")
                return

            time.sleep(0.1)

        print("[Stage] Warning: Operation Timed Out")

    def get_error(self) -> str:
        """
        Queries the controller for memorized errors using 'TE'.
        Returns empty string if no error.
        """
        resp = self._send_command("TE")
        clean_resp = resp.replace(f"{self.axis}TE", "").strip()

        if clean_resp != "@":
            return f"Error Code: {clean_resp}"
        return ""

    def get_position(self) -> float:
        """
        Queries current position using 'TP'.
        e.g., Response "1TP10.005" -> Returns 10.005
        """
        resp = self._send_command("TP")
        clean_resp = resp.replace(f"{self.axis}TP", "").strip()
        try:
            return float(clean_resp)
        except ValueError:
            return -999.0

    def home(self) -> None:
        """
        Performs homing using 'OR'.
        Required if controller is in 'Not Referenced' state (0A-11).
        """
        state = self._get_controller_state()

        # Check if already Ready (32-35)
        if state in ["32", "33", "34", "35"]:
            print("[Stage] Already Referenced (Ready). Skipping Homing.")
            return

        # Check if Moving (28) or Homing (1E, 1F)
        if state in ["28", "1E", "1F"]:
            print("[Stage] Stage is currently moving/homing. Waiting...")
            self._wait_for_ready()
            return

        # Not Referenced states (0A-11) require OR command
        print("[Stage] Homing (OR command)...")
        self._send_command("OR")

        self._wait_for_ready(timeout=60.0)
        print("[Stage] Homing Complete.")

    def move_absolute(self, target_mm: float) -> None:
        """
        Moves stage to target using 'PA'.
        Enforces Ready state check before moving.
        """
        # Verify we are allowed to move
        state = self._get_controller_state()
        if state not in ["32", "33", "34", "35"]:
            print(f"[Stage] Error: Cannot Move. Controller in state '{state}' (Not Ready).")
            return

        print(f"[Stage] Moving to {target_mm} mm...")
        self._send_command(f"PA{target_mm}")

        # Check for immediate rejection error
        err = self.get_error()
        if err:
            print(f"[Stage] Move Aborted. Controller Error: {err}")
            return

        # Wait for state machine to return to Ready
        self._wait_for_ready()

        # Confirm final position
        final_pos = self.get_position()
        print(f"[Stage] Reached {final_pos:.4f} mm.")


class BeamGageCamera:
    """
    Handles Ophir BeamGage Automation via .NET interop.
    """

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

    # Ensure stage is referenced before any moves
    stage.home()

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
