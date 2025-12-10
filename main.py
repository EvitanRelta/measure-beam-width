import time
import statistics
import configparser
import ast
import csv
import os
import math
import win32api
from mock_beamgagepy import BeamGagePy  # from beamgagepy import BeamGagePy
from mock_stage import NewportStage  # from stage import NewportStage


MOTOR_PORT: str = "COM5"
MOTOR_BAUD: int = 921600  # according to "CONEX-CC Single-Axis DC Motion Controller Documentation"
BGSETUP_PATH: str = "./automation.bgsetup"
OUTPUT_CSV: str = "output.csv"

# Global variables, used for cleanup
has_cleaned_up = False
beamgage = None
csv_file = None


def handle_shutdown():
    global has_cleaned_up, beamgage, csv_file
    if has_cleaned_up:
        return
    has_cleaned_up = True
    print("\n\nGracefully shutting down...")
    if csv_file is not None:
        csv_file.close()
    if beamgage is not None:
        beamgage.shutdown()
    print("Successfully shutdown\n")


# Handle Windows terminal 'X' close button
def win_handler(sig, func=None):
    if sig == 2:  # 2 is CTRL_CLOSE_EVENT
        handle_shutdown()
        return True
    return False


def prompt_for_float_value(field_name: str, section_name: str) -> float:
    while True:
        user_input = input(f"Enter {field_name} for {section_name}: ").strip()
        if not user_input:
            print("Input cannot be empty. Please enter a numeric value.")
            continue
        try:
            return float(user_input)
        except ValueError:
            print("Invalid number. Please enter a numeric value.")


