"""
Project IRIS - Component & Model Verifier
Verifies file integrity, disk sizes, checksums, and model loadability.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("iris.setup.verifier")


class Verifier:
    """Verifies file integrity and executes load tests on installed models."""

    @staticmethod
    def verify_file_exists(filepath: str, min_size_bytes: int = 1) -> bool:
        p = Path(filepath)
        if not p.exists():
            return False
        return p.stat().st_size >= min_size_bytes

    @staticmethod
    def calculate_sha256(filepath: str, chunk_size: int = 1024 * 1024) -> str:
        """Calculate SHA256 hash of a file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def verify_wake_word_model(model_path: str, melspec_path: str, embedding_path: str) -> Dict[str, Any]:
        """Test load openWakeWord model to verify ONNX integrity."""
        for path, label in [
            (model_path, "hey_iris.onnx"),
            (melspec_path, "melspectrogram.onnx"),
            (embedding_path, "embedding_model.onnx"),
        ]:
            if not os.path.exists(path):
                return {"valid": False, "error": f"{label} not found at {path}"}

        try:
            import numpy as np
            from openwakeword.model import Model

            model = Model(
                wakeword_models=[model_path],
                melspec_model_path=melspec_path,
                embedding_model_path=embedding_path,
                inference_framework="onnx",
            )
            # Test run on dummy chunk
            dummy = np.zeros(1280, dtype=np.int16)
            res = model.predict(dummy)
            return {
                "valid": True,
                "models": list(model.models.keys()),
                "test_prediction": res,
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def verify_gguf_model(model_path: str) -> Dict[str, Any]:
        """Test load GGUF model via llama_cpp."""
        if not os.path.exists(model_path):
            return {"valid": False, "error": f"GGUF file not found: {model_path}"}

        try:
            import llama_cpp
            llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=512,
                n_threads=2,
                verbose=False,
            )
            output = llm("Hello", max_tokens=4, echo=False)
            text = output["choices"][0]["text"]
            del llm
            return {"valid": True, "test_output": text}
        except Exception as e:
            return {"valid": False, "error": str(e)}
