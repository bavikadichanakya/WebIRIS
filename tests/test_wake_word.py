"""Unit tests for WakeWordAdapter with hey_iris.onnx."""

import os
import numpy as np
import pytest
from iris.voice.wake_word_adapter import OpenWakeWordAdapter, MockWakeWordAdapter


def test_mock_wake_word_adapter():
    mock = MockWakeWordAdapter(should_trigger=True)
    assert mock.load()
    detected, conf = mock.process_audio(np.zeros(1280, dtype=np.int16))
    assert detected
    assert conf > 0.9


def test_real_open_wake_word_loading():
    model_path = "models/wakeword/hey_iris.onnx"
    melspec = "models/wakeword/melspectrogram.onnx"
    embed = "models/wakeword/embedding_model.onnx"

    if not (os.path.exists(model_path) and os.path.exists(melspec) and os.path.exists(embed)):
        pytest.skip("Wake word model assets not found in models/wakeword.")

    adapter = OpenWakeWordAdapter(
        model_path=model_path,
        melspec_path=melspec,
        embedding_path=embed,
        threshold=0.5,
    )
    assert adapter.load()
    assert adapter.is_loaded

    # Process silence
    silence = np.zeros(1280, dtype=np.int16)
    detected, conf = adapter.process_audio(silence)
    assert not detected
    assert conf < 0.2

    # Verify diagnostics
    diag = adapter.get_diagnostics()
    assert diag["is_loaded"]
    assert diag["threshold"] == 0.5
