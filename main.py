import time
import statistics
import configparser
import ast
import sys
import csv
import os
from mock_beamgagepy import BeamGagePy  # from beamgagepy import BeamGagePy
from mock_stage import NewportStage  # from stage import NewportStage


MOTOR_PORT: str = "COM5"
MOTOR_BAUD: int = (
    921600  # according to "CONEX-CC Single-Axis DC Motion Controller Documentation"
)
BGSETUP_PATH: str = "./automation.bgsetup"
OUTPUT_CSV: str = "output.csv"


def main() -> None:
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
    measurement_sets = [
        section
        for section in config.sections()
        if section.startswith("measurement-set-")
    ]
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

        for i, section in enumerate(measurement_sets, 1):
            print(f"\n--- {section} ({i}/{len(measurement_sets)}) ---")

            # Add blank row before new measurement set (except for the first one)
            if i > 1:
                csv_writer.writerow(["", "", "", "", "", "", ""])
                csv_file.flush()

            try:
                gain_val: float = float(config[section]["gain"])
                exp_val: float = float(config[section]["exposure"])
                print(f"Gain: {gain_val}, Exposure: {exp_val}")
            except (KeyError, ValueError) as e:
                print(f"Invalid configuration in {section}: {e}")
                continue

            beamgage.data_source.gain = gain_val
            beamgage.data_source.exposure = exp_val

            print("Running Ultracal...")
            beamgage.data_source.ultracal()

            if sys.stdin is None or not sys.stdin.isatty():
                print("Unblock beam before measuring (no interactive input available).")
            else:
                input("Unblock beam and press Enter to measure...")

            positions_raw = config[section].get("absolute-positions", "")
            if not positions_raw:
                print(
                    f"No absolute-positions defined in {section}. Skipping this measurement set."
                )
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
                print(
                    f"No positions provided for {section}. Skipping this measurement set."
                )
                continue

            for position_index, position in enumerate(positions, 1):
                print(
                    f"\nMoving stage to position {position_index}/{len(positions)}: {position:.4f} mm"
                )
                stage.move_absolute(position)
                stage_error = stage.get_error()
                if stage_error:
                    print(
                        f"Stage error after move: {stage_error}. Skipping this position."
                    )
                    continue

                samples_x: list[float] = []
                samples_y: list[float] = []

                def sample_handler() -> None:
                    # Prevent collecting more samples than needed
                    if len(samples_x) >= num_samples:
                        return

                    beamgage.spatial_results.update()
                    samples_x.append(beamgage.spatial_results.d_4sigma_x)
                    samples_y.append(beamgage.spatial_results.d_4sigma_y)
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

                mean_x: float = statistics.mean(samples_x)
                mean_y: float = statistics.mean(samples_y)

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

                # Formatting to 9 decimal places to show the increased precision
                print(
                    f"Position {position:.4f} mm -> Mean D4Sigma X: {mean_x:.9f} | Mean D4Sigma Y: {mean_y:.9f} (Count: {len(samples_x)})"
                )

    finally:
        csv_file.close()
        beamgage.shutdown()


if __name__ == "__main__":
    main()
