import os

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from send_email import email

# Load environment variables from .env file
load_dotenv()

# Debug (remove in production)
print("CLOUDINARY_CLOUD_NAME:", os.getenv("CLOUDINARY_CLOUD_NAME"))
print("CLOUDINARY_API_KEY:", os.getenv("CLOUDINARY_API_KEY"))
print("CLOUDINARY_API_SECRET:", os.getenv("CLOUDINARY_API_SECRET"))

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

def upload_pdf(pdf_file):
    """
    Upload a PDF receipt to Cloudinary and email the receipt link.
    
    Args:
        pdf_file (str): File name without the .pdf extension.
    
    Returns:
        str: "success" if upload and email succeed.
    """
    try:
        file_path = f"receipts/{pdf_file}.pdf"

        # Upload PDF
        result = cloudinary.uploader.upload(
            file_path,
            resource_type="raw"
        )

        receipt_url = result["secure_url"]

        print("Cloudinary upload successful")
        print(receipt_url)

        # Send email
        email(
            "liquidambish@gmail.com",
            "Payment Received",
            f"Thank you. We have received your payment.\n\n"
            f"Receipt: {receipt_url}"
        )

        return "success"

    except Exception as e:
        print(f"Upload failed: {e}")
        return "failed"


# Example
# upload_pdf("UDS482XO0S")