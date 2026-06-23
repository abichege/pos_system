import time
import math
import base64
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
load_dotenv()
import os

consumer_key=os.getenv("consumer_key")
consumer_secret=os.getenv("consumer_secret")
token_api=os.getenv("token_api")
saf_short_code=os.getenv("saf_short_code")
saf_stk_push_url=os.getenv("saf_stk_push_url")
saf_api_url = os.getenv("saf_api_url")
saf_pass_key=os.getenv("saf_pass_key")
my_callback_url=os.getenv("my_callback_url")

# time will be sent to the stk push
# the request is for sending http like axios
# math is for converting into an integer
# base 64 is for hashing for security
# http basicAuth is used to get token for authentication

def get_mpesa_access_token():
    try:
        print("consumer_key:", consumer_key)
        print("saf_api_url:", saf_api_url)
        res = requests.get(
            saf_api_url,
            auth=HTTPBasicAuth(consumer_key, consumer_secret),
        )
        token = res.json()['access_token']

    except Exception as e:
        print(str(e), "error getting access token")
        raise e

    return token

myToken=get_mpesa_access_token()
print(myToken)

timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

headers = {
            "Authorization": f"Bearer {myToken}",
            "Content-Type": "application/json"
        }

def generate_password():

    password_str = saf_short_code + saf_pass_key + timestamp
    password_bytes = password_str.encode()

    return base64.b64encode(password_bytes).decode("utf-8")

password=generate_password()
print(password)

def make_stk_push( payload):
    amount = payload['amount']
    phone_number = payload['phone_number']

    push_data = {
        "BusinessShortCode":saf_short_code,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": math.ceil(float(amount)),
        "PartyA": phone_number,
        "PartyB": saf_short_code,
        "PhoneNumber": phone_number,
        "CallBackURL": my_callback_url,
        "AccountReference": "Whatever you call your app",
        "TransactionDesc": "description of the transaction",
    }

    response = requests.post(
        saf_stk_push_url,
        json=push_data,
        headers=headers)

    response_data = response.json()

    return response_data

# c=make_stk_push({
#     "amount":"1",
#     "phone_number":"254790218190"
# })
# print(c)