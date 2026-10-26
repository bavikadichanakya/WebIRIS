"""Unit tests for IRIS configuration management."""

import json
from pathlib import Path
from iris.core.config import IrisConfig, ModelConfig, WakeWordConfig


def test_default_config_creation(tmp_path: Path):
    cfg_file = tmp_path / "test_config.json"
    config = IrisConfig()
    config.save(cfg_file)

    assert cfg_file.exists()
    loaded = IrisConfig.load(cfg_file)
    assert loaded.version == "1.0.0"
    assert loaded.model.context_length == 2048
    assert loaded.wake_word.threshold == 0.5


def test_config_modification_and_persistence(tmp_path: Path):
    cfg_file = tmp_path / "custom_config.json"
    config = IrisConfig()
    config.model.temperature = 0.7
    config.wake_word.threshold = 0.65
    config.automation.typing_delay_ms = 25
    config.save(cfg_file)

    loaded = IrisConfig.load(cfg_file)
    assert loaded.model.temperature == 0.7
    assert loaded.wake_word.threshold == 0.65
    assert loaded.automation.typing_delay_ms == 25
