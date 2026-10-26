"""
Project IRIS - Local Inference Backend Architecture
Provides modular, replaceable inference backends for SmolLM3-3B.
Supports both llama.cpp (for .gguf) and Hugging Face Transformers (for safetensors).
"""

from __future__ import annotations

import abc
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional

logger = logging.getLogger("iris.brain.inference_backend")


class BackendMetrics:
    """Metrics tracking for local model inference."""

    def __init__(self) -> None:
        self.load_time_seconds: float = 0.0
        self.total_tokens_generated: int = 0
        self.total_generation_time: float = 0.0
        self.last_latency_ms: float = 0.0
        self.last_tokens_per_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "load_time_seconds": round(self.load_time_seconds, 2),
            "total_tokens_generated": self.total_tokens_generated,
            "total_generation_time": round(self.total_generation_time, 2),
            "last_latency_ms": round(self.last_latency_ms, 1),
            "last_tokens_per_sec": round(self.last_tokens_per_sec, 2),
        }


class InferenceBackend(abc.ABC):
    """Abstract base class for all local inference backends."""

    def __init__(self) -> None:
        self.metrics = BackendMetrics()
        self._is_loaded = False
        self._model_path: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def model_path(self) -> Optional[str]:
        return self._model_path

    @abc.abstractmethod
    def load(
        self,
        model_path: str,
        context_length: int = 2048,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        **kwargs: Any,
    ) -> bool:
        """Load model weights into memory."""
        pass

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> str:
        """Generate complete text response synchronously."""
        pass

    @abc.abstractmethod
    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> Iterator[str]:
        """Stream generated text token by token."""
        pass

    @abc.abstractmethod
    def unload(self) -> None:
        """Unload model and free memory."""
        pass


class LlamaCppBackend(InferenceBackend):
    """Llama.cpp backend for GGUF model files (e.g. smol-Q4_K_M.gguf)."""

    def __init__(self) -> None:
        super().__init__()
        self._model: Any = None

    def load(
        self,
        model_path: str,
        context_length: int = 2048,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        **kwargs: Any,
    ) -> bool:
        t0 = time.time()
        self._model_path = os.path.abspath(model_path)
        if not os.path.exists(self._model_path):
            logger.error(f"LlamaCppBackend: Model file not found at {self._model_path}")
            return False

        try:
            import llama_cpp
            logger.info(f"Loading GGUF model via llama.cpp: {self._model_path}")
            self._model = llama_cpp.Llama(
                model_path=self._model_path,
                n_ctx=context_length,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._is_loaded = True
            self.metrics.load_time_seconds = time.time() - t0
            logger.info(f"Model loaded in {self.metrics.load_time_seconds:.2f}s")
            return True
        except Exception as e:
            logger.error(f"Failed to load model with llama_cpp: {e}", exc_info=True)
            self._is_loaded = False
            self._model = None
            return False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> str:
        if not self._is_loaded or self._model is None:
            raise RuntimeError("LlamaCppBackend: Model is not loaded.")

        t0 = time.time()
        output = self._model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            echo=False,
        )
        duration = time.time() - t0
        text = output["choices"][0]["text"]
        token_count = output["usage"]["completion_tokens"]

        self.metrics.total_tokens_generated += token_count
        self.metrics.total_generation_time += duration
        self.metrics.last_latency_ms = duration * 1000.0
        self.metrics.last_tokens_per_sec = (token_count / duration) if duration > 0 else 0.0

        return text

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> Iterator[str]:
        if not self._is_loaded or self._model is None:
            raise RuntimeError("LlamaCppBackend: Model is not loaded.")

        stream = self._model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            stream=True,
            echo=False,
        )
        for chunk in stream:
            delta = chunk["choices"][0].get("text", "")
            if delta:
                yield delta

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
        self._is_loaded = False
        logger.info("LlamaCppBackend: Model unloaded.")


class TransformersBackend(InferenceBackend):
    """Transformers backend for Hugging Face safetensors format."""

    def __init__(self) -> None:
        super().__init__()
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: str = "cpu"

    def load(
        self,
        model_path: str,
        context_length: int = 2048,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        **kwargs: Any,
    ) -> bool:
        t0 = time.time()
        self._model_path = os.path.abspath(model_path)
        if not os.path.exists(self._model_path):
            logger.error(f"TransformersBackend: Directory not found: {self._model_path}")
            return False

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            torch.set_num_threads(n_threads)
            self._device = "cuda" if torch.cuda.is_available() and n_gpu_layers > 0 else "cpu"
            logger.info(f"Loading Transformers model from {self._model_path} onto {self._device}")

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_path,
                torch_dtype=torch.float32 if self._device == "cpu" else torch.float16,
            ).to(self._device)
            self._is_loaded = True
            self.metrics.load_time_seconds = time.time() - t0
            logger.info(f"Transformers model loaded in {self.metrics.load_time_seconds:.2f}s")
            return True
        except Exception as e:
            logger.error(f"Failed to load Transformers model: {e}", exc_info=True)
            self._is_loaded = False
            return False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> str:
        if not self._is_loaded or self._model is None:
            raise RuntimeError("TransformersBackend: Model is not loaded.")

        import torch
        t0 = time.time()
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        input_len = inputs.input_ids.shape[1]

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=max(temperature, 0.01),
                do_sample=temperature > 0.05,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        duration = time.time() - t0
        generated_ids = outputs[0][input_len:]
        text = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        token_count = len(generated_ids)

        self.metrics.total_tokens_generated += token_count
        self.metrics.total_generation_time += duration
        self.metrics.last_latency_ms = duration * 1000.0
        self.metrics.last_tokens_per_sec = (token_count / duration) if duration > 0 else 0.0

        return text

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
    ) -> Iterator[str]:
        # Fallback to single yield if streamer is not configured
        yield self.generate(prompt, max_tokens, temperature, stop)

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        self._is_loaded = False
        logger.info("TransformersBackend: Model unloaded.")


class BackendFactory:
    """Factory to create and resolve inference backends based on format."""

    @staticmethod
    def create_backend(model_path: str, requested_backend: str = "auto") -> InferenceBackend:
        if requested_backend == "llama_cpp":
            return LlamaCppBackend()
        elif requested_backend == "transformers":
            return TransformersBackend()

        # Automatic detection
        path_str = str(model_path).lower()
        if path_str.endswith(".gguf") or path_str.endswith(".bin"):
            return LlamaCppBackend()
        elif os.path.isdir(model_path):
            return TransformersBackend()

        # Default fallback to llama_cpp
        return LlamaCppBackend()
