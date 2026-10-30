# U21 · reviewed sketch input → neural 3D (experimental)

## Result, not a quality claim

The existing U20 → U21 client/server now supports **prepare → inspect foreground →
explicitly confirm → local neural inference → inspect/download GLB**. No inference may
start from the upload/preparation request alone. The current experimental engine is
**TripoSG-scribble**, directly conditioned on the sketch and a fixed, disclosed BUNNY prompt.
Its output uses a constant neutral material: it does NOT synthesize texture or recover eyes/nose markings.
Legacy TripoSR remains an explicit local configuration option, never a silent failure fallback.
Requested dimensions are recorded only; neither engine is dimension-calibrated, design-approved
or manufacturing-approved. This path does not automatically enter U22/U23 workflows.

## Initial TripoSR rounds (historical)

The requested Meshy screenshot quality was NOT reached in the initial three rounds below.
They are preserved failures, not current production-quality claims. No new model training was performed.

| Round | Changes | Actual result | Mesh |
|---|---|---|---|
| 1 | U2Net background removal, grid 128 | Torso/legs largely removed; rejected | 6,849 vertices / 13,702 faces |
| 2 | Faint sketch contour closing/fill, grid 192 | Whole body retained but too flat; not target quality | 8,308 / 16,612 |
| 3 | Existing local SD1.5 img2img (.55, 30 steps, seed 42, safety checker retained), then U2Net, grid 256 | Design drift and foreground loss; rejected, NOT promoted | 17,852 / 35,704 |

All used the same actual rabbit sketch from project processed data, not a fabricated successful example.
`results/learned3d-evaluation/iteration{1,2,3}/` contains actual GLB/condition/report files locally.
Round 1/2/3 reconstruction times on this Mac's MPS were approximately 10.1/10.2/10.9 seconds
(excluding segmentation, checkpoint downloads, hashing and SD conditioning). These are not general benchmarks.
The current preprocessing retains round 2's **contour** preservation; third-round SD design changes are
an evaluation-only script, not a hidden production transformation. Uploaded transparent PNGs
retain their supplied foreground alpha. No fourth TripoSR reconstruction was run in that initial three-round request.

## Implemented improvement: input review + sketch-specific model

1. Input preparation writes white-background preview.png, mask.png and preflight.json, with
   a preparation SHA binding the source brief/checksum, uploaded pixels, foreground and preview hashes.
2. The UI must display the preview and receive a separate explicit foreground confirmation.
   Dark-pixel coverage is a heuristic diagnostic, NOT semantic completeness or 3D accuracy.
3. Confirmation rechecks the brief and all prepared files. Stale/mutated/unconfirmed inputs do not queue.
4. TripoSG-scribble uses a fixed developer BUNNY prompt, seed42, 16steps, sketch confidence.4,
   prompt confidence1, 512latent tokens, non-flash dense SDF grid128. These are recorded assumptions,
   not automatic extraction/fulfilment of the whole U20 brief.
5. A normal-orientation check and constant neutral vertex color are explicit postprocessing.
   No rembg/RMBG-1.4 or SD middle-image conversion is used by this improved pipeline.

Actual follow-up generation: CLI1 + fresh browser/API2 = **3 TripoSG generations**, separate from
initial TripoSR3. All produced 21,927vertices / 43,866faces for this seed/device. The first browser
flow completed new inference/GLB display but failed the mobile overflow assertion; scoped CSS fixed
that issue and the next fresh browser flow passed. One run does not establish generalization.

Observed: head/torso/limbs regained visible volume instead of the previous thin sheet-like result.
Remaining: absent facial/color/fabric texture, ear/foot detail differences and surface artifacts.
**Meshy equivalence, expert design acceptance, scale and sewing/manufacturing remain unverified.**
A watertight mesh is not evidence of sewability. The current choice is an experimental local default,
not production acceptance. Exact input/foreground hashes are recorded with the confirmation.

### TripoSG setup on the existing AI runtime

Keep the base AI environment intact; isolate older compatibility libraries:

