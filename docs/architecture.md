# Project IRIS — Technical Architecture & Specifications

This document outlines the detailed architecture, data flows, and design decisions for Project IRIS.

---

## 1. Subsystem Architecture

```
+-----------------------------------------------------------------------------------+
|                                  USER / DESKTOP                                   |
+-----------------------------------------------------------------------------------+
       | (Speech Audio)                                           ^ (Window / Keystrokes)
       v                                                           |
+--------------------------+                         +------------------------------+
| AudioCapture             |                         | Windows Automation Tools     |
| - sounddevice (16kHz)    |                         | - AppLauncherTool            |
| - RMS metering           |                         | - WindowManagerTool          |
| - Mute/Unmute control    |                         | - TextInputTool (Safe)       |
+--------------------------+                         | - UIAutomationTool           |
       |                                             +------------------------------+
       v (1280-sample chunks)                                      ^
+--------------------------+                                       |
| OpenWakeWordAdapter      |                                       | (Execute Approved)
| - hey_iris.onnx          |                                       |
| - melspectrogram.onnx    |                                       |
| - embedding_model.onnx   |                                       |
+--------------------------+                                       |
       | (Wake Detected)                                           |
       v                                                           |
+--------------------------+                         +------------------------------+
| VoicePipeline            |                         | PermissionManager            |
| - Command audio buffer   |                         | - allow / confirm / deny     |
| - VAD silence detector   |                         | - ConfirmationManager (GUI)  |
+--------------------------+                         +------------------------------+
       |                                                           ^
       v (Speech Array)                                            | (Proposed Plan)
+--------------------------+                                       |
| FasterWhisperSTT         |                                       |
| - tiny.en / base.en      |                                       |
| - int8 CTranslate2       |                                       |
+--------------------------+                                       |
       | (Transcribed Text)                                        |
       v                                                           |
+------------------------------------------------------------------+
| ActionPlanner                                                    |
| - Deterministic Fast-Path (instant launch / focus)               |
| - PromptBuilder (Tool Catalog + JSON Schema)                     |
| - SmolLM3-3B Reasoning (llama.cpp GGUF / Transformers)           |
| - OutputValidator (Pydantic schema validation & syntax repair)   |
+------------------------------------------------------------------+
       |
       v (Spoken Response)
+--------------------------+
| WindowsSAPI5TTS          |
| - Loopback Suppression   |
| - Microsoft David / Zira |
+--------------------------+
```

---

## 2. State Machine Flow

```
   +--------+   start()    +-----------+
   |  IDLE  | -----------> | LISTENING | <--------------------+
   +--------+              +-----------+                      |
       ^                         | (Wake word detected)       |
       | pause                   v                            |
       |                   +---------------+                  |
       +------------------ | WAKE_DETECTED |                  |
       |                   +---------------+                  |
       |                         | (Audio recorded)           |
       |                         v                            |
       |                   +--------------+                   |
       +------------------ | TRANSCRIBING |                   |
       |                   +--------------+                   |
       |                         | (STT complete)             |
       |                         v                            |
       |                   +----------+                       |
       +------------------ | THINKING |                       |
       |                   +----------+                       |
       |                         | (Plan validated)           |
       |                         v                            |
       |                   +-----------+                      |
       +------------------ | EXECUTING |                      |
       |                   +-----------+                      |
       |                         | (Tool finished)            |
       |                         v                            |
       |                   +----------+                       |
       +------------------ | SPEAKING | ----------------------+
                           +----------+ (TTS playback ends;
                                         microphone un-muted)
```

---

## 3. SmolLM3-3B Inference Engine Selection

### Choice of Primary Backend: `llama-cpp-python` with Q4_K_M GGUF
1. **Memory Footprint**:
   - SmolLM3-3B unquantized in FP16 requires ~6.5 GB RAM. On a Windows machine with 8 GB total system RAM and an integrated Intel Iris Xe GPU, running FP16 leaves insufficient headroom for Windows and desktop apps.
   - The `Q4_K_M` 4-bit quantization reduces memory use to **~1.9 GB**, fitting comfortably within available memory while preserving instruction-following accuracy.
2. **Latency & Performance**:
   - `llama.cpp` uses optimized AVX2/AVX-512 CPU instructions and multi-threading (`n_threads=4`).
   - Achieves low prompt-processing latency and ~15-25 tokens/second on standard mobile/desktop CPUs.
3. **Plug-and-Play Extensibility**:
   - The modular `InferenceBackend` abstract class also provides `TransformersBackend` for environments with dedicated GPUs or raw Hugging Face safetensors directories.
   - The `BackendFactory` automatically detects model format based on file extensions.

---

## 4. Wake-Word Integration (`hey_iris.onnx`)

- **Format**: ONNX Runtime computational graph exported from PyTorch 2.10.
- **Input Tensor**: `input` of shape `[batch, 16, 96]`, representing 16 consecutive 80ms time-slices of 96-dimensional acoustic embeddings.
- **Output Tensor**: `output` of shape `[batch, 1]`, representing sigmoid activation probability `[0.0, 1.0]`.
- **Preprocessors**:
  - `melspectrogram.onnx`: Converts 16kHz PCM audio to 80-bin log mel-spectrograms.
  - `embedding_model.onnx`: Transforms mel-spectrogram bins into 96-dimensional embeddings.
- **Integration**: Loaded directly via `openwakeword.model.Model`. Cooldown suppresses false-trigger cascades.

---

## 5. Security & Safety Model

1. **Untrusted Planner Paradigm**:
   - The language model is **never** given raw shell execution or eval capabilities.
   - All proposed actions must strictly match pre-registered tools in `iris/tools/registry.py`.
2. **Password & Credential Protection**:
   - `TextInputTool` queries Windows UI Automation (`auto.GetFocusedControl()`) before injecting keystrokes.
   - If `IsPassword == True` or control title contains "password", typing is immediately blocked.
3. **Consequential Action Confirmations**:
   - Actions marked with policy `"confirm"` (such as `submit_text` or destructive commands) raise an interactive confirmation dialog or require explicit confirmation.
4. **Log Data Sanitization**:
   - The in-memory logging buffer and rotating file handler automatically redact common token and password patterns.
