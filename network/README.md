# GLaDOS Network Mode

Run GLaDOS on a homelab server while streaming audio from your laptop/phone.

## Architecture

```
┌─────────────────┐         ┌─────────────────────────────┐
│  Laptop/Phone   │  TCP    │      Homelab Server         │
│                 │◄───────►│                             │
│  audio_client   │  Audio  │  GLaDOS (unchanged)         │
│  - Mic capture  │  Stream │  - ASR (local)              │
│  - Speaker out  │         │  - LLM (Ollama)             │
└─────────────────┘         │  - TTS (local)              │
                            │  + NetworkAudioIO           │
                            └─────────────────────────────┘
```

## How it works

1. `NetworkAudioIO` replaces the local sounddevice audio I/O
2. It implements the same `AudioProtocol` interface
3. Audio streams over TCP with minimal latency
4. All the original GLaDOS logic (VAD, interruption, queues) works unchanged

## Usage

### Server (homelab)
```bash
# Run GLaDOS with network audio
python -m glados.cli --config configs/glados_config.yaml --audio-io network --network-port 5555
```

### Client (laptop)
```bash
# Stream audio to/from server
python network/audio_client.py --server 192.168.1.100:5555
```
