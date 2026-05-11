# import africastalking

# username="sandbox"
# API_key="atsk_9c1a8e8f65f5f9ba993de149d63a5bc7514dbacc65d46af2831b65cf322690448acf709c"

# africastalking.initialize(username,API_key)
# sms=africastalking.SMS

# def send_sms(phone, message):
#     try:
#         # Phone must be in international format e.g. +254790218190
#         response = sms.send(message, [f"+{phone}"])
#         print("SMS response:", response)
#         return response
# #     except Exception as e:
# #         print("SMS error:", str(e))
# #         return None
# import africastalking
# import requests
# from requests.adapters import HTTPAdapter

# username="sandbox"
# api_key="atsk_9c1a8e8f65f5f9ba993de149d63a5bc7514dbacc65d46af2831b65cf322690448acf709c"

# africastalking.initialize(username, api_key)

# # Patch the session to skip SSL verification
# session = requests.Session()
# session.verify = False
# africastalking.SMS._session = session

# sms = africastalking.SMS

# def send_sms(phone, message):
#     try:
#         response = sms.send(message, [f"+{phone}"])
#         print("SMS response:", response)
#         return response
#     except Exception as e:
#         print("SMS error:", str(e))
#         return None
import requests
import certifi
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AT_USERNAME = "sandbox"
AT_API_KEY  ="atsk_9c1a8e8f65f5f9ba993de149d63a5bc7514dbacc65d46af2831b65cf322690448acf709c"


def send_sms(phone, message):
    try:
        response = requests.post(
            "https://api.sandbox.africastalking.com/version1/messaging",
            headers={
                "apiKey": AT_API_KEY,
                "Accept": "application/json"
            },
            data={
                "username": AT_USERNAME,
                "to":       f"+{phone}",
                "message":  message
            },
            verify=certifi.where()  # ← use certifi's cert bundle
        )
        print("SMS response:", response.json())
        return response.json()
    except Exception as e:
        print("SMS error:", str(e))
        return None