```sh
python -m pip install -r requirements-learned3d.txt
git clone https://github.com/VAST-AI-Research/TripoSG.git .models/TripoSG
git -C .models/TripoSG checkout fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c
python -m pip install --target .models/triposg-python --no-deps -r requirements-triposg-compat.txt
```

Download `VAST-AI/TripoSG-scribble` revision `e70b06bad2dece5b6a359aa8cd12f538cabd7095`
using `huggingface_hub.snapshot_download` (about4.7GB tensor weights, plus tokenizer/config).
Set engine:"TripoSG-scribble", python, triposg_source and triposg_weights absolute paths in
`.learned3d-local.json` (example provided). Official source/model are MIT; files are SHA-pinned
in `configs/ai/triposg-manifest.json` and verified locally before loading safetensors.
No model files are committed. SD/TripoSR weights are not required to run the sketch-specific path.

Official inference targets CUDA; this adapter was actually tested on this Mac's MPS/float16.
The non-flash decoder uses upstream scikit-image marching cubes at equal dense/hierarchical depth7,
avoiding CUDA-only refinement. Native diso is explicitly unavailable and fails if invoked, not silently
approximated. VAE queries use4096-point chunks to bound memory. CPU remains a slow possible device;
no CPU-performance or cross-hardware byte-reproduction guarantee is claimed.

