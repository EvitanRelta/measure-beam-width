import time
import statistics
import configparser
import mock_beamgagepy as beamgagepy

# import beamgagepy


MOTOR_PORT: str = "COM5"
MOTOR_BAUD: int = 921600  # according to "CONEX-CC Single-Axis DC Motion Controller Documentation"
BGSETUP_PATH: str = "./automation.bgsetup"


def main() -> None:
    beamgage = beamgagepy.BeamGagePy("camera", True)

    # Use full precision. Default is 3 dp. We set it to 15 (standard double precision).
    beamgage.spatial_results.precision = 15

    beamgage.data_source.stop()

    try:
        # Restores computational methods (e.g. ISO Clip levels) and camera config
        beamgage.save_load_setup.load_setup(BGSETUP_PATH)
    except Exception:
        pass

    # Read configuration from .ini file
    config = configparser.ConfigParser()
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

    try:
        num_samples = config.getint("config", "num-samples")

        for i, section in enumerate(measurement_sets, 1):
            print(f"\n--- {section} ({i}/{len(measurement_sets)}) ---")

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

            input("Unblock beam and press Enter to measure...")

            samples_x: list[float] = []
            samples_y: list[float] = []

            def sample_handler() -> None:
                # Prevent collecting more samples than needed
                if len(samples_x) >= num_samples:
                    return

                beamgage.spatial_results.update()
                samples_x.append(beamgage.spatial_results.d_4sigma_x)
                samples_y.append(beamgage.spatial_results.d_4sigma_y)
                print(f"Sample {len(samples_x)}/{num_samples}", end="\r")

            beamgage.frameevents.OnNewFrame += sample_handler
            beamgage.data_source.start()

            while len(samples_x) < num_samples:
                time.sleep(0.01)

            beamgage.data_source.stop()
            beamgage.frameevents.OnNewFrame -= sample_handler

            assert len(samples_x) == num_samples
            assert len(samples_y) == num_samples

            mean_x: float = statistics.mean(samples_x)
            mean_y: float = statistics.mean(samples_y)

            # Formatting to 9 decimal places to show the increased precision
            print(f"\nMean D4Sigma X: {mean_x:.9f} | Mean D4Sigma Y: {mean_y:.9f} (Count: {len(samples_x)})")

    finally:
        beamgage.shutdown()


if __name__ == "__main__":
    main()
