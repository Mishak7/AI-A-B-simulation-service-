import base64
import json
import requests

BASE_URL = "https://45.9.24.84/v1"
API_KEY = "inf12_synth_omni_07_29523cdda25035ffd5b43e4a4467b9c504f1"
MODEL = "Qwen3.5-397B-A17B-FP8"

# 1x1 red png
RED_DOT_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/"
    "l6lHAAAAAElFTkSuQmCC"
)

url = f"{BASE_URL}/chat/completions"

payload = {
    "model": MODEL,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image? Answer one word."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{RED_DOT_BASE64}"
                    },
                },
            ],
        }
    ],
    "temperature": 0,
}

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

r = requests.post(url, headers=headers, json=payload, timeout=60)

print("STATUS:", r.status_code)
print("HEADERS:", dict(r.headers))
print("TEXT:")
print(r.text)

try:
    print("JSON:")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except Exception:
    pass