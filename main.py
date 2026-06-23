import psycopg2
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
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

CORS(app, supports_credentials=True, origins=["http://localhost:8004"])

jwt = JWTManager(app)
bcrypt = Bcrypt(app)

# DATABASE_URL = os.getenv("DATABASE_URL")
MY_DATABASE_URL=os.getenv("MY_DATABASE_URL")

# Connect SQLAlchemy to PostgreSQL using engine
## engine = create_engine(DATABASE_URL,connect_args={"check_same_thread":False},echo=False)
engine = create_engine(MY_DATABASE_URL,echo=False)

# Create session to call query methods
session = sessionmaker(bind=engine)
my_session = session()

# Create tables automatically
Base.metadata.create_all(engine)

allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]


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
            #reads json data sent in an http request
            data = request.get_json()

            # Check all fields are provided
            if data["full_name"] == "" or data["email"] == "" or data["password"] == "":
                return jsonify({"msg": "Full name, email and password cannot be empty"}), 400

            # Check if user already exists
            existing_user = my_session.query(
                User).filter_by(email=data["email"]).first()
            if existing_user:
                return jsonify({"msg": "Email already registered"}), 409

            # Hash password
            hashed_password = bcrypt.generate_password_hash(
                data["password"]).decode("utf-8")

            # Create new user
            new_user = User(
                full_name=data["full_name"],
                email=data["email"],
                password=hashed_password,
                created_at=datetime.utcnow()
            )
            #stages a new object to be saved;not saved immediately
            my_session.add(new_user)
            #permanently saves all changes
            my_session.commit()

            # Generate token
            token = create_access_token(identity=data["email"])

            return jsonify({"msg": "User registered successfully", "token": token}), 201

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        #undoes all committed changes
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/login', methods=allowed_methods)
def login():
    try:
        method = request.method.lower()

        if method == "post":
            #reads json data sent in an http request
            data = request.get_json()

            email = data.get("email")
            password = data.get("password")

            # Validate input
            if not email or not password:
                return jsonify({"msg": "Email and password required"}), 400

            # Check if user exists
            query = select(User).where(User.email == email)
            user = my_session.scalars(query).first()

            if not user:
                return jsonify({"msg": "Invalid email"}), 401

            # Verify password
            if not bcrypt.check_password_hash(user.password, password):
                return jsonify({"msg": "Invalid password"}), 401

            # Generate token
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

        # Get the logged-in user
        user = my_session.scalars(
            select(User).where(User.email == email)).first()

        if method == "get":
            product_list = []
            query = select(Product)
            all_products = list(my_session.scalars(query).all())

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
            my_session.add(new_product)
            my_session.commit()

            return jsonify({"msg": "Product added successfully"}), 201

        elif method == "put":
            data = request.get_json()

            if not data.get("id"):
                return jsonify({"error": "id is required"}), 400

            if not data.get("name") or data.get("amount") is None:
                return jsonify({"error": "name and amount are required"}), 400

            product = my_session.scalars(
                select(Product).where(Product.id == data["id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            product.name = data["name"]
            product.amount = float(data["amount"])
            my_session.commit()
            return jsonify({"msg": "Product updated"}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("id"):
                return jsonify({"error": "id is required"}), 400

            product = my_session.scalars(
                select(Product).where(Product.id == data["id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            # Delete related sales and their payments first
            related_sales = my_session.scalars(
                select(Sale).where(Sale.product_id == data["id"])
            ).all()

            for sale in related_sales:
                if sale.payment:
                    my_session.delete(sale.payment)
                my_session.delete(sale)

            # Delete related stock
            stock_entry = my_session.scalars(
                select(Stock).where(Stock.product_id == data["id"])
            ).first()
            if stock_entry:
                my_session.delete(stock_entry)

            my_session.delete(product)
            my_session.commit()
            return jsonify({"msg": "Product deleted"}), 200

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/sales', methods=allowed_methods)
@jwt_required()
def sales():
    try:
        method = request.method.lower()

        if method == "get":
            sales_list = []
            query = select(Sale)
            all_sales = list(my_session.scalars(query).all())

            for sale in all_sales:
                sales_list.append({
                    "id":         sale.id,
                    "product_id": sale.product_id,
                    "created_at": sale.created_at.isoformat(),
                    # Use ORM relationships directly
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
                        "status": sale.payment.status
                    } if sale.payment else None
                })

            return jsonify({"data": sales_list}), 200

        elif method == "post":
            data = request.get_json()

            if not data.get("product_id"):
                return jsonify({"msg": "product_id is required"}), 400

            # Confirm product exists
            product = my_session.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not product:
                return jsonify({"msg": "Product not found"}), 404

            # Check stock availability
            stock_entry = my_session.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if not stock_entry or stock_entry.quantity < 1:
                return jsonify({"error": f"'{product.name}' is out of stock"}), 400

            new_sale = Sale(
                product_id=data["product_id"],
                created_at=datetime.utcnow()
            )
            my_session.add(new_sale)
            my_session.flush()

            # Deduct stock
            stock_entry.quantity -= 1
            stock_entry.updated_at = datetime.utcnow()

            my_session.commit()
            return jsonify({"msg": "Sale created successfully", "sale_id": new_sale.id}), 201

        elif method == "put":
            data = request.get_json()

            if not data.get("sale_id"):
                return jsonify({"error": "sale_id is required"}), 400

            sale = my_session.scalars(
                select(Sale).where(Sale.id == data["sale_id"])
            ).first()

            if not sale:
                return jsonify({"error": "Sale not found"}), 404

            if not data.get("product_id"):
                return jsonify({"error": "product_id is required"}), 400

            new_product = my_session.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not new_product:
                return jsonify({"error": "Product not found"}), 404

            new_stock = my_session.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if not new_stock or new_stock.quantity < 1:
                return jsonify({"error": f"'{new_product.name}' is out of stock"}), 400

            # Restore stock for old product
            old_stock = my_session.scalars(
                select(Stock).where(Stock.product_id == sale.product_id)
            ).first()

            if old_stock:
                old_stock.quantity += 1
                old_stock.updated_at = datetime.utcnow()

            # Deduct stock for new product
            new_stock.quantity -= 1
            new_stock.updated_at = datetime.utcnow()

            sale.product_id = data["product_id"]
            my_session.commit()
            return jsonify({"msg": "Sale updated successfully"}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("sale_id"):
                return jsonify({"error": "sale_id is required"}), 400

            sale = my_session.scalars(
                select(Sale).where(Sale.id == data["sale_id"])
            ).first()

            if not sale:
                return jsonify({"error": "Sale not found"}), 404

            # Restore stock
            stock_entry = my_session.scalars(
                select(Stock).where(Stock.product_id == sale.product_id)
            ).first()

            if stock_entry:
                stock_entry.quantity += 1
                stock_entry.updated_at = datetime.utcnow()

            # Delete linked payment
            if sale.payment:
                my_session.delete(sale.payment)

            my_session.delete(sale)
            my_session.commit()
            return jsonify({"msg": "Sale deleted successfully"}), 200

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/stk-push', methods=allowed_methods)
def stk_push():
    try:
        data = request.get_json()

        # create a payment with only id,saleid,mrid,crid,created at
        sale_id = data.get('sale_id')
        trans_amount = data.get('amount')
        phone_paid = data.get('phone_number')

        if sale_id == None or trans_amount == None or phone_paid == None:
            return jsonify({"error": "sale_id, phone_number and amount are required"}), 400

        stk_response = make_stk_push({
            "phone_number": phone_paid,
            "amount": trans_amount
        })
        print(stk_response)

        new_payment = Payment(
            sale_id=sale_id,
            mrid=stk_response.get("MerchantRequestID"),
            crid=stk_response.get("CheckoutRequestID"),
            phone_paid=phone_paid,
            trans_amount=float(trans_amount),
            status="Pending"
        )

        my_session.add(new_payment)
        my_session.commit()

        return jsonify({
            "message": "STK push sent",
            "response": stk_response,
            "phone_number": phone_paid,
            "amount": trans_amount
        }), 200

    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/stk-call-back', methods=allowed_methods)
def call_back():
    try:
        data = request.get_json()
        print("stk callback data:-----------------", data)

        # fetch the payment record using mrid and crid
        query = select(Payment).where(
            Payment.mrid == data['Body']['stkCallback']['MerchantRequestID'], Payment.crid == data['Body']['stkCallback']['CheckoutRequestID'])
        existing_payment = my_session.scalars(query).first()

        if int(data['Body']['stkCallback']['ResultCode']) == 0:
            # update payment record with transaction code,transaction amount and status
            existing_payment.trans_code = data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value']
            existing_payment.status = "Paid"
            # now generate receipt pdf
            text = "Payment Receipt\n\nTransaction Code: " + data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value'] + "\n" + "Amount: KSH " + str(
                existing_payment.trans_amount) + "\n" + "Date: " + str(existing_payment.created_at)
            generate_pdf(text, data['Body']['stkCallback']
                         ['CallbackMetadata']['Item'][1]['Value'])
            # generate sms
            message = "Payment Received.Thank You we have received your payment.Welcome again"
            # send_sms(existing_payment.phone_paid, message)
            print(data)

        else:
            existing_payment.status = "Unpaid"

        my_session.commit()

        return jsonify({"message": "callback received"}), 200
    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/mpesa-payments', methods=allowed_methods)
def mpesa_payments():
    try:
        method = request.method.lower()
        if method == 'get':
            query = select(Payment)
            payments = my_session.scalars(query).all()

            result = []

            for p in payments:
                result.append({
                    "id": p.id,
                    "sale_id": p.sale_id,
                    "mrid": p.mrid,
                    "crid": p.crid,
                    "trans_code": p.trans_code,
                    "trans_amount": p.trans_amount,
                    "phone_paid": p.phone_paid,
                    "status": p.status,
                    "created_at": p.created_at
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
            # Return all products with their stock quantity
            products = my_session.scalars(select(Product)).all()

            stock_list = []
            for p in products:
                stock_entry = my_session.scalars(
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

            # Check product exists
            product = my_session.scalars(
                select(Product).where(Product.id == data["product_id"])
            ).first()

            if not product:
                return jsonify({"error": "Product not found"}), 404

            # Update existing stock or create new
            stock_entry = my_session.scalars(
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
                my_session.add(stock_entry)

            my_session.commit()
            return jsonify({"msg": "Stock updated", "quantity": stock_entry.quantity}), 200

        elif method == "put":
            data = request.get_json()

            if not data.get("product_id") or data.get("quantity") is None:
                return jsonify({"error": "product_id and quantity are required"}), 400

            if int(data["quantity"]) < 0:
                return jsonify({"error": "Quantity cannot be negative"}), 400

            stock_entry = my_session.scalars(
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
                my_session.add(stock_entry)

            my_session.commit()
            return jsonify({"msg": "Stock updated", "quantity": stock_entry.quantity}), 200

        elif method == "delete":
            data = request.get_json()

            if not data.get("product_id"):
                return jsonify({"error": "product_id is required"}), 400

            stock_entry = my_session.scalars(
                select(Stock).where(Stock.product_id == data["product_id"])
            ).first()

            if stock_entry:
                stock_entry.quantity = 0
                stock_entry.updated_at = datetime.utcnow()
                my_session.commit()

            return jsonify({"msg": "Stock reset to 0"}), 200

        else:
            return jsonify({"error": "Method not allowed"}), 405

    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/dashboard', methods=["GET"])
@jwt_required()
def dashboard():
    try:
        # ── Summary stats ──
        total_sales = my_session.scalar(select(func.count(Sale.id)))

        total_revenue = my_session.scalar(
            select(func.sum(Payment.trans_amount))
            .where(Payment.status == "Paid")
        ) or 0

        pending_count = my_session.scalar(
            select(func.count(Payment.id))
            .where(Payment.status == "Pending")
        )

        low_stock_count = my_session.scalar(
            select(func.count(Stock.id))
            .where(Stock.quantity <= 5)
        )

        # ── Sales by product ──
        sales_by_product = my_session.execute(
            select(Product.name, func.count(Sale.id).label("cnt"))
            .join(Sale, Sale.product_id == Product.id)
            .group_by(Product.name)
            .order_by(func.count(Sale.id).desc())
        ).all()

        # ── Revenue by product ──
        revenue_by_product = my_session.execute(
            select(Product.name, func.sum(Payment.trans_amount).label("rev"))
            .join(Sale,    Sale.product_id == Product.id)
            .join(Payment, Payment.sale_id == Sale.id)
            .where(Payment.status == "Paid")
            .group_by(Product.name)
            .order_by(func.sum(Payment.trans_amount).desc())
        ).all()

        # ── Sales per day (last 30 days) ──
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sales_per_day = my_session.execute(
            select(
                func.date(Sale.created_at).label("day"),
                func.count(Sale.id).label("cnt")
            )
            .where(Sale.created_at >= thirty_days_ago)
            .group_by(func.date(Sale.created_at))
            .order_by(func.date(Sale.created_at))
        ).all()

        # ── Stock levels ──
        stock_levels = my_session.execute(
            select(Product.name, Stock.quantity)
            .join(Stock, Stock.product_id == Product.id)
            .order_by(Stock.quantity.asc())
        ).all()

        return jsonify({
            "stats": {
                "total_sales":    total_sales,
                "total_revenue":  float(total_revenue),
                "pending_count":  pending_count,
                "low_stock_count": low_stock_count
            },
            "charts": {
                "sales_by_product": {
                    "labels": [r.name for r in sales_by_product],
                    "values": [r.cnt for r in sales_by_product]
                },
                "revenue_by_product": {
                    "labels": [r.name for r in revenue_by_product],
                    "values": [float(r.rev) for r in revenue_by_product]
                },
                "sales_per_day": {
                    "labels": [str(r.day) for r in sales_per_day],
                    "values": [r.cnt for r in sales_per_day]
                },
                "stock_levels": {
                    "labels": [r.name for r in stock_levels],
                    "values": [r.quantity for r in stock_levels]
                }
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)