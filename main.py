import sys
import time
import clr  # Requires 'pip install pythonnet'
import serial  # Requires 'pip install pyserial'
from typing import Any, Final

# ==========================================
# CONFIGURATION CONSTANTS
# ==========================================

# MOTOR SETTINGS (Newport SMC100)
# Check Windows Device Manager -> Ports (COM & LPT) to find the correct number.
MOTOR_PORT: Final[str] = 'COM3'
MOTOR_BAUD: Final[int] = 57600
MOTOR_AXIS: Final[int] = 1  # Standard for single-axis controllers

# BEAMGAGE SETTINGS
# Path to the Automation DLL. This path is standard for BeamGage Professional.
# If you get a "Module not found" error, verify this file exists.
BEAMGAGE_DLL_PATH: Final[str] = r"C:\Program Files\Spiricon\BeamGage Professional\Automation\Spiricon.Automation.dll"

# Measurement Settings
READINGS_TO_AVERAGE: Final[int] = 100
TIMEOUT_SECONDS: Final[int] = 10

# ==========================================
# HARDWARE CLASSES
# ==========================================

class NewportStage:
    """
    Handles communication with the Newport SMC100 Controller via Serial/USB.
    """
    def __init__(self, port: str, baud_rate: int = 57600) -> None:
        self.axis: int = MOTOR_AXIS
        self.port: str = port
        
        print(f"[Stage] Connecting to {port}...")
        try:
            self.ser: serial.Serial = serial.Serial(
                port=port, 
                baudrate=baud_rate, 
                timeout=0.1
            )
            # Clear any garbage data in the buffer
            self.ser.read_all()
        except serial.SerialException as e:
            print(f"[Stage] Critical Error: Could not open {port}. {e}")
            sys.exit(1)

    def _send_command(self, cmd: str) -> str:
        """
        Internal helper: Sends an ASCII command to the controller and reads the response.
        Format: [AxisNumber][Command] e.g., "1PA10.0"
        """
        full_cmd: str = f'{self.axis}{cmd}\r\n'
        
        try:
            self.ser.write(full_cmd.encode('ascii'))
            time.sleep(0.05)  # Short delay to allow controller processing
            
            # Read response (stripping whitespace and newlines)
            response: str = self.ser.readline().decode('ascii').strip()
            return response
        except Exception as e:
            print(f"[Stage] Comms Error: {e}")
            return ""

    def get_position(self) -> float:
        """
        Queries the controller for the current position (TP command).
        """
        # Command: TP (Tell Position)
        response: str = self._send_command('TP')
        
        # Response format is usually "1TP10.005" or just "10.005" depending on mode.
        # We strip the "1TP" prefix if it exists.
        clean_resp: str = response.replace(f"{self.axis}TP", "").strip()
        
        try:
            return float(clean_resp)
        except ValueError:
            # If garbage data returned, return a safe fallback or raise
            return -999.0

    def move_absolute(self, target_mm: float) -> None:
        """
        Moves the stage to a specific position (mm) and blocks until arrival.
        """
        print(f"[Stage] Moving to {target_mm} mm...")
        
        # Command: PA (Position Absolute)
        self._send_command(f'PA{target_mm}')
        
        # --- Polling Loop ---
        # We check the position repeatedly until we are close to the target.
        # (Newport also has a 'TS' Tell Status command, but checking position is often simpler)
        while True:
            current_pos: float = self.get_position()
            
            # Check if we are within tolerance (0.005mm)
            if abs(current_pos - target_mm) < 0.005:
                print(f"[Stage] Target reached at {current_pos:.4f} mm.")
                break
            
            time.sleep(0.2)  # Don't flood the serial port


