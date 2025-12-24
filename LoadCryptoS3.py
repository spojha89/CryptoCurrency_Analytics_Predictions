import json
import boto3
from collections import defaultdict
import base64
from datetime import datetime
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

# CONFIG
BUCKET = "suvus3bucket"
WINDOW = 10  # moving average window
price_buffer = defaultdict(list)  # in-memory buffer

def lambda_handler(event, context):
    """
    Lambda triggered by Kinesis.
    Each record from Kinesis should contain JSON like:
    {
        "bitcoin": {
            "usd": 87037,
            "usd_market_cap": 1738332206735.3381,
            "usd_24h_vol": 45102475159.332664,
            "usd_24h_change": 1.5662022163293967
        }
    }
    """
    logger.info("EVENT = %s", json.dumps(event))

    if 'Records' not in event:
        logger.error("Not a Kinesis event: %s", event)
        return {
            'statusCode': 400,
            'body': 'Not a Kinesis event'
        }

    for record in event['Records']:
        # Kinesis data is base64 encoded
        payload = base64.b64decode(record['kinesis']['data'])
        data = json.loads(payload)
        logger.info("Decoded payload: %s", data)

        # Extract crypto info
        crypto_id = list(data.keys())[0]      # 'bitcoin'
        crypto_data = data[crypto_id]

        ts = datetime.utcnow()  # current processing time

        price_usd = crypto_data['usd']
        market_cap_usd = crypto_data['usd_market_cap']
        hr24_volume = crypto_data['usd_24h_vol']
        hr24_change = crypto_data['usd_24h_change']

        # --- Compute simple moving average ---
        price_buffer[crypto_id].append(price_usd)
        if len(price_buffer[crypto_id]) > WINDOW:
            price_buffer[crypto_id].pop(0)
        ma_10 = sum(price_buffer[crypto_id]) / len(price_buffer[crypto_id])

        # --- Compute simple signal ---
        signal = "BUY" if price_usd > ma_10 else "SELL"

        # --- Prepare record for S3 ---
        enriched = {
            "timestamp": ts.isoformat() + "Z",
            "symbol": crypto_id,
            "price": price_usd,
            "ma_10": round(ma_10, 2),
            "signal": signal,
            "market_cap_usd": market_cap_usd,
            "hr24_volume": hr24_volume,
            "hr24_change": hr24_change
        }

        # --- Generate S3 key (partitioned by symbol/year/month/day) ---
        key = (
            f"symbol={crypto_id}/"
            f"year={ts.year}/month={ts.month:02d}/day={ts.day:02d}/"
            f"data-{int(ts.timestamp())}.json"
        )

        # --- Write to S3 ---
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=json.dumps(enriched)
        )
        logger.info("Written record to S3: %s", key)

    return {"status": "success", "records_processed": len(event['Records'])}
