# Project IRIS — Native Windows Desktop Voice Agent with Local SmolLM3-3B Brain

Project IRIS is a system-wide, background voice assistant for Windows built from the ground up with local AI. It operates with zero cloud API dependencies: reasoning is powered by a locally running **SmolLM3-3B** model, wake-word detection uses a dedicated **'Hey Iris'** ONNX model, speech-to-text uses **Faster-Whisper**, speech output uses **Windows SAPI5 / Piper TTS**, and desktop automation is driven by native Windows APIs.

---

## Key Features

1. **Local SmolLM3-3B Brain**:
   - Runs locally on CPU or GPU with zero cloud LLM reliance.
   - Modular inference backend: primary **llama.cpp** backend for quantized GGUF models (`smol-Q4_K_M.gguf`, ~1.78 GB), plus **Transformers** backend for Hugging Face safetensors.
   - Constrained action-planning schema producing validated JSON tool selections.
   - Deterministic fast-path for routine commands (launch apps, switch windows, greetings) for instant execution.
   - Off-UI-thread execution preventing UI freezes.

2. **Custom Trained Wake-Word Model**:
   - Direct integration of the user's trained `hey_iris.onnx` openWakeWord model.
   - Melspectrogram and embedding preprocessors running via ONNX Runtime.
   - Adjustable sensitivity threshold, refractory cooldown, and false-positive suppression.

3. **Background Voice Pipeline & Loopback Protection**:
   - Runs in the background independently of whether the settings window is open, hidden, or closed.
   - State machine: `IDLE`, `LISTENING`, `WAKE_DETECTED`, `TRANSCRIBING`, `THINKING`, `EXECUTING`, `SPEAKING`, `ERROR`.
   - **Loopback protection**: Audio capture is muted during TTS playback so IRIS never triggers from its own voice.

4. **System-Wide Windows Automation**:
   - **App Launcher**: Launches approved programs from a configurable allowlist.
   - **Window Manager**: Enumerates active windows, brings windows to foreground, restores minimized windows, and cycles focus.
   - **Safe Text Input**: Types into active applications with controlled pacing. UI Automation verifies target controls to **block typing into password or passcode fields**.
   - **Text Submission**: Sends Enter keystrokes only upon explicit request or user authorization.
   - **UI Element Reader**: Inspects accessible text and control types in the active application.

5. **Security & Permissions**:
   - Model treated as an untrusted planner; permissions enforced in deterministic application code.
   - Configurable per-tool policies: `allow`, `confirm`, or `deny`.
   - Interactive confirmation dialogs before executing potentially consequential actions.
   - Sensitive pattern redactor in logging buffer.

6. **Native PySide6 Desktop UI & System Tray**:
   - Polished dark UI with neon status indicators, live microphone level meter, and interactive model sandbox.
   - Pages: Dashboard, SmolLM3-3B Brain, Voice & Audio, Automation Tools, Setup & Models, Diagnostics Logs.
   - Windows System Tray icon with dynamic menu: Pause/Resume listening, Show settings, and Exit.
   - Closing the window minimizes to tray to keep the background voice engine running.

7. **Automatic Setup Manager & Resumable Downloader**:
   - First-run Setup Wizard inspecting Python, virtualenv, models, and speech engines.
   - Resumable HTTP model downloader with speed calculation, ETA, and Windows file-lock retry.
   - SHA-256 and ONNX/GGUF model load verification.

---

## Directory Structure

