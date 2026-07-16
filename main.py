import psycopg2
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, scoped_session
from database import Base, User, Product, Sale, Payment, Stock
from datetime import datetime, timedelta
from mpesa import make_stk_push
from generate_pdf import generate_pdf
# from sms import send_sms
from dotenv import load_dotenv
load_dotenv()
import os


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")

CORS(app, supports_credentials=True, origins=["https://abipos.co.ke",
            "https://www.abipos.co.ke"])

jwt = JWTManager(app)
bcrypt = Bcrypt(app)

MY_DATABASE_URL = os.getenv("MY_DATABASE_URL")

engine = create_engine(
    MY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300
)
engine = create_engine(
    MY_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300
)

# scoped_session gives each thread/request its own Session automatically
SessionLocal = scoped_session(sessionmaker(bind=engine))

# Create tables automatically
Base.metadata.create_all(engine)

allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

# How long a Pending payment blocks a retry in /stk-push.
# This is ONLY a retry gate — it does NOT auto-expire payments.
# Status only changes to Paid/Unpaid when Safaricom sends a callback.
PENDING_TIMEOUT_SECONDS = 20


@app.route('/', methods=allowed_methods)
def home():
    method = request.method.lower()
    if method == "get":
        return jsonify({"Flask API": "POS System v1.0"}), 200
    else:
        return jsonify({"msg": "Method not allowed"}), 405


