import time
import statistics
import beamgagepy

def main() -> None:
    beamgage = beamgagepy.BeamGagePy("camera", True)
    
    beamgage.data_source.stop()
    
    try:
        beamgage.save_load_setup.load_setup("beammaker.bgsetup")
    except Exception:
        pass

    TOTAL_RUNS: int = 3
    SAMPLES_TARGET: int = 75

    try:
        for i in range(TOTAL_RUNS):
            print(f"\n--- Run {i + 1}/{TOTAL_RUNS} ---")

            try:
                gain_val: float = float(input("Enter Gain: "))
                exp_val: float = float(input("Enter Exposure: "))
            except ValueError:
                print("Invalid input.")
                continue

            beamgage.data_source.gain = gain_val
            beamgage.data_source.exposure = exp_val

            print("Running Ultracal...")
            beamgage.data_source.ultracal()

            input("Unblock beam and press Enter to measure...")
            
            samples_x: list[float] = []
            samples_y: list[float] = []

            def sample_handler() -> None:
                # Stop adding to list if we reached target to prevent huge overshoots
                if len(samples_x) >= SAMPLES_TARGET:
                    return
                
                beamgage.spatial_results.update()
                samples_x.append(beamgage.spatial_results.d_4sigma_x)
                samples_y.append(beamgage.spatial_results.d_4sigma_y)
                print(f"Sample {len(samples_x)}/{SAMPLES_TARGET}", end='\r')

            beamgage.frameevents.OnNewFrame += sample_handler
            beamgage.data_source.start()

            while len(samples_x) < SAMPLES_TARGET:
                time.sleep(0.01)

            beamgage.data_source.stop()
            beamgage.frameevents.OnNewFrame -= sample_handler

            # Ensure exactly SAMPLES_TARGET are used even if handler overshot
            final_x = samples_x[:SAMPLES_TARGET]
            final_y = samples_y[:SAMPLES_TARGET]

            mean_x: float = statistics.mean(final_x)
            mean_y: float = statistics.mean(final_y)
            
            print(f"\nMean D4Sigma X: {mean_x:.4f} | Mean D4Sigma Y: {mean_y:.4f} (Count: {len(final_x)})")

    finally:
        beamgage.shutdown()

if __name__ == "__main__":
    main()