Official bases: [TripoSG source](https://github.com/VAST-AI-Research/TripoSG),
[scribble weights](https://huggingface.co/VAST-AI/TripoSG-scribble),
[technical report](https://arxiv.org/abs/2502.06608).
The report describes the base shape/rectified-flow approach; the released scribble variant and
its inference arguments were verified in official code, not inferred from that report.
Hunyuan3D-2.1 was not adopted because its [shape license](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dshape/LICENSE)
explicitly excludes South Korea from the licensed territory.

## Legacy TripoSR setup

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
The UI first checks/shows prepared input/mask and requires confirmation, then polls the actual job,
checks artifact size/SHA-256 and shows/downloads input/GLB/report. Old servers without
requires_confirmation:true are disabled by the client; restart the local server after updating.
No browser path, shell fragment, URL, prompt, model path or arbitrary hyperparameter is accepted.

- `GET /api/learned3d/capabilities`
- `POST /api/learned3d/runs` → 201 **prepared, no inference**; strict JSON fields `image_base64`, `dimensions_mm`,
  `view:"single"`, `source_id`, `source_checksum`.
- `POST /api/learned3d/runs/{id}/confirm` → 202; exactly preparation_sha256 and foreground_confirmed:true.
- `GET /api/learned3d/runs/{id}` → prepared/queued/running/succeeded/failed.
- `GET /api/learned3d/artifacts/{id}/{name}` → preview.png/mask.png/preflight.json before confirmation; condition.png/model.glb/report.json only after success. Input/foreground private originals are never served.

Loopback Host and same-origin POST guards apply. Request ≤3MiB, decoded image ≤2MiB,
PNG/JPEG single frame, ≥32 pixels, ≤8M pixels. Model processes use no shell and have 1,200-second
inference timeout and60-second preparation timeout. One active neural 3D request, maximum 100 stored runs; shared one-worker GPU
executor serializes existing 2D AI and new 3D jobs. Restart marks preparing/queued/running jobs failed while prepared inputs remain inspectable.
Leaving the page does not cancel the server job. Inputs stay on this Mac; no paid API/cloud upload.

## Optional visible-surface sketch projection (experimental)

Only explicitly confirmed, successful TripoSG runs can produce a separate color derivative.
The UI keeps the original neutral mesh and downloads intact, with a separate projection viewer,
confirmation checkbox and immutable projected.glb/projection-report.json downloads.
No new model, learned texture, fabric material or recovered camera is involved. The CPU adapter
uses orthographic normalized-bbox mapping, foreground alpha, front-facing normals and a rasterized
z-buffer (2% depth tolerance); grazing-angle colors fade to neutral. Back/occluded surfaces remain neutral.

Settings are exactly yaw [-45,45] degrees, offset_x/offset_y [-.15,.15] in normalized bbox coordinates,
and scale [.8,1.2]. Positive offset_y moves sampled markings upward on the mesh. Both XY extents
are independently normalized: this is an approximate alignment, not perspective camera recovery.
Default alignment was visibly wrong (face too low); manual offset_y=.10 partly adjusted this example,
but smearing and design mismatch remain. It is NOT a passing quality candidate.

- Capabilities adds supports_projection:true for TripoSG only. Older servers hide the feature.
- POST /api/learned3d/runs/{parent_id}/projections: JSON≤64KiB, exactly parent_model_sha256,
  source_image_sha256 (confirmed foreground), settings, projection_confirmed:true; synchronous bounded
  CPU operation (60-second subprocess timeout), no shell/arbitrary paths. Returns201 including on reuse.
- GET /api/learned3d/projections/{id}: stored state/report.
- GET /api/learned3d/projection-artifacts/{id}/{name}: only successful projected.glb/projection-report.json,
  checked by size/SHA. Private foreground and worker logs are not served.
- Parent source brief/current hashes are checked before creation/reuse. Same parent/hash/settings reuses
  the same successful copy after verifying its artifacts; altered settings get a new UUID. One active
  CPU projection, maximum200 copies overall/20 per parent. Server restart fails incomplete jobs.
- Parent files are never overwritten. Export is reloaded and checked for float32 vertices and identical
  face indices. Geometry SHA and input/parent/adapter hashes are recorded. This is integrity validation,
  not a shape accuracy or sewing metric. Invalid/superseded inputs cannot silently substitute outputs.
- Files live under ignored results/sketch-projections/{uuid}/. No automatic remote/U22 handoff.

Reproducible opt-in browser check: tools/verify_projection_ui.mjs. Supply the explicit loopback URL,
absolute sketch/evidence paths and Playwright module/Chrome paths as shown in its header. This runs
a REAL new neural inference and CPU projection, so it is not part of model-free CI. Its source file
contains no local sketch data or credentials. Projection unit tests require numpy/scipy/Pillow/trimesh,
which CI installs without downloading model weights.

## Verification and next decision

- Latest full local Python211 pass, including14 new projection tests and13 learned3D service/preprocessor tests; JS14 pass;
  SQL/RLS105 pass with Auth/Storage doubles (not new live Supabase verification).
- The expanded13 cover no inference before confirmation, explicit boolean/hash, stale source,
  corrupted prepared input/preview, one-active queue, idempotent confirmation, worker failure without
  fallback, restart and timeout. CI installs small image/preprocessing dependencies, not model weights.
- Fresh browser flow on an isolated local server: upload/preflight, missing/false/stale confirmation
  rejected and GLB404 before confirmation, actual TripoSG inference, hash-checked GLB display,
  stale source400, cross-origin403, non-BUNNY disable,390px without overflow, no page errors.
  A separate old-server capability test also verified disabled submission/model POST0; its restart
  warning persists across the connection-initialization event.
  It is not a stored-result replay. The earlier replay test belongs only to initial TripoSR rounds.
- Actual evaluated outputs and immutable copies are in project processed data
  `04_데이터/가공/2026-10-30_스케치3D_개선/`. Existing production DB/U22 approvals were not changed.
- Follow-up actual browser check: one NEW TripoSG inference (~22.78s model portion), then REAL CPU
  projection (~1.63s), explicit confirmation, false/stale/range400 and foreign-origin403, immutable parent
  SHA, hash-checked projected files, idempotent reuse, private-log denial, source-switch reset and390px
  with no page errors/overflow. Earlier CPU prototypes2 + integrated1 are3 projections, not3 models.
  Stored actual evidence is project processed data 2026-10-30_스케치3D_원화투영/.
- Current code/test work does not verify a GitHub Actions/Pages deployment or Supabase model route.

Next: compare more held-out sketches and front/side references; define acceptable ear/foot details and
artist correction burden; improve facial/camera alignment and line smearing before considering
projection acceptance. Evaluate a separately licensed learned texture/backside approach if needed. Only after
explicit quality acceptance consider U22/remote integration, and keep scale/material/sewing validation separate.
