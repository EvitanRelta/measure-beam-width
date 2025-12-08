import threading
import time
import random
from typing import Callable, Optional


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
    FRAME_INTERVAL_SECONDS: float = 2.0 / 75.0

    def __init__(self):
        self._gain: float = 1.0
        self._exposure: float = 10.0
        self._is_running: bool = False
        self._frame_events: Optional["MockFrameEvents"] = None
        self._frame_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

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

    def attach_frame_events(self, frame_events: "MockFrameEvents"):
        self._frame_events = frame_events

    def start(self):
        if self._is_running:
            return

        if self._frame_events is None:
            raise RuntimeError(
                "Frame events must be attached before starting the data source"
            )

        self._is_running = True
        self._stop_event.clear()
        self._frame_thread = threading.Thread(target=self._emit_frames, daemon=True)
        self._frame_thread.start()
        print("Mock data source started")

    def stop(self):
        if not self._is_running:
            return

        self._is_running = False
        self._stop_event.set()
        if self._frame_thread is not None:
            self._frame_thread.join(timeout=1.0)
            self._frame_thread = None
        print("Mock data source stopped")

    def ultracal(self):
        print("Mock Ultracal calibration completed")

    def _emit_frames(self):
        while not self._stop_event.is_set():
            if self._frame_events is not None:
                self._frame_events.trigger_new_frame()
            time.sleep(self.FRAME_INTERVAL_SECONDS)


class MockSaveLoadSetup:
    def load_setup(self, filename: str):
        print(f"Mock loading setup from: {filename}")


class MockFrameEvents:
    def __init__(self):
        self._on_new_frame_handlers: list[Callable[[], None]] = []

    @property
    def OnNewFrame(self):
        return self

    @OnNewFrame.setter
    def OnNewFrame(self, value: "MockFrameEvents"):
        # Allow augmented assignments (+=/-=) without reassigning the property
        pass

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
        self.frameevents = MockFrameEvents()
        self.data_source = MockDataSource()
        self.data_source.attach_frame_events(self.frameevents)
        self.save_load_setup = MockSaveLoadSetup()
        self._is_shutdown: bool = False

        print(
            f"Mock BeamGagePy initialized with profile: {profile}, logging: {enable_logging}"
        )

    def shutdown(self):
        if not self._is_shutdown:
            self.data_source.stop()
            self._is_shutdown = True
            print("Mock BeamGagePy shutdown completed")
