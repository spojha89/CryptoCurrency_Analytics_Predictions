import json
import boto3
import os
import base64
from datetime import datetime, timedelta
from decimal import Decimal
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
raw_table = dynamodb.Table(os.environ['RAW_TABLE'])
agg_table = dynamodb.Table(os.environ['AGG_TABLE'])

# Bucket size in seconds (5-min = 300 sec)
BUCKET_SIZE = 300
MOVING_WINDOW_MINUTES = 30

def lambda_handler(event, context):
    logger.info("EVENT = %s", json.dumps(event))

    if 'Records' not in event:
        logger.error("Not a Kinesis event: %s", event)
        return {
            'statusCode': 400,
            'body': 'Not a Kinesis event'
        }
    
    for record in event['Records']:
        # Kinesis data is base64 encoded so decode here
        payload = base64.b64decode(record["kinesis"]["data"])
        logger.info(payload)
        data = json.loads(payload, parse_float=Decimal)
        logger.info(data)
        crypto_id = list(data.keys())[0]      # 'bitcoin'
        crypto_data = data[crypto_id]

        try:
            raw_table.put_item(Item={
                'crypto_id':crypto_id,
                'loading_time':int(datetime.now().timestamp()), #in timestamp
                'price_usd':crypto_data['usd'],
                'market_cap_usd':crypto_data['usd_market_cap'],
                'hr24_volume':crypto_data['usd_24h_vol'],
                'hr24_change':crypto_data['usd_24h_change']
        })


        except Exception as e:
            logger.error(e)
            logger.error("Error while inserting data into DynamoDB")
            raise e
        
        # --- 2. Compute bucket key ---
        # bucket_time = (ts // BUCKET_SIZE) * BUCKET_SIZE

        # --- 3. Update aggregate table ---
        # try:
        #     agg_table.update_item(
        #         Key={
        #             'crypto_id': crypto_id,
        #             'time_window': bucket_time
        #         },
        #         UpdateExpression="ADD #sum :p, #count :c",
        #         ExpressionAttributeNames={
        #             '#sum': 'sum',
        #             '#count': 'count'
        #         },
        #         ExpressionAttributeValues={
        #             ':p': crypto_data['usd'],
        #             ':c': 1
        #         }
        #     )
        # except Exception as e:
        #     logger.error(f"Error updating aggregate table: {e}")
        #     continue

        try:
            # Get the last 30-minutes data
            start_time = int((datetime.now() - timedelta(minutes=MOVING_WINDOW_MINUTES)).timestamp())
            end_time = int(datetime.now().timestamp())
            response = raw_table.query(
                KeyConditionExpression='crypto_id = :crypto_id AND loading_time BETWEEN :start_time AND :end_time',
                ExpressionAttributeValues={
                    ':crypto_id': crypto_id,
                    ':start_time': start_time,
                    ':end_time': end_time
                }
            )

            # Calculate the average price, min, max price, percentage of change of current price with respect to avg price
            total_price = 0
            
            for item in response['Items']:
                total_price += item['price_usd']

            avg_price = total_price / len(response['Items'])

            #Finding min price
            min_price = min(item['price_usd'] for item in response['Items'])

            #Finding max price
            max_price = max(item['price_usd'] for item in response['Items'])

            #Finding percentage of change in avg price with respect to current price
            percentage_change = ((crypto_data['usd'] - avg_price) / avg_price) * 100
            percentage_change = round(percentage_change, 2)

            #If percentage of change > +2%, then bullish, percentage of change < -2%, then bearish
            #SNS notification can be added. Placeholder. 
            if percentage_change > 0.2:
                print("Bullish")

            elif percentage_change < -0.2:
                print("Bearish")

            else:
                print("Neutral")
            


            # Insert the average price into the aggregate table
            agg_table.put_item(Item={
                'crypto_id': crypto_id,
                'time_window': int(datetime.now().timestamp()),
                'avg_type': '30min_moving_average',
                'price_usd': avg_price,
                'min_price': min_price,
                'max_price': max_price,
                'percentage_change': percentage_change
            })
        except Exception as e:
            logger.error(f"Error calculating average price: {e}")
            continue

        


    return {
        'statusCode': 200,
        'body': json.dumps('Program completed successfully')
    }
