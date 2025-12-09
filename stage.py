import time
import serial


class NewportStage:
    """
    Handles communication with Newport SMC100CC via Serial.
    """

    def __init__(self, port: str, baud_rate: int) -> None:
        self.axis: int = 1
        print(f"[Stage] Connecting to {port}...")
        self.ser = serial.Serial(
            port=port,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,
            rtscts=False,
            timeout=0.1,
        )
        self.ser.read_all()  # Flush garbage from buffer
        self._home()

    def _send_command(self, cmd_str: str) -> str:
        """
        Sends command formatted as [Axis][Command][Value].
        e.g., Input 'PA10.0' -> Sends '1PA10.0\\r\\n'
        """
        self.ser.write(f"{self.axis}{cmd_str}\r\n".encode("ascii"))
        # Small sleep required for controller processing time
        time.sleep(0.02)
        response = self.ser.readline().decode("ascii").strip()
        return response

    def _get_controller_state(self) -> str:
        """
        Parses 'TS' command to determine controller state.
        Returns the last 2 hex characters of the response.
        """
        resp = self._send_command("TS")
        # Response format: 1TSxxxxxx (where last 2 chars are the state in Hex)
        clean_resp = resp.replace(f"{self.axis}TS", "").strip()
        assert len(clean_resp) == 6, f"Expected 6 char controller state, got: '{clean_resp}'"
        return clean_resp[-2:]

    def _wait_for_ready(self, timeout: float = 30.0) -> None:
        """Blocks until state returns to a READY code (32-35)."""
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

    def _home(self) -> None:
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
