#!/usr/bin/env bash
# Check one smoke conversion result: the file exists, opens with a YAML header
# that reports `ok`, and carries a body. The body is measured in non-blank
# characters rather than lines, because a converter is free to join or split
# lines; what separates a real conversion from an empty result that still
# parses is how much text arrived.
set -euo pipefail

result="$1"
minimum_body_chars="${2:-100}"

test -f "$result" || {
  echo "no result at $result" >&2
  exit 1
}

head -n 1 "$result" | grep -qx -- '---' || {
  echo "result does not open with a YAML header" >&2
  exit 1
}

grep -qx 'status: ok' "$result" || {
  echo "result is not status: ok" >&2
  sed -n '1,20p' "$result" >&2
  exit 1
}

body_chars=$(awk 'body { print } /^---$/ { if (++fence == 2) body = 1 }' "$result" |
  tr -d '[:space:]' | wc -c)
if [ "$body_chars" -lt "$minimum_body_chars" ]; then
  echo "body holds $body_chars non-blank character(s), expected at least $minimum_body_chars" >&2
  exit 1
fi

echo "$result: header ok, $body_chars non-blank body character(s)"
