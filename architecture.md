# Architecture (ARCHITECTURE) — SAEA

## System context (C4 Level 1)

```
Teacher (browser, PWA) --HTTPS--> FastAPI backend --SQL/vector--> PostgreSQL 16 + pgvector
                                        |
                                        v
                               ONNX Runtime (CPU)
                          (SCRFD-2.5GF, ArcFace MobileFaceNet INT8)
```

## Containers (C4 Level 2)

- **frontend** (React + Vite + TS PWA, served via nginx or Vite preview in prod, package-managed with pnpm)
- **backend** (FastAPI, Python 3.11, ONNX Runtime, runs in a single container, threadpool for CPU-heavy inference)
- **db** (`pgvector/pgvector:pg16` image)

## Face pipeline (Pipe-and-Filter)

1. **Decode**: incoming WebP burst → BGR ndarray via OpenCV, in memory only.
2. **Detect (SCRFD-2.5GF, `det_2.5g.onnx`)**: bounding boxes only — this model has no keypoint output (confirmed empirically: 6 output tensors).
3. **Extract landmarks (`2d106det.onnx`)**: run per detected face crop, producing 106 2D points; index-mapped down to the 5 standard points (left eye, right eye, nose tip, left mouth corner, right mouth corner).
4. **Align**: affine transform to canonical 112×112 crop using those 5 points.
5. **Embed (ArcFace ResNet50, `w600k_r50.onnx`, fp32)**: 512-d vector via ONNX Runtime, AVX2/AVX-512 CPU path.
6. **Match**: cosine similarity search against `student_biometrics.embedding` using the HNSW index in pgvector, threshold ≥ 0.42.
7. **Discard**: raw frame and intermediate crops are dropped from memory; nothing is written to disk (constitution.md Article 2).

### Model acquisition

All three ONNX files (`det_2.5g.onnx`, `2d106det.onnx`, `w600k_r50.onnx`) come from the official InsightFace `buffalo_m` pack, fetched via the official `insightface` PyPI package's own auto-download mechanism (not a hand-written URL+checksum script — no single stable "official" standalone URL exists for these individual files; see the decision notes in `spec.md` §2 RF-02/RF-03). `backend/scripts/download_models.py` triggers this download once, then copies the three files out of the package's cache directory into `backend/models_data/` for the app to load directly via `onnxruntime`, independent of the `insightface` package at inference time.

## Concurrency

FastAPI's event loop stays free for I/O; CPU-bound inference steps (2–4 above) run via `asyncio.to_thread()` so one slow burst does not block other requests.

## State management decision (frontend)

Chosen: **Zustand**, single store at `frontend/src/store/attendanceStore.ts`. Rationale: minimal boilerplate for a small app, works well with the offline queue in `offlineSync.ts`. This decision is binding — do not introduce Redux/Context duplicating this store without updating this file first.

## Directory structure

```
SAEA/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/        # attendance.py, students.py, courses.py
│   │   ├── core/                    # config.py, security.py, logging.py
│   │   ├── models/                  # database.py, schemas.py
│   │   ├── services/                # face_detection.py, alignment.py, face_recognition.py, attendance.py
│   │   ├── db/                      # session.py, repositories/, migrations/
│   │   ├── utils/                   # image_processing.py
│   │   └── main.py
│   ├── tests/{unit,integration,performance,fixtures}/
│   ├── models_data/                 # .onnx files (gitignored)
│   ├── docker/Dockerfile
│   ├── requirements/{base,dev,prod}.txt
│   └── scripts/{download_models.py, init_db.py}
├── frontend/
│   ├── src/{api,components,pages,hooks,services,store,types}/
│   ├── docker/Dockerfile
│   ├── package.json                 # pnpm only
│   └── vite.config.ts
├── docs/{architecture,api,user-guide}/
└── (root .md files listed in README.md)
```

## Data purge strategy

`student_biometrics` rows are deleted via `ON DELETE CASCADE` when a student record is deleted. No soft-delete of embeddings — biometric data is either fully present or fully gone.