class BeamGageCamera:
    """
    Handles communication with Ophir BeamGage software via .NET Automation.
    """
    def __init__(self, dll_path: str) -> None:
        print("[Camera] Initializing BeamGage Automation...")
        
        if not self._load_dotnet_library(dll_path):
            sys.exit(1)

        try:
            # Import the namespace dynamically after CLR load
            import Spiricon.Automation as SA # type: ignore
            
            # Connect to BeamGage application. 
            # True = Launch application if it's not already running.
            self.bg_app: Any = SA.AutomatedBeamGage(True)
            self.bg_app.Instance.Start()
            print("[Camera] Connected successfully.")
            
        except Exception as e:
            print(f"[Camera] Connection Failed: {e}")
            print(" -> Tip: Ensure BeamGage Professional is installed.")
            sys.exit(1)

    def _load_dotnet_library(self, dll_path: str) -> bool:
        """Loads the C# .NET DLL into the Python memory space."""
        try:
            sys.path.append(dll_path)
            clr.AddReference(dll_path)
            return True
        except Exception as e:
            print(f"[Camera] DLL Load Error: {e}")
            print(f" -> Checked path: {dll_path}")
            return False

    def perform_ultracal(self) -> None:
        """
        Guide user through the Ultracal (background subtraction) process.
        This zeros the noise level of the CCD.
        """
        print("\n" + "="*40)
        print(" ACTION REQUIRED: ULTRACALIBRATION")
        print("="*40)
        input("1. BLOCK the laser beam completely.\n2. Press [Enter] to run Ultracal...")
        
        print("[Camera] Running Ultracal... please wait...")
        try:
            self.bg_app.Instance.Calibration.Ultracal()
            print("[Camera] Ultracal Finished.")
        except Exception as e:
            print(f"[Camera] Ultracal Error: {e}")
            
        input("3. UNBLOCK the laser beam.\n4. Press [Enter] to continue...")
        print("="*40 + "\n")

    def get_average_beam_width(self, num_readings: int) -> float:
        """
        Captures N frames and averages the beam width (D4 Sigma).
        """
        print(f"[Camera] Acquiring {num_readings} frames...")
        
        valid_readings: list[float] = []
        
        # Ensure camera is streaming
        self.bg_app.Instance.Start()
        
        # Loop until we have enough data
        while len(valid_readings) < num_readings:
            # Access the Results array from BeamGage
            # Note: 'Simple' provides easy access to standard ISO calculations
            try:
                # D4SigmaWidth is the ISO standard for laser beam width
                # This returns the width in microns (um) usually.
                width_val: float = self.bg_app.Instance.Results.Simple.D4SigmaWidth
                
                # Filter out bad reads (0 or negative)
                if width_val > 0:
                    valid_readings.append(width_val)
                    # Print progress on the same line
                    sys.stdout.write(f"\r -> Reading {len(valid_readings)}/{num_readings}: {width_val:.2f} um")
                    sys.stdout.flush()
            except Exception:
                # Sometimes results aren't ready immediately
                pass
            
            # Sync with camera framerate (approx 15-30Hz usually)
            time.sleep(0.05)
            
        print("") # Newline after loop
        
        average: float = sum(valid_readings) / len(valid_readings)
        return average


# ==========================================
# MAIN PROGRAM FLOW
# ==========================================

def main() -> None:
    print("--- Laser M2/Divergence Measurement Assistant ---")
    
    # 1. Initialize Objects
    stage = NewportStage(MOTOR_PORT, MOTOR_BAUD)
    camera = BeamGageCamera(BEAMGAGE_DLL_PATH)
    
    # 2. Setup Phase (Camera Settings)
    print("\n--- Phase 1: Manual Camera Setup ---")
    print("Please use the BeamGage window to adjust Exposure and Gain.")
    print("Ensure the beam is not saturated (red pixels).")
    input("Press [Enter] when settings are correct...")
    
    # 3. Ultracal Phase (Critical for CCDs)
    camera.perform_ultracal()
    
    # 4. Data Collection Loop
    print("\n--- Phase 2: Measurement Loop ---")
    
    try:
        while True:
            user_input: str = input("\n>> Enter Target Position (mm) or 'q' to quit: ")
            
            if user_input.lower().startswith('q'):
                print("Exiting loop.")
                break
            
            # Validate input
            try:
                target_mm = float(user_input)
            except ValueError:
                print("Error: Please enter a valid number.")
                continue
                
            # A. Move the Stage
            stage.move_absolute(target_mm)
            
            # Wait for mechanical vibrations to settle
            print("[System] Settling for 1 second...")
            time.sleep(1.0) 
            
            # B. Take Measurements
            avg_width = camera.get_average_beam_width(READINGS_TO_AVERAGE)
            
            # Output Result
            print(f"RESULT: Pos={target_mm}mm | AvgWidth={avg_width:.4f}um")
            
    except KeyboardInterrupt:
        print("\n[System] Interrupted by user.")
        
    finally:
        print("[System] Shutting down connection.")
        # Note: serial ports close automatically on object destruction,
        # but explicit cleanup code can go here if needed.

if __name__ == "__main__":
    main()