@app.route('/register', methods=allowed_methods)
def register():
    try:
        method = request.method.lower()

        if method == "post":
            data = request.get_json()

            if data["full_name"] == "" or data["email"] == "" or data["password"] == "":
                return jsonify({"msg": "Full name, email and password cannot be empty"}), 400

            existing_user = SessionLocal.query(
                User).filter_by(email=data["email"]).first()
            if existing_user:
                return jsonify({"msg": "Email already registered"}), 409

            hashed_password = bcrypt.generate_password_hash(
                data["password"]).decode("utf-8")

            new_user = User(
                full_name=data["full_name"],
                email=data["email"],
                password=hashed_password,
                created_at=datetime.utcnow()
            )
            SessionLocal.add(new_user)
            SessionLocal.commit()

            token = create_access_token(identity=data["email"])

            return jsonify({"msg": "User registered successfully", "token": token}), 201

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/login', methods=allowed_methods)
def login():
    try:
        method = request.method.lower()

        if method == "post":
            data = request.get_json()

            email = data.get("email")
            password = data.get("password")

            if not email or not password:
                return jsonify({"msg": "Email and password required"}), 400

            query = select(User).where(User.email == email)
            user = SessionLocal.scalars(query).first()

            if not user:
                return jsonify({"msg": "Invalid email"}), 401

            if not bcrypt.check_password_hash(user.password, password):
                return jsonify({"msg": "Invalid password"}), 401

            token = create_access_token(identity=email)

            return jsonify({
                "msg":   "Login successful",
                "user":  {
                    "id":        user.id,
                    "full_name": user.full_name,
                    "email":     user.email
                },
                "token": token
            }), 200

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/products', methods=allowed_methods)
@jwt_required()
def products():
    try:
        method = request.method.lower()
        email = get_jwt_identity()

        user = SessionLocal.scalars(
            select(User).where(User.email == email)).first()

        if method == "get":
            product_list = []
            query = select(Product)
            all_products = list(SessionLocal.scalars(query).all())

            for product in all_products:
                product_list.append({
                    "id":         product.id,
                    "user_id":    product.user_id,
                    "name":       product.name,
                    "amount":     product.amount,
                    "created_at": product.created_at.isoformat()
                })

            return jsonify({"data": product_list}), 200

        elif method == "post":
            data = request.get_json()

            if data["name"] == "" or data["amount"] == "":
                return jsonify({"msg": "All fields required"}), 400

            new_product = Product(
                user_id=user.id,
                name=data["name"],
                amount=float(data["amount"]),
                created_at=datetime.utcnow()
            )
            SessionLocal.add(new_product)
            SessionLocal.commit()

            return jsonify({"msg": "Product added successfully"}), 201

        elif method == "put":
            data = request.get_json()

            if not data.get("id"):
                return jsonify({"error": "id is required"}), 400

            if not data.get("name") or data.get("amount") is None:
                return jsonify({"error": "name and amount are required"}), 400

            product = SessionLocal.scalars(
                select(Product).where(Product.id == data["id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            product.name = data["name"]
            product.amount = float(data["amount"])
            SessionLocal.commit()
            return jsonify({"msg": "Product updated"}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("id"):
                return jsonify({"error": "id is required"}), 400

            product = SessionLocal.scalars(
                select(Product).where(Product.id == data["id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            related_sales = SessionLocal.scalars(
                select(Sale).where(Sale.product_id == data["id"])
            ).all()

            for sale in related_sales:
                if sale.payment:
                    SessionLocal.delete(sale.payment)
                SessionLocal.delete(sale)

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["id"])
            ).first()
            if stock_entry:
                SessionLocal.delete(stock_entry)

            SessionLocal.delete(product)
            SessionLocal.commit()
            return jsonify({"msg": "Product deleted"}), 200

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/sales', methods=allowed_methods)
@jwt_required()
def sales():
    try:
        method = request.method.lower()

        if method == "get":
            sales_list = []
            query = select(Sale)
            all_sales = list(SessionLocal.scalars(query).all())

            # NOTE: We do NOT auto-expire Pending payments here.
            # Only the /stk-call-back should change status to Paid or Unpaid.
            # Safaricom callbacks can take 30-60s, so expiring at 20s
            # would kill legitimate in-flight payments before they confirm.

            for sale in all_sales:
                sales_list.append({
                    "id":         sale.id,
                    "product_id": sale.product_id,
                    "created_at": sale.created_at.isoformat(),
                    "product": {
                        "id":     sale.product.id,
                        "name":   sale.product.name,
                        "amount": sale.product.amount
                    } if sale.product else None,
                    "payment": {
                        "id":           sale.payment.id,
                        "trans_code":   sale.payment.trans_code,
                        "trans_amount": sale.payment.trans_amount,
                        "phone_paid":   sale.payment.phone_paid,
                        "status":       sale.payment.status
                    } if sale.payment else None
                })

            return jsonify({"data": sales_list}), 200

        elif method == "post":
            data = request.get_json()

            if not data.get("product_id"):
                return jsonify({"msg": "product_id is required"}), 400

            product = SessionLocal.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not product:
                return jsonify({"msg": "Product not found"}), 404

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if not stock_entry or stock_entry.quantity < 1:
                return jsonify({"error": f"'{product.name}' is out of stock"}), 400

            new_sale = Sale(
                product_id=data["product_id"],
                created_at=datetime.utcnow()
            )
            SessionLocal.add(new_sale)
            SessionLocal.flush()

            stock_entry.quantity -= 1
            stock_entry.updated_at = datetime.utcnow()

            SessionLocal.commit()
            return jsonify({"msg": "Sale created successfully", "sale_id": new_sale.id}), 201

        elif method == "put":
            data = request.get_json()

            if not data.get("sale_id"):
                return jsonify({"error": "sale_id is required"}), 400

            sale = SessionLocal.scalars(
                select(Sale).where(Sale.id == data["sale_id"])
            ).first()

            if not sale:
                return jsonify({"error": "Sale not found"}), 404

            if not data.get("product_id"):
                return jsonify({"error": "product_id is required"}), 400

            new_product = SessionLocal.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not new_product:
                return jsonify({"error": "Product not found"}), 404

            new_stock = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if not new_stock or new_stock.quantity < 1:
                return jsonify({"error": f"'{new_product.name}' is out of stock"}), 400

            old_stock = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == sale.product_id)
            ).first()

            if old_stock:
                old_stock.quantity += 1
                old_stock.updated_at = datetime.utcnow()

            new_stock.quantity -= 1
            new_stock.updated_at = datetime.utcnow()

            sale.product_id = data["product_id"]
            SessionLocal.commit()
            return jsonify({"msg": "Sale updated successfully"}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("sale_id"):
                return jsonify({"error": "sale_id is required"}), 400

            sale = SessionLocal.scalars(
                select(Sale).where(Sale.id == data["sale_id"])
            ).first()

            if not sale:
                return jsonify({"error": "Sale not found"}), 404

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == sale.product_id)
            ).first()

            if stock_entry:
                stock_entry.quantity += 1
                stock_entry.updated_at = datetime.utcnow()

            if sale.payment:
                SessionLocal.delete(sale.payment)

            SessionLocal.delete(sale)
            SessionLocal.commit()
            return jsonify({"msg": "Sale deleted successfully"}), 200

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/stk-push', methods=allowed_methods)
@jwt_required()
def stk_push():
    """
    Safe STK push with upsert logic:
    1. Reject immediately if sale is already Paid.
    2. Reject if a Pending payment exists and is < PENDING_TIMEOUT_SECONDS old.
    3. If timed-out Pending or Unpaid or no row yet → call Safaricom.
    4. Only write/update DB row AFTER Safaricom returns mrid + crid.
    5. Always UPDATE existing row if one exists (never blind INSERT) to
       avoid the UniqueViolation on payments_sale_id_key.
    """
    try:
        data = request.get_json()

        sale_id      = data.get("sale_id")
        trans_amount = data.get("amount")
        phone_paid   = data.get("phone_number")

        if sale_id is None or trans_amount is None or phone_paid is None:
            return jsonify({"error": "sale_id, phone_number and amount are required"}), 400

        # ── Check existing payment for this sale ──────────────────────────────
        existing_payment = SessionLocal.scalars(
            select(Payment).where(Payment.sale_id == sale_id)
        ).first()

        if existing_payment:
            if existing_payment.status == "Paid":
                return jsonify({"error": "This sale has already been paid"}), 400

            if existing_payment.status == "Pending":
                age = (datetime.utcnow() - existing_payment.created_at).total_seconds()
                if age <= PENDING_TIMEOUT_SECONDS:
                    remaining = int(PENDING_TIMEOUT_SECONDS - age)
                    return jsonify({
                        "error": f"Payment already in progress. Please wait {remaining} second(s) before retrying."
                    }), 400
                # Timed out — fall through to retry

        # ── Call Safaricom FIRST; only write to DB if this succeeds ──────────
        stk_response = make_stk_push({
            "phone_number": phone_paid,
            "amount":       trans_amount
        })
        print("STK response:", stk_response)

        mrid = stk_response.get("MerchantRequestID")
        crid = stk_response.get("CheckoutRequestID")

        if not mrid or not crid:
            return jsonify({
                "error": stk_response.get("errorMessage") or "STK push failed — Safaricom did not return a request ID"
            }), 400

        # ── Upsert: update existing row OR insert a fresh one ─────────────────
        if existing_payment:
            # Update in place — avoids any UniqueViolation
            existing_payment.mrid         = mrid
            existing_payment.crid         = crid
            existing_payment.phone_paid   = phone_paid
            existing_payment.trans_amount = float(trans_amount)
            existing_payment.trans_code   = None           # clear any stale code
            existing_payment.status       = "Pending"
            existing_payment.created_at   = datetime.utcnow()  # reset timeout clock
        else:
            new_payment = Payment(
                sale_id      = sale_id,
                mrid         = mrid,
                crid         = crid,
                phone_paid   = phone_paid,
                trans_amount = float(trans_amount),
                status       = "Pending",
                created_at   = datetime.utcnow()
            )
            SessionLocal.add(new_payment)

        SessionLocal.commit()

        return jsonify({
            "message":      "STK push sent",
            "response":     stk_response,
            "phone_number": phone_paid,
            "amount":       trans_amount
        }), 200

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/stk-call-back', methods=allowed_methods)
def call_back():
    try:
        data = request.get_json()
        print("stk callback data:-----------------", data)

        query = select(Payment).where(
            Payment.mrid == data['Body']['stkCallback']['MerchantRequestID'],
            Payment.crid == data['Body']['stkCallback']['CheckoutRequestID']
        )
        existing_payment = SessionLocal.scalars(query).first()

        # Guard: unknown mrid/crid — ignore safely instead of crashing
        if not existing_payment:
            print("Warning: callback received for unknown mrid/crid — ignoring")
            return jsonify({"message": "callback received"}), 200

        if int(data['Body']['stkCallback']['ResultCode']) == 0:
            trans_code = data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value']
            existing_payment.trans_code = trans_code
            existing_payment.status     = "Paid"

            text = (
                "Payment Receipt\n\n"
                f"Transaction Code: {trans_code}\n"
                f"Amount: KSH {existing_payment.trans_amount}\n"
                f"Date: {existing_payment.created_at}"
            )
            generate_pdf(text, trans_code)
            # send_sms(existing_payment.phone_paid, "Payment Received. Thank you!")
            print(data)

        else:
            # Customer cancelled, wrong PIN, timeout, etc.
            # Mark Unpaid so the cashier can retry immediately
            existing_payment.status     = "Unpaid"
            existing_payment.trans_code = None

        SessionLocal.commit()
        return jsonify({"message": "callback received"}), 200

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/mpesa-payments', methods=allowed_methods)
def mpesa_payments():
    try:
        method = request.method.lower()
        if method == 'get':
            query = select(Payment)
            payments = SessionLocal.scalars(query).all()

            result = []
            for p in payments:
                result.append({
                    "id":           p.id,
                    "sale_id":      p.sale_id,
                    "mrid":         p.mrid,
                    "crid":         p.crid,
                    "trans_code":   p.trans_code,
                    "trans_amount": p.trans_amount,
                    "phone_paid":   p.phone_paid,
                    "status":       p.status,
                    "created_at":   p.created_at
                })

            return jsonify(result), 200
        else:
            return jsonify({"error": "Method not allowed"}), 405

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/stock', methods=allowed_methods)
@jwt_required()
def stock():
    try:
        method = request.method.lower()

        if method == "get":
            products = SessionLocal.scalars(select(Product)).all()

            stock_list = []
            for p in products:
                stock_entry = SessionLocal.scalars(
                    select(Stock).where(Stock.product_id == p.id)
                ).first()

                stock_list.append({
                    "product_id":     p.id,
                    "product_name":   p.name,
                    "product_amount": p.amount,
                    "quantity":       stock_entry.quantity if stock_entry else 0,
                    "updated_at":     stock_entry.updated_at.isoformat() if stock_entry else None
                })

            return jsonify({"data": stock_list}), 200

        elif method == "post":
            data = request.get_json()

            if not data.get("product_id") or data.get("quantity") is None:
                return jsonify({"error": "product_id and quantity are required"}), 400

            if int(data["quantity"]) < 1:
                return jsonify({"error": "Quantity must be at least 1"}), 400

            product = SessionLocal.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if stock_entry:
                stock_entry.quantity += int(data["quantity"])
                stock_entry.updated_at = datetime.utcnow()
            else:
                stock_entry = Stock(
                    product_id=data["product_id"],
                    quantity=int(data["quantity"]),
                    updated_at=datetime.utcnow()
                )
                SessionLocal.add(stock_entry)

            SessionLocal.commit()
            return jsonify({"msg": "Stock updated", "quantity": stock_entry.quantity}), 200

        elif method == "put":
            data = request.get_json()

            if not data.get("product_id") or data.get("quantity") is None:
                return jsonify({"error": "product_id and quantity are required"}), 400

            if int(data["quantity"]) < 0:
                return jsonify({"error": "Quantity cannot be negative"}), 400

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if stock_entry:
                stock_entry.quantity = int(data["quantity"])
                stock_entry.updated_at = datetime.utcnow()
            else:
                stock_entry = Stock(
                    product_id=data["product_id"],
                    quantity=int(data["quantity"]),
                    updated_at=datetime.utcnow()
                )
                SessionLocal.add(stock_entry)

            SessionLocal.commit()
            return jsonify({"msg": "Stock updated", "quantity": stock_entry.quantity}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("product_id"):
                return jsonify({"error": "product_id is required"}), 400

            stock_entry = SessionLocal.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if stock_entry:
                stock_entry.quantity = 0
                stock_entry.updated_at = datetime.utcnow()
                SessionLocal.commit()

            return jsonify({"msg": "Stock reset to 0"}), 200

        else:
            return jsonify({"error": "Method not allowed"}), 405

    except Exception as e:
        SessionLocal.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/dashboard', methods=["GET"])
@jwt_required()
def dashboard():
    try:
        total_sales = SessionLocal.scalar(select(func.count(Sale.id)))

        total_revenue = SessionLocal.scalar(
            select(func.sum(Payment.trans_amount))
            .where(Payment.status == "Paid")
        ) or 0

        pending_count = SessionLocal.scalar(
            select(func.count(Payment.id))
            .where(Payment.status == "Pending")
        )

        low_stock_count = SessionLocal.scalar(
            select(func.count(Stock.id))
            .where(Stock.quantity <= 5)
        )

        sales_by_product = SessionLocal.execute(
            select(Product.name, func.count(Sale.id).label("cnt"))
            .join(Sale, Sale.product_id == Product.id)
            .group_by(Product.name)
            .order_by(func.count(Sale.id).desc())
        ).all()

        revenue_by_product = SessionLocal.execute(
            select(Product.name, func.sum(Payment.trans_amount).label("rev"))
            .join(Sale,    Sale.product_id == Product.id)
            .join(Payment, Payment.sale_id == Sale.id)
            .where(Payment.status == "Paid")
            .group_by(Product.name)
            .order_by(func.sum(Payment.trans_amount).desc())
        ).all()

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sales_per_day = SessionLocal.execute(
            select(
                func.date(Sale.created_at).label("day"),
                func.count(Sale.id).label("cnt")
            )
            .where(Sale.created_at >= thirty_days_ago)
            .group_by(func.date(Sale.created_at))
            .order_by(func.date(Sale.created_at))
        ).all()

        stock_levels = SessionLocal.execute(
            select(Product.name, Stock.quantity)
            .join(Stock, Stock.product_id == Product.id)
            .order_by(Stock.quantity.asc())
        ).all()

        return jsonify({
            "stats": {
                "total_sales":     total_sales,
                "total_revenue":   float(total_revenue),
                "pending_count":   pending_count,
                "low_stock_count": low_stock_count
            },
            "charts": {
                "sales_by_product": {
                    "labels": [r.name for r in sales_by_product],
                    "values": [r.cnt  for r in sales_by_product]
                },
                "revenue_by_product": {
                    "labels": [r.name       for r in revenue_by_product],
                    "values": [float(r.rev) for r in revenue_by_product]
                },
                "sales_per_day": {
                    "labels": [str(r.day) for r in sales_per_day],
                    "values": [r.cnt      for r in sales_per_day]
                },
                "stock_levels": {
                    "labels": [r.name     for r in stock_levels],
                    "values": [r.quantity for r in stock_levels]
                }
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.teardown_appcontext
def remove_session(exception=None):
    SessionLocal.remove()


if __name__ == "__main__":
    app.run(debug=True)