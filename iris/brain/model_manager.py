"""
Project IRIS - Model Manager
Controls the lifecycle, thread-safety, and execution of the local SmolLM3-3B brain.
"""

from __future__ import annotations

import concurrent.futures
import enum
import logging
import threading
from typing import Any, Callable, Dict, Generator, Iterator, Optional

from iris.brain.inference_backend import BackendFactory, InferenceBackend
from iris.core.config import ModelConfig
from iris.core.event_bus import EventBus, EventTopic

logger = logging.getLogger("iris.brain.model_manager")


class ModelStatus(str, enum.Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    LOADING = "LOADING"
    READY = "READY"
    GENERATING = "GENERATING"
    ERROR = "ERROR"


class ModelManager:
    """Manages SmolLM3-3B model instance, loading, and background inference."""

    def __init__(self, config: ModelConfig, bus: Optional[EventBus] = None) -> None:
        self.config = config
        self.bus = bus or EventBus()
        self._status = ModelStatus.NOT_CONFIGURED
        self._backend: Optional[InferenceBackend] = None
        self._lock = threading.RLock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="iris_model_thread"
        )
        self._error_message: Optional[str] = None

    @property
    def status(self) -> ModelStatus:
        with self._lock:
            return self._status

    @property
    def error_message(self) -> Optional[str]:
        with self._lock:
            return self._error_message

    @property
    def backend(self) -> Optional[InferenceBackend]:
        with self._lock:
            return self._backend

    def is_ready(self) -> bool:
        with self._lock:
            return self._status == ModelStatus.READY and self._backend is not None and self._backend.is_loaded

    def set_status(self, status: ModelStatus, error: Optional[str] = None) -> None:
        with self._lock:
            self._status = status
            self._error_message = error
        logger.info(f"Model status changed to: {status.value}" + (f" ({error})" if error else ""))

    def load_model_async(self, on_complete: Optional[Callable[[bool, str], None]] = None) -> None:
        """Load model asynchronously off the UI thread."""
        self._executor.submit(self._do_load, on_complete)

    def load_model(self) -> bool:
        """Synchronously load model."""
        return self._do_load(None)

    def _do_load(self, callback: Optional[Callable[[bool, str], None]] = None) -> bool:
        self.set_status(ModelStatus.LOADING)
        path = self.config.model_path

        try:
            backend = BackendFactory.create_backend(path, self.config.backend)
            success = backend.load(
                model_path=path,
                context_length=self.config.context_length,
                n_threads=self.config.n_threads,
                n_gpu_layers=self.config.n_gpu_layers,
            )

            if success:
                with self._lock:
                    self._backend = backend
                    self.set_status(ModelStatus.READY)
                if callback:
                    callback(True, "Model loaded successfully.")
                return True
            else:
                msg = f"Failed to load model from: {path}"
                self.set_status(ModelStatus.ERROR, msg)
                if callback:
                    callback(False, msg)
                return False

        except Exception as e:
            msg = f"Exception while loading model: {e}"
            logger.error(msg, exc_info=True)
            self.set_status(ModelStatus.ERROR, msg)
            if callback:
                callback(False, msg)
            return False

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list[str]] = None,
    ) -> str:
        """Generate text using the loaded model synchronously."""
        with self._lock:
            if not self.is_ready() or self._backend is None:
                raise RuntimeError("SmolLM3-3B is not loaded or ready.")
            self.set_status(ModelStatus.GENERATING)

        self.bus.publish(EventTopic.BRAIN_GENERATION_START, {"prompt_len": len(prompt)})

        try:
            tokens = max_tokens or self.config.max_output_tokens
            temp = temperature if temperature is not None else self.config.temperature
            result = self._backend.generate(prompt, max_tokens=tokens, temperature=temp, stop=stop)
            return result
        finally:
            with self._lock:
                if self._backend and self._backend.is_loaded:
                    self.set_status(ModelStatus.READY)

    def generate_async(
        self,
        prompt: str,
        callback: Callable[[Optional[str], Optional[Exception]], None],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list[str]] = None,
    ) -> None:
        """Run inference asynchronously on the model thread."""
        def task():
            try:
                res = self.generate(prompt, max_tokens, temperature, stop)
                callback(res, None)
            except Exception as e:
                callback(None, e)

        self._executor.submit(task)

    def generate_stream(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list[str]] = None,
    ) -> Iterator[str]:
        """Stream tokens synchronously."""
        with self._lock:
            if not self.is_ready() or self._backend is None:
                raise RuntimeError("SmolLM3-3B is not loaded or ready.")
            self.set_status(ModelStatus.GENERATING)

        tokens = max_tokens or self.config.max_output_tokens
        temp = temperature if temperature is not None else self.config.temperature

        try:
            for chunk in self._backend.generate_stream(prompt, max_tokens=tokens, temperature=temp, stop=stop):
                self.bus.publish(EventTopic.BRAIN_GENERATION_CHUNK, chunk)
                yield chunk
        finally:
            with self._lock:
                if self._backend and self._backend.is_loaded:
                    self.set_status(ModelStatus.READY)

    def run_health_check(self) -> Dict[str, Any]:
        """Verify model readiness with a brief prompt."""
        if not self.is_ready() or self._backend is None:
            return {
                "healthy": False,
                "status": self.status.value,
                "error": self._error_message or "Model not loaded.",
            }

        try:
            import time
            t0 = time.time()
            test_prompt = "Say 'IRIS Ready' in two words."
            resp = self._backend.generate(test_prompt, max_tokens=16, temperature=0.1)
            duration = time.time() - t0
            return {
                "healthy": True,
                "status": self.status.value,
                "response": resp.strip(),
                "duration_ms": round(duration * 1000, 1),
                "metrics": self._backend.metrics.to_dict(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": ModelStatus.ERROR.value,
                "error": str(e),
            }

    def unload(self) -> None:
        """Unload backend and free resources."""
        with self._lock:
            if self._backend is not None:
                self._backend.unload()
                self._backend = None
            self.set_status(ModelStatus.NOT_CONFIGURED)

    def shutdown(self) -> None:
        """Clean shutdown of background executor and model."""
        self.unload()
        self._executor.shutdown(wait=False)
