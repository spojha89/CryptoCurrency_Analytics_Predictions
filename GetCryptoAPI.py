import json
import requests
import os
import boto3

def lambda_handler(event, context):

    # aws kinesis
    kinesis = boto3.client('kinesis', region_name='us-east-1')

    crypto_map = {
            'bitcoin': 'BTC',
            'ethereum': 'ETH',
            'solana': 'SOL',
            'cardano': 'ADA'
        }

    data = []

    try:
        for crypto_full,crypto_symbol in crypto_map.items():
            url = "https://api.coingecko.com/api/v3/simple/price?vs_currencies=usd&ids="+crypto_full+"&names="+crypto_full.capitalize()+"&symbols="+crypto_symbol
            headers = {"x-cg-demo-api-key": os.environ['coingecko_api_key']}
            response = requests.get(url, params={'vs_currencies': 'usd', 'include_market_cap': 'true', 'include_24hr_vol': 'true',
            'include_24hr_change': 'true'}, headers=headers)
            # print(response.text)

            kinesis.put_record(
                StreamName=os.environ['KINESIS_DATASTREAM'],
                Data=json.dumps(response.json()),
                PartitionKey=crypto_full
            )
            print("Data sent to Kinesis")

            data.append({
                'crypto': crypto_full,
                'price': response.json()[crypto_full]['usd'],
                'market_cap': response.json()[crypto_full]['usd_market_cap'],
                '24hr_vol': response.json()[crypto_full]['usd_24h_vol'],
                '24hr_change': response.json()[crypto_full]['usd_24h_change']
            })
        print(data)
    except Exception as e:
        print(e)
        raise e
        exit(1)

    return {
        'statusCode': 200,
        'body': json.dumps('Executed Successfully!!')
    }
