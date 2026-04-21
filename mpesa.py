import time
import math
import base64
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth

consumer_key="D0P7CG8WveDoky1GjOFcrF9jn5cId1OkXxVesHdwLc1VLMog"
consumer_secret="LlGUxE3wHED0AnkJkVz0zWX7I2AnPQ3GQzXMKD4EuRAGhLwk31yu9nP5nDqkQlSA"
token_api="https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
saf_short_code="174379"
saf_stk_push_url="https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
saf_api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
saf_pass_key="bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
my_callback_url="https://payphone-despite-unrigged.ngrok-free.dev/stk-call-back"

# time will be sent to the stk push
# the request is for sending http like axios
# math is for converting into an integer
# base 64 is for hashing for security
# http basicAuth is used to get token for authentication

def get_mpesa_access_token():
    try:
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