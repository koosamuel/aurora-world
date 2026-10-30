# U21 · local neural sketch-to-3D (experimental)

## Result, not a quality claim

The existing U20 → U21 client/server now also accepts a locally uploaded PNG/JPEG,
uses the selected immutable BUNNY brief/hash as context, and reconstructs a vertex-colored
GLB through **official pretrained TripoSR**, not procedural ellipsoids. Requested dimensions
are recorded only; outputs are not dimension-calibrated, design-approved, or manufacturing-approved.
This path does not silently enter U22/U23 review/pattern/BOM workflows.

**The requested Meshy screenshot quality was NOT reached in three evaluated rounds.**
Do not confuse a valid/watertight GLB with a good reconstruction. No extra training was performed.

| Round | Changes | Actual result | Mesh |
|---|---|---|---|
| 1 | U2Net background removal, grid 128 | Torso/legs largely removed; rejected | 6,849 vertices / 13,702 faces |
| 2 | Faint sketch contour closing/fill, grid 192 | Whole body retained but too flat; not target quality | 8,308 / 16,612 |
| 3 | Existing local SD1.5 img2img (.55, 30 steps, seed 42, safety checker retained), then U2Net, grid 256 | Design drift and foreground loss; rejected, NOT promoted | 17,852 / 35,704 |

All used the same actual rabbit sketch from project processed data, not a fabricated successful example.
`results/learned3d-evaluation/iteration{1,2,3}/` contains actual GLB/condition/report files locally.
Round 1/2/3 reconstruction times on this Mac's MPS were approximately 10.1/10.2/10.9 seconds
(excluding segmentation, checkpoint downloads, hashing and SD conditioning). These are not general benchmarks.
The current default uses round 2's **contour** preprocessing; third-round SD design changes are
an evaluation-only script, not a hidden production transformation. Uploaded transparent PNGs
retain their supplied foreground alpha. No fourth neural reconstruction was run for this task.

## Setup

Optional; normal synthetic U20–U24 requires none of these weights.
Use the existing AI Python described in `AI_SAMPLING.md`. Additional packages:

```sh
python -m pip install -r requirements-learned3d.txt
mkdir -p .models
git clone https://github.com/VAST-AI-Research/TripoSR.git .models/TripoSR
git -C .models/TripoSR checkout 107cefdc244c39106fa830359024f6a2f1c78871
python -m pip install --target .models/tripo-python --no-deps transformers==4.46.3 tokenizers==0.20.3 huggingface-hub==0.26.5
```

Use `huggingface_hub.snapshot_download` to download `stabilityai/TripoSR` at revision
`5b521936b01fbe1890f6f9baed0254ab6351c04a` (`config.yaml`, `model.ckpt`) and
`hf_hub_download('facebook/dino-vitb16', 'config.json', revision='f205d5d8e640a89a2b8ef0369670dfc37cc07fc2')`.
Copy `.learned3d-local.example.json` to `.learned3d-local.json`, set absolute local paths.
The checkpoint is 1,677,246,742 bytes. Source/model SHA-256 values are pinned in
`configs/ai/triposr-manifest.json` and checked before loading (tensor-only `weights_only=True`).

The compatibility layer is isolated to this subprocess; it does not downgrade existing 2D AI dependencies.
The adapter substitutes scikit-image marching cubes for native torchmcubes, avoiding CUDA compilation.
MPS is used when available, otherwise CPU. Background handling does not load rembg/OpenMP into Torch.
RemBG/ONNX were only needed for the rejected round 1/3 evaluation, not the production default.
Models, environment, inputs and generated results are ignored by Git. Model licenses remain separate:
TripoSR upstream source and weights are MIT; the existing SD1.5 experiment has its own model license.

## UI / APIs

Run the usual `PYTHONPATH=src python -m aurora serve --port 8765` from the repository.
In digital sampling select a U20 BUNNY brief. In **학습형 스케치 → 3D**, upload and consent.
The UI polls the job, checks artifact size/SHA-256, shows the actual conditioned input and GLB,
and offers GLB/PNG/JSON downloads. It warns explicitly that current pencil-sketch quality is insufficient.
No browser path, shell fragment, URL, prompt, model path or arbitrary hyperparameter is accepted.

- `GET /api/learned3d/capabilities`
- `POST /api/learned3d/runs` → 202; strict JSON fields `image_base64`, `dimensions_mm`,
  `view:"single"`, `source_id`, `source_checksum`.
- `GET /api/learned3d/runs/{id}` → queued/running/succeeded/failed.
- `GET /api/learned3d/artifacts/{id}/{name}` → only condition.png/model.glb/report.json.

Loopback Host and same-origin POST guards apply. Request ≤3MiB, decoded image ≤2MiB,
PNG/JPEG single frame, ≥32 pixels, ≤8M pixels. Model processes use no shell and have 1,200-second
per-stage timeouts. One active neural 3D request, maximum 100 stored runs; shared one-worker GPU
executor serializes existing 2D AI and new 3D jobs. Restart marks queued/running jobs failed.
Leaving the page does not cancel the server job. Inputs stay on this Mac; no paid API/cloud upload.

## Verification and next decision

- 5 new service/preprocessor tests: hashes/briefs, input rejection, single-active guard,
  worker failure/restart, artifact path/integrity, faint closed-contour fill.
- Existing 7 silhouette-fit tests pass unchanged in behavior.
- Three real local neural generations inspected from default and side views in the existing GLB viewer.
- Browser integration test **replayed the stored real round-2 artifacts** with explicit
  `integration_test_replay:true`, without generating a fourth mesh: U20 selection/upload/job API,
  hash-checked GLB display, stale checksum 400, cross-origin 403, non-BUNNY disable, no JS errors.
  This is a UI/protocol test, not an extra model-quality or full fresh-inference E2E result.

Further progress needs a better sketch-conditioned/multiview model or an explicitly authorized
Meshy/provider integration, and a clear front/side reference. Do not keep tuning resolution alone:
round 3 demonstrates that higher grid resolution does not repair missing input or design drift.

References: [official code](https://github.com/VAST-AI-Research/TripoSR),
[technical report](https://arxiv.org/abs/2403.02151),
[official weights](https://huggingface.co/stabilityai/TripoSR).
