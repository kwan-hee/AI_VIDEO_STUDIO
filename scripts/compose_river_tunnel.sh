#!/usr/bin/env sh
# 하저터널 5장면 Kling 클립을 내려받아 한 편으로 합친다.
# CDN 접근이 가능한 환경에서 실행한다. ffmpeg 필요.
set -eu

OUT_DIR="${1:-output/river_tunnel}"
RESULT="$OUT_DIR/result.json"
FINAL="$OUT_DIR/river_tunnel_final.mp4"

mkdir -p "$OUT_DIR"

python3 - "$RESULT" "$OUT_DIR" <<'PY'
import json, sys
result, out_dir = sys.argv[1], sys.argv[2]
with open(result, encoding="utf-8") as f:
    data = json.load(f)
for clip in data["clips"]:
    print(f"{clip['key']}\t{clip['url']}")
PY

python3 - "$RESULT" "$OUT_DIR" <<'PY' > "$OUT_DIR/concat.txt"
import json, sys
result, out_dir = sys.argv[1], sys.argv[2]
with open(result, encoding="utf-8") as f:
    data = json.load(f)
for clip in sorted(data["clips"], key=lambda c: c["order"]):
    print(f"file '{clip['key']}.mp4'")
PY

python3 - "$RESULT" "$OUT_DIR" <<'PY' | while IFS="$(printf '\t')" read -r key url; do
    [ -f "$OUT_DIR/$key.mp4" ] || curl -sS -L --retry 3 -o "$OUT_DIR/$key.mp4" "$url"
    echo "받음: $key.mp4"
done
import json, sys
result, out_dir = sys.argv[1], sys.argv[2]
with open(result, encoding="utf-8") as f:
    data = json.load(f)
for clip in sorted(data["clips"], key=lambda c: c["order"]):
    print(f"{clip['key']}\t{clip['url']}")
PY

# 모든 클립이 720x1280 / 동일 코덱이므로 재인코딩 없이 이어 붙인다.
ffmpeg -y -f concat -safe 0 -i "$OUT_DIR/concat.txt" -c copy "$FINAL"
echo "완성: $FINAL"
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$FINAL"
