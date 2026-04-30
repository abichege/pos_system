import requests

# ELASTIC_API_KEY="2B28E98BD104B7199C3E994B81D6CAE5D7B93C93C4151CBE6DAD634F08C600C06EEBEFE7C282081ED46E4C4874360FA0"
# FROM_EMAIL="abigaelchege4@gmail.com"
# # url = "https://api.elasticemail.com/v2/email/send"

# def send_email(to, subject, message):
#     data={"apiKey":ELASTIC_API_KEY,"subject":subject,"from":FROM_EMAIL,"to":to,"bodytext":message}
#     res=requests.post(url,data=data)
#     print(res)
#     return res.status_code

# send_email("liquidambish@gmail.com","testing email","I am testing api")

import mailtrap as mt
MAILTRAP_API_KEY="72cd2ecfbb905ac0004efaac94829970"

def email(to,subject,message):
    mail = mt.Mail(
        sender=mt.Address(email="hello@demomailtrap.co", name="Flask API"),
        to=[mt.Address(email=to)],
        subject=subject,
        text=message,
        category="Integration Test",
    )

    client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
    response = client.send(mail)

    print(response)
    print("this is mailtrap--------")

# email("liquidambish@gmail.com"," Testing APi 1","I am testing api")    

