# Using Small Qwen Models as Face (Fast Role)

## Models Available

| Model | File | Size | Port | GPU | Context |
|-------|------|------|------|-----|---------|
| Qwen3-1.7B-BF16 | `Qwen3-1.7B-BF16.gguf` | ~3.5 GB | 12323 | RTX 3090 (1) | 32K |
| Qwen3-1.7B-Q4_K_XL | `Qwen3-1.7B-UD-Q4_K_XL.gguf` | ~1.1 GB | 12324 | RTX 3090 (1) | 32K |

Both run on **RTX 3090 (GPU 1)**. Deep model uses RTX 4090 (GPU 0).

---

## Quick Test (Option 1 - No Code Changes)

### Stop current face server
```bash
./scripts/llama-face.sh --stop
```

### Start Qwen 1.7B-Q4 as face on port 12322
```bash
LLAMA_FACE_MODEL=/home/albert/aidev/models/Qwen3-1.7B-UD-Q4_K_XL.gguf \
LLAMA_FACE_PORT=12322 \
LLAMA_FACE_GPU=1 \
LLAMA_FACE_CTX=32768 \
./scripts/llama-face.sh
```

### Restart Fluent server (picks up new face on port 12322)
```bash
fuser -k 4890/tcp 2>/dev/null; sleep 1
FLUENT_DATA_DIR=/tmp/fluent-nes PORT=4890 nohup bun server/src/index.ts > /tmp/fluent-srv-4890.log 2>&1 &
```

---

## Permanent Config (Option 2 - Update Server Config)

### Edit `server/src/index.ts`

In `loadModels()` function, update `faceDefaults`:

```typescript
const faceDefaults = {
  name: "qwen1.7b-q4",                    // model name for routing
  baseURL: "http://127.0.0.1:12324/v1",   // Qwen 1.7B-Q4 port
  temperature: 0.7,
  maxTokens: 4096,
  topP: 0.95,
  timeoutMs: 120000,
};
```

Or for BF16 model:
```typescript
const faceDefaults = {
  name: "qwen1.7b-bf16",
  baseURL: "http://127.0.0.1:12323/v1",   // Qwen 1.7B-BF16 port
  temperature: 0.7,
  maxTokens: 4096,
  topP: 0.95,
  timeoutMs: 120000,
};
```

### Rebuild & Restart
```bash
cd /media/albert/railab2/projects/fluent_dev/server && bunx tsc --noEmit
fuser -k 4890/tcp 2>/dev/null; sleep 1
FLUENT_DATA_DIR=/tmp/fluent-nes PORT=4890 nohup bun server/src/index.ts > /tmp/fluent-srv-4890.log 2>&1 &
```

---

## Ports Summary

| Role | Model | Port | GPU |
|------|-------|------|-----|
| Deep (tutor) | Qwen3-14B | 12321 | 4090 (0) |
| Face (fast) | Qwen 1.7B-Q4 | 12324 | 3090 (1) |
| Face (alt) | Qwen 1.7B-BF16 | 12323 | 3090 (1) |

---

## Verify Face Model Working

```bash
# Test face model directly
curl -s -X POST http://127.0.0.1:12324/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen1.7b-q4","messages":[{"role":"user","content":"Say hello in one sentence"}],"max_tokens":20}'
```

Should return a response in < 1 second.

---

## Notes

- Both Qwen 1.7B models share **RTX 3090 (GPU 1)** — total ~4.6 GB VRAM
- Deep model (14B) runs on **RTX 4090 (GPU 0)**
- Context 32K is sufficient for vocab/review/progress (fast role)
- If using BF16 model, change port to 12323 in config