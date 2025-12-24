import json
import boto3
from decimal import Decimal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB tables
dynamodb = boto3.resource('dynamodb')
raw_table = dynamodb.Table('crypto_raw')
agg_table = dynamodb.Table('crypto_agg')

# Bucket size in seconds (5-min = 300 sec)
BUCKET_SIZE = 300
MOVING_WINDOW_MINUTES = 30

def lambda_handler(event, context):
    for record in event['Records']:
        # Decode Kinesis payload
        payload = json.loads(record["kinesis"]["data"])
        crypto_id = payload['crypto']
        price = Decimal(str(payload['price_usd']))
        ts = int(datetime.now().timestamp())

        # --- 1. Store raw data ---
        raw_table.put_item(
            Item={
                'crypto_id': crypto_id,
                'loading_time': ts,
                'price_usd': price
            }
        )

        # --- 2. Compute bucket key ---
        bucket_time = (ts // BUCKET_SIZE) * BUCKET_SIZE

        # --- 3. Update aggregate table ---
        try:
            agg_table.update_item(
                Key={
                    'crypto_id': crypto_id,
                    'bucket_time': bucket_time
                },
                UpdateExpression="ADD #sum :p, #count :c",
                ExpressionAttributeNames={
                    '#sum': 'sum',
                    '#count': 'count'
                },
                ExpressionAttributeValues={
                    ':p': price,
                    ':c': 1
                }
            )
        except Exception as e:
            logger.error(f"Error updating aggregate table: {e}")
            continue

        # --- 4. Compute 30-min moving average ---
        # Get all buckets in last 30 minutes
        start_ts = ts - MOVING_WINDOW_MINUTES*60
        start_bucket = (start_ts // BUCKET_SIZE) * BUCKET_SIZE

        response = agg_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('crypto_id').eq(crypto_id) & 
                                   boto3.dynamodb.conditions.Key('bucket_time').between(start_bucket, bucket_time)
        )

        total_sum = Decimal('0')
        total_count = 0

        for item in response['Items']:
            total_sum += item.get('sum', Decimal('0'))
            total_count += item.get('count', 0)

        moving_avg = total_sum / total_count if total_count > 0 else None

        logger.info(f"Crypto: {crypto_id}, 30-min MA: {moving_avg}")
        
        # Optional: store moving average in aggregate table
        agg_table.update_item(
            Key={
                'crypto_id': crypto_id,
                'bucket_time': bucket_time
            },
            UpdateExpression="SET moving_avg = :ma",
            ExpressionAttributeValues={
                ':ma': moving_avg
            }
        )

    return {"statusCode": 200}