def main() -> None:
    # Handle Windows terminal 'X' close button
    win32api.SetConsoleCtrlHandler(win_handler, True)

    global beamgage, csv_file
    beamgage = BeamGagePy("camera", True)
    stage = NewportStage(MOTOR_PORT, MOTOR_BAUD)

    # Use full precision. Default is 3 dp. We set it to 15 (standard double precision).
    beamgage.spatial_results.precision = 15

    beamgage.data_source.stop()

    try:
        # Restores computational methods (e.g. ISO Clip levels) and camera config
        beamgage.save_load_setup.load_setup(BGSETUP_PATH)
    except Exception:
        pass

    # Read configuration from .ini file. Preserve inline comments in config.ini values.
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    try:
        config.read("config.ini")
    except Exception as e:
        print(f"Error reading config.ini: {e}")
        return

    # Get all measurement-set sections
    measurement_sets = [section for section in config.sections() if section.startswith("measurement-set-")]
    if not measurement_sets:
        print("No measurement-set sections found in config.ini")
        return

    # Initialize CSV file
    csv_exists = os.path.exists(OUTPUT_CSV)
    csv_file = open(OUTPUT_CSV, "a", newline="")
    csv_writer = csv.writer(csv_file)

    if not csv_exists:
        csv_writer.writerow(
            [
                "Measurement Set",
                "Gain",
                "Exposure",
                "Sample Count",
                "Position (mm)",
                "Mean D4Sigma X",
                "Mean D4Sigma Y",
            ]
        )
    else:
        csv_writer.writerow(["", "", "", "", "", "", ""])
    csv_file.flush()

    try:
        num_samples = config.getint("config", "num-samples")
        num_output_decimals = config.getint("config", "num-output-decimals")

        if num_output_decimals < 0:
            print("num-output-decimals cannot be negative. Using 0.")
            num_output_decimals = 0

        for i, section in enumerate(measurement_sets, 1):
            print(f"\n--- {section} ({i}/{len(measurement_sets)}) ---")

            # Add blank row before new measurement set (except for the first one)
            if i > 1:
                csv_writer.writerow(["", "", "", "", "", "", ""])
                csv_file.flush()

            config_section = config[section]

            gain_val_raw = config_section.get("gain", fallback="").strip()
            gain_val: float
            if gain_val_raw:
                try:
                    gain_val = float(gain_val_raw)
                except ValueError:
                    print(f"Invalid gain value in {section}: {gain_val_raw}")
                    continue
            else:
                gain_val = prompt_for_float_value("gain", section)

            exp_val_raw = config_section.get("exposure", fallback="").strip()
            exp_val: float
            if exp_val_raw:
                try:
                    exp_val = float(exp_val_raw)
                except ValueError:
                    print(f"Invalid exposure value in {section}: {exp_val_raw}")
                    continue
            else:
                exp_val = prompt_for_float_value("exposure", section)

            print(f"Gain: {gain_val}, Exposure: {exp_val}")

            beamgage.data_source.gain = gain_val
            beamgage.data_source.exposure = exp_val

            print("Running Ultracal...")
            beamgage.data_source.ultracal()

            input("Unblock beam and press Enter to measure...")

            positions_raw = config[section].get("absolute-positions", "")
            if not positions_raw:
                print(f"No absolute-positions defined in {section}. Skipping this measurement set.")
                continue

            try:
                parsed_positions = ast.literal_eval(positions_raw)
                if not isinstance(parsed_positions, (list, tuple)):
                    raise ValueError("absolute-positions must be a list or tuple")
                positions = [float(pos) for pos in parsed_positions]
            except (ValueError, SyntaxError) as e:
                print(f"Invalid absolute-positions in {section}: {e}")
                continue

            if not positions:
                print(f"No positions provided for {section}. Skipping this measurement set.")
                continue

            for position_index, position in enumerate(positions, 1):
                print(f"\nMoving stage to position {position_index}/{len(positions)}: {position:.2f} mm")
                stage.move_absolute(position)
                stage_error = stage.get_error()
                if stage_error:
                    print(f"Stage error after move: {stage_error}. Skipping this position.")
                    continue

                samples_x: list[float] = []
                samples_y: list[float] = []
                zero_sample_count = 0
                nan_sample_count = 0

                def sample_handler() -> None:
                    nonlocal zero_sample_count, nan_sample_count
                    # Prevent collecting more samples than needed
                    if len(samples_x) >= num_samples:
                        return
                    assert beamgage is not None
                    beamgage.spatial_results.update()
                    d4sigma_x = beamgage.spatial_results.d_4sigma_x
                    d4sigma_y = beamgage.spatial_results.d_4sigma_y

                    invalid_sample = False
                    for value in (d4sigma_x, d4sigma_y):
                        if value == 0:
                            zero_sample_count += 1
                            invalid_sample = True
                        else:
                            try:
                                if math.isnan(value):
                                    nan_sample_count += 1
                                    invalid_sample = True
                            except TypeError:
                                pass

                    if invalid_sample:
                        return

                    samples_x.append(d4sigma_x)
                    samples_y.append(d4sigma_y)
                    print(
                        f"Position {position_index}: Sample {len(samples_x)}/{num_samples}",
                        end="\r",
                    )

                beamgage.frameevents.OnNewFrame += sample_handler
                beamgage.data_source.start()

                while len(samples_x) < num_samples:
                    time.sleep(0.01)

                beamgage.data_source.stop()
                beamgage.frameevents.OnNewFrame -= sample_handler

                print(
                    f"Position {position_index}: ignored {zero_sample_count} zero readings and {nan_sample_count} NaN readings"
                )

                mean_x: float = round(statistics.mean(samples_x), num_output_decimals)
                mean_y: float = round(statistics.mean(samples_y), num_output_decimals)

                # Write to CSV
                csv_writer.writerow(
                    [
                        section,
                        gain_val,
                        exp_val,
                        len(samples_x),
                        position,
                        mean_x,
                        mean_y,
                    ]
                )
                csv_file.flush()
                print(
                    f"Position {position:.2f} mm -> Mean D4Sigma X: {mean_x:.{num_output_decimals}f} | Mean D4Sigma Y: {mean_y:.{num_output_decimals}f} ({len(samples_x)} samples)"
                )

    finally:
        handle_shutdown()


if __name__ == "__main__":
    main()
