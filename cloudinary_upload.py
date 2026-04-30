import cloudinary
import cloudinary.uploader
from send_email import email

CLOUDINARY_URL="denlwa9bs"
API_KEY="211965476343423"
API_SECRET="wb0pNDAsCV9vCb_dia-zenyh_h8"

cloudinary.config(
    cloud_name=CLOUDINARY_URL,
    api_key=API_KEY,
    api_secret=API_SECRET
)

def upload_pdf(pdf_file):
    res=cloudinary.uploader.upload(f"receipts/{pdf_file}.pdf")

    print("this is cloudinary---------")
    print(res["secure_url"])
    email("liquidambish@gmail.com","Payment Received",f"Thank You we have received your payment.Here is a link to your receipt-> {res['secure_url']}")
    return "success"

# upload_pdf("UDS482XO0S")


