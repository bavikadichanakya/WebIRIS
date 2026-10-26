"""Unit tests for ModelManager lifecycle, health checks, and status reporting."""

from iris.brain.model_manager import ModelManager, ModelStatus
from iris.core.config import ModelConfig


def test_model_manager_initial_state():
    cfg = ModelConfig(model_path="non_existent.gguf")
    mgr = ModelManager(cfg)
    assert mgr.status == ModelStatus.NOT_CONFIGURED
    assert not mgr.is_ready()


def test_model_manager_failed_load_diagnostics():
    cfg = ModelConfig(model_path="missing_file.gguf")
    mgr = ModelManager(cfg)
    success = mgr.load_model()

    assert not success
    assert mgr.status == ModelStatus.ERROR
    assert "Failed to load model" in (mgr.error_message or "")


def test_model_manager_health_check_unloaded():
    cfg = ModelConfig(model_path="missing_file.gguf")
    mgr = ModelManager(cfg)
    health = mgr.run_health_check()

    assert not health["healthy"]
    assert health["status"] == ModelStatus.NOT_CONFIGURED.value
