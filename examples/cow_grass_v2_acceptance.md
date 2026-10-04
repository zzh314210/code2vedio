# Cow Grass V2 Acceptance Record

Historical acceptance date: 2026-10-04

The local test videos listed below have been deleted during the pipeline cleanup. This record describes their past acceptance results, not currently available deliverables or acceptance of the refactored project pack. Regenerated videos require fresh review.

## Historical Deliverables (Deleted)

- Landscape master: `workspace/9420f0c89126/output/final.mp4`
  - 1920x1080, 30 fps, approximately 120.667 seconds.
  - H.264 video, AAC mono narration, and Chinese `mov_text` subtitle tracks.
- Portrait reflow: `workspace/be9bf5b8c87f/output/final.mp4`
  - 1080x1920, 30 fps, approximately 120.667 seconds.
  - Independently laid out for portrait; it is not a crop of the landscape video.
- V1 test video (also deleted): `workspace/1ffb73363c20/output/final.mp4`

## Content verification

- Teaching problem: 10 cows eat for 22 days, 16 cows eat for 10 days; find how long 25 cows eat.
- Growth rate: `G = (220 - 160) / (22 - 10) = 5 units/day`.
- Initial stock: `Q = (10 - 5) x 22 = 110 units`.
- Net consumption for 25 cows: `25 - 5 = 20 units/day`; therefore `T = 110 / 20 = 5.5 days`.
- Check: `25 x 5.5 = 110 + 5 x 5.5 = 137.5`; the visual ratio bar uses `110 : 27.5 = 4 : 1`.
- The two conditions are independent scenarios from the same initial stock; ?5 cows offset growth? is an equivalent grouping, not a cow swap over time.

## Audio, subtitles, and assets

- TTS: Edge `zh-CN-XiaoxiaoNeural`, rate `+6%`, actual narration about 120.667 seconds.
- Each video contains 36 sentence-level short subtitle cues; SRT is UTF-8, monotonic, and non-overlapping.
- Cow, herb, seedling, and sun visuals use a consistent Noto color SVG style from the public, login-free Iconify SVG API.
- Asset records: `assets.json` and `ATTRIBUTION.md` in each output directory.
- License text: `examples/assets/noto/LICENSE-graphics.txt`.

## Review boundary

- Manual frame review covered the light background, safe text areas, icons, formulas, stock animation, and subtitle placement in both orientations.
- FFmpeg from the project virtual environment verified resolution, tracks, duration, and non-zero audio.
- This lesson has `vision.enabled=false`; it must not be described as having passed external automatic visual review. `manual_review_required=true` is recorded in `course_version.json`.
- The Web panel can enable a configured vision model and continue or rerun the lesson for automatic visual feedback.
