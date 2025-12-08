import time
import random
from typing import Callable, Any


class MockSpatialResults:
    def __init__(self):
        self.precision: int = 3
        self._d_4sigma_x: float = 0.0
        self._d_4sigma_y: float = 0.0

    @property
    def d_4sigma_x(self) -> float:
        return self._d_4sigma_x

    @property
    def d_4sigma_y(self) -> float:
        return self._d_4sigma_y

    def update(self):
        # Generate mock beam width measurements with some realistic variation
        self._d_4sigma_x = random.uniform(0.5, 2.0)
        self._d_4sigma_y = random.uniform(0.5, 2.0)


class MockDataSource:
    def __init__(self):
        self._gain: float = 1.0
        self._exposure: float = 10.0
        self._is_running: bool = False

    @property
    def gain(self) -> float:
        return self._gain

    @gain.setter
    def gain(self, value: float):
        self._gain = value

    @property
    def exposure(self) -> float:
        return self._exposure

    @exposure.setter
    def exposure(self, value: float):
        self._exposure = value

    def start(self):
        self._is_running = True
        print("Mock data source started")

    def stop(self):
        self._is_running = False
        print("Mock data source stopped")

    def ultracal(self):
        print("Mock Ultracal calibration completed")


class MockSaveLoadSetup:
    def load_setup(self, filename: str):
        print(f"Mock loading setup from: {filename}")


class MockFrameEvents:
    def __init__(self):
        self._on_new_frame_handlers: list[Callable[[], None]] = []

    @property
    def OnNewFrame(self):
        return self

    def __iadd__(self, handler: Callable[[], None]):
        self._on_new_frame_handlers.append(handler)
        return self

    def __isub__(self, handler: Callable[[], None]):
        if handler in self._on_new_frame_handlers:
            self._on_new_frame_handlers.remove(handler)
        return self

    def trigger_new_frame(self):
        for handler in self._on_new_frame_handlers:
            try:
                handler()
            except Exception as e:
                print(f"Error in frame handler: {e}")


class BeamGagePy:
    def __init__(self, profile: str, enable_logging: bool):
        self.profile = profile
        self.enable_logging = enable_logging
        self.spatial_results = MockSpatialResults()
        self.data_source = MockDataSource()
        self.save_load_setup = MockSaveLoadSetup()
        self.frameevents = MockFrameEvents()
        self._is_shutdown: bool = False

        print(
            f"Mock BeamGagePy initialized with profile: {profile}, logging: {enable_logging}"
        )

    def shutdown(self):
        if not self._is_shutdown:
            self.data_source.stop()
            self._is_shutdown = True
            print("Mock BeamGagePy shutdown completed")
