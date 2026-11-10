# QMD Embed — llama.cpp Metal Crash on Apple Silicon

## Full Error Transcript

```
Model: hf:ggml-org/embeddinggemma-300M-GGUF/embeddinggemma-300M-Q8_0.gguf

✓ Done! Embedded 23648 chunks from 1290 documents in 30m 1s
⚠ 2218 chunks failed

/Users/runner/work/node-llama-cpp/node-llama-cpp/llama/llama.cpp/ggml/src/ggml-metal/ggml-metal-device.m:612: GGML_ASSERT([rsets->data count] == 0) failed
WARNING: Using native backtrace. Set GGML_BACKTRACE_LLDB for more info.
WARNING: GGML_BACKTRACE_LLDB may cause native MacOS Terminal.app to crash.
See: https://github.com/ggml-org/llama.cpp/pull/17869
0   libggml-base.dylib                  0x... ggml_print_backtrace + 276
1   libggml-base.dylib                  0x... ggml_abort + 156
2   libggml-metal.so                    0x... ggml_metal_device_init + 0
3   libggml-metal.so                    0x... ggml_metal_device_free + 24
4   libggml-metal.so                    0x... _ZNSt3__16vectorINS_10unique_ptrI17ggml_metal_device25ggml_metal_device_deleterEENS_9allocatorIS4_EEED1B8ne200100Ev + 72
5   libsystem_c.dylib                   0x... __cxa_finalize_ranges + 416
6   libsystem_c.dylib                   0x... exit + 44
...
```

## What Actually Happens

1. `qmd embed` downloads model weights on first run (~1min, cached thereafter)
2. Embeddings are computed and written to `~/.cache/qmd/index.sqlite` in real-time
3. Progress shown as `██████████████████████████████ 100%` with "✓ Done!"
4. **Then** the atexit handler runs `ggml_metal_device_free`
5. The Metal device has a non-empty `rsets` vector — triggers GGML_ASSERT
6. Backtrace prints (this causes the long hang)
7. Process eventually exits — **but all embeddings are already on disk**

## Verified: Env Vars That Do NOT Fix It

```bash
export NODE_LLAMA_CPP_GPU=false      # Not respected by node-llama-cpp
export LLAMA_CPP_NO_GPU=true        # Not respected
export GGML_METAL_DEVICE=cpu        # Not respected
export GGML_METAL_OFF=1             # Not respected
export GGML_NO_METAL=1              # Not respected
```

## Observed Performance (Apple M4, 16GB RAM, Metal GPU)

- Batch 1: ~80 vectors/min (warm-up)
- Batch 2: ~100 vectors/min
- Batch 3: ~170 vectors/min
- Batch 4: ~440 vectors/min (after internal optimization)
- Batch 5+: ~130-160 vectors/min (stable)
- ~51,000 total vectors embedded in ~50 minutes across multiple runs

## "Session expired" Errors

During long embed runs, a "Session expired — skipping N remaining chunks" warning appears. This means some chunks were not embedded. Re-running `qmd embed` picks up from where it left off.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (crash dump prints after this anyway) |
| 124 | `timeout` killed process (not available on macOS) |
| 137 | `perl alarm` killed process (SIGALRM) |
| 142 | `perl alarm` killed process (128 + 14 = SIGALRM) |

## Log File Locations

- Embed stdout: `~/.cache/qmd/embed.log` or redirect via `> /tmp/qmd-embed.log 2>&1`
- QMD status: `qmd status` shows Vectors/Pending/Updated counts
- QMD index DB: `~/.cache/qmd/index.sqlite`

## Upstream Issue

See: https://github.com/ggml-org/llama.cpp/pull/17869 (referenced in warning message)