```
Web-IRIS/
├── iris/
│   ├── app/
│   │   ├── main.py              # Main application entrypoint
│   │   └── bootstrap.py         # Subsystem wiring and container
│   ├── core/
│   │   ├── config.py            # Pydantic configuration schemas
│   │   ├── state_machine.py     # Thread-safe runtime state machine
│   │   ├── event_bus.py         # Publish/subscribe event bus
│   │   └── logging_setup.py     # Rotating file and memory logging
│   ├── brain/
│   │   ├── inference_backend.py # LlamaCpp and Transformers backends
│   │   ├── model_manager.py     # Off-thread model execution & health check
│   │   ├── prompt_builder.py    # System prompt formatting with tool catalog
│   │   ├── action_planner.py    # Deterministic fast-path + model reasoning
│   │   └── output_validator.py  # JSON extraction, repair, and schema validation
│   ├── voice/
│   │   ├── audio_capture.py     # sounddevice capture & RMS level metering
│   │   ├── wake_word_adapter.py # openWakeWord adapter for hey_iris.onnx
│   │   ├── stt_adapter.py       # Faster-Whisper local STT
│   │   ├── tts_adapter.py       # Windows SAPI5 / Piper TTS
│   │   └── voice_pipeline.py    # Full voice loop with loopback suppression
│   ├── tools/
│   │   ├── schemas.py           # Tool definition schemas
│   │   ├── registry.py          # Central tool registry
│   │   ├── app_launcher.py      # Allowlisted app launcher
│   │   ├── window_manager.py    # Native window enumeration and focus
│   │   ├── text_input.py        # Safe typing & password field blocking
│   │   └── ui_automation.py     # UI element inspection
│   ├── ipc/
│   │   ├── protocol.py          # JSON-RPC protocol
│   │   ├── server.py            # Local socket server
│   │   └── client.py            # Local socket client
│   ├── ui/
│   │   ├── main_window.py       # PySide6 main window
│   │   ├── settings_pages.py    # 6 settings and diagnostic pages
│   │   ├── setup_wizard.py      # First-run setup wizard dialog
│   │   ├── tray.py              # Windows System Tray integration
│   │   └── theme.py             # Modern dark QSS stylesheet
│   ├── security/
│   │   ├── permissions.py       # Allow/confirm/deny policies
│   │   └── confirmations.py     # GUI and spoken confirmation handler
│   └── setup/
│       ├── manifest.py          # Component manifests
│       ├── downloader.py        # Resumable chunked downloader
│       ├── verifier.py          # Checksums & model load checks
│       └── environment.py       # Host environment inspector
├── models/
│   ├── wakeword/
│   │   ├── hey_iris.onnx        # Trained wake-word model
│   │   ├── melspectrogram.onnx  # openWakeWord preprocessor
│   │   └── embedding_model.onnx # openWakeWord embeddings
│   └── smollm3/
│       └── smol-Q4_K_M.gguf     # SmolLM3-3B quantized model (1.78 GB)
├── scripts/
│   └── download_model.py        # CLI model downloader
├── tests/                       # 36 automated unit & integration tests
├── requirements.txt             # Pinned Python dependencies
└── run_iris.py                  # Root execution script
```

---

## Quick Start & Installation

### 1. Requirements
- **OS**: Windows 10 or Windows 11 (64-bit)
- **Python**: Python 3.12 (recommended) or 3.11
- **Hardware**: Minimum 8 GB RAM, 4 CPU cores (optional Intel Iris Xe / NVIDIA GPU)
- **Microphone**: Working audio input device

### 2. Setup Virtual Environment & Dependencies
```powershell
# Create Python 3.12 virtual environment using uv or python
uv venv --python 3.12 .venv

# Activate environment
.\.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

### 3. Verify All Tests
Run the automated test suite covering state machine, output validator, action planner, permissions, wake-word model, tools, and IPC:
```powershell
.\.venv\Scripts\pytest.exe -v
```

### 4. Run IRIS
```powershell
.\.venv\Scripts\python.exe run_iris.py
```

---

## Wake-Word & Voice Operation

1. Say **"Hey Iris"**.
2. IRIS transitions to `WAKE_DETECTED` and listens for your spoken command.
3. Speak a command such as:
   - *"Open Notepad"*
   - *"Switch to Chrome"*
   - *"Launch Calculator"*
   - *"Type hello world into the document"*
   - *"What can you do?"*
4. IRIS transcribes the speech via Faster-Whisper, routes through the deterministic fast-path or SmolLM3-3B, verifies security permissions, performs the Windows desktop action, and speaks the response via Windows SAPI5.
5. The microphone is muted during speech playback to prevent self-triggering, then returns to `LISTENING`.

---

## Windows System Tray & Background Runtime

- When the configuration window is closed with the `X` button, IRIS minimizes to the Windows System Tray and continues listening.
- Left-click or right-click the tray icon to:
  - **Open Settings**: Re-open the configuration dashboard.
  - **Pause Listening**: Temporarily disable microphone ingestion.
  - **Exit IRIS Completely**: Terminate the background runtime cleanly.
