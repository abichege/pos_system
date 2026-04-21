from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from database import Base, User, Product, Sale, Payment
from datetime import datetime
from mpesa import make_stk_push


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = "abcdef123"

CORS(app, supports_credentials=True)

jwt = JWTManager(app)
bcrypt = Bcrypt(app)

DATABASE_URL = "postgresql+psycopg2://postgres:blossomabigael@localhost:5432/pos_db"

# Connect SQLAlchemy to PostgreSQL using engine
engine = create_engine(DATABASE_URL, echo=False)

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
            my_session.add(new_user)
            my_session.commit()

            # Generate token
            token = create_access_token(identity=data["email"])

            return jsonify({"msg": "User registered successfully", "token": token}), 201

        else:
            return jsonify({"msg": "Method not allowed"}), 405

    except Exception as e:
        my_session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/login', methods=allowed_methods)
def login():
    try:
        method = request.method.lower()

        if method == "post":
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
                        "phone_paid":   sale.payment.phone_paid
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

            new_sale = Sale(
                product_id=data["product_id"],
                created_at=datetime.utcnow()
            )
            my_session.add(new_sale)
            my_session.commit()

            return jsonify({"msg": "Sale created successfully"}), 201

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
        return jsonify({"error": str(e)}), 500


@app.route('/stk-call-back', methods=allowed_methods)
def call_back():
    data = request.get_json()
    print("stk callback data:-----------------", data)

    # fetch the payment record using mrid and crid
    query = select(Payment).where(Payment.mrid == data['Body']['stkCallback']['MerchantRequestID'], Payment.crid == data['Body']['stkCallback']['CheckoutRequestID'])
    existing_payment = my_session.scalars(query).first()

    if  int(data['Body']['stkCallback']['ResultCode'])==0:
        # update payment record with transaction code,transaction amount and status
        existing_payment.trans_code = data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value']
        existing_payment.status="Success"
        
    else:
        existing_payment.status="Failed"
        my_session.commit()

    return jsonify({"message": "callback received"}), 200


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


app.run(debug=True)
