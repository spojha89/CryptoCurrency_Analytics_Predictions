import base64
import json

payload = {
    "crypto": "bitcoin",
    "price": 86655,
    "market_cap": 1724362434390.975,
    "24hr_vol": 45570139013.074196,
    "24hr_change": -1.0872773083855538
}

encoded = base64.b64encode(json.dumps(payload).encode()).decode()
print(encoded)