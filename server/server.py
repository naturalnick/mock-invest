from flask import Flask, request
from flask_cors import CORS
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv
from database import db
from models import Account, Holdings, Transactions
from helpers import generate_account_id, generate_token, decode_token
import iex

load_dotenv()

def create_app():
	app = Flask(__name__)
	app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DB_ACCESS")
	CORS(app)
	db.init_app(app)
	return app

app = create_app()

with app.app_context():
	from models import Account
	db.create_all()


@app.route("/")
def index():
	print(get_account_holdings(66245866))
	return "Hello"


@app.route("/login", methods=["POST"])
def login_user():
	email = request.json["email"]
	password = request.json["password"]

	if check_email_exists(email) is False:
		return {"error": "Account does not exist for that email."}, 404

	account = get_account(email)
	if password != account.password:
		return {"error": "Incorrect password."}, 401

	return {"token": generate_token(email)}, 200


@app.route("/register", methods=["POST"])
def register_user():
	email = request.json["email"]
	password = request.json["password"]

	if check_email_exists(email) is True:
		return {"error":"This email already has an account."}, 403

	create_account(email, password)
	return {"token": generate_token(email)}, 200


@app.route("/api/stock", methods=["GET"])
def get_stock():
	stock_symbol = request.args.get("symbol")
	data = iex.get_stock_data(stock_symbol)
	return data, 200


@app.route("/api/account/info", methods=["GET"])
def account_info():
	token = decode_token(request.args.get("token"))
	if token is None: return {"error": "invalid token"}, 401

	account = get_account(token["email"])
	return {"account_number": account.id, "balance": account.balance}, 200


@app.route("/api/account/holdings", methods=["GET"])
def account_holdings():
	token = request.args.get("token")
	email = decode_token(token)["email"]

	if decode_token(token) is None: return {"Error": "invalid token"}, 401

	account = get_account(email)
	holdings = get_account_holdings(account.id)

	return {"holdings": holdings}, 200


@app.route("/api/account/transactions", methods=["GET"])
def account_transactions():
	token = request.args.get("token")
	email = decode_token(token)["email"]

	if decode_token(token) is None: return {"Error": "invalid token"}, 401

	account = get_account(email)
	transactions = get_account_transactions(account.id)

	return {"transactions": transactions}, 200


@app.route("/api/trade", methods=["POST"])
def trade():
	transaction = request.json

	token = transaction.pop("token")
	email = decode_token(token)["email"]
	if email is None: return {"Error": "invalid token"}, 401

	account = get_account(email)
	transaction.update({"account_number": account.id})

	transaction_amount = float(transaction["quantity"]) * float(transaction["cost_per_share"])

	adjustBalance(account.id, account.balance, transaction_amount)
	modifyHoldings(**transaction)
	logTransaction(**transaction)
	return "Ok", 200


def adjustBalance(account_number, balance, amount):
	db.session.query(Account).filter(Account.id == account_number).update({"balance": balance - amount})
	db.session.commit()
	

def modifyHoldings(account_number, symbol, quantity, cost_per_share):
	holding = db.session.query(Holdings).filter(Holdings.account_number == account_number and Holdings.symbol == symbol).one()
	if holding is None:
		newHolding = Holdings(account_number=account_number, symbol=symbol, shares=quantity, base_cost=cost_per_share)
		db.session.add(newHolding)
	else:
		new_quantity = holding.shares + float(quantity)

		if int(quantity) > 0:
			new_price = (holding.base_cost + cost_per_share) / 2
		else:
			new_price = holding.base_cost

		db.session.query(Holdings).filter(Holdings.account_number == account_number and Holdings.symbol == symbol).update({"shares": new_quantity, "base_cost": new_price})

	db.session.commit()


def logTransaction(account_number, symbol, quantity, cost_per_share):
	date = datetime.now().astimezone(pytz.utc)
	newTransaction = Transactions(account_number=account_number, date=date, symbol=symbol, shares=quantity, price=cost_per_share)
	db.session.add(newTransaction)
	db.session.commit()


def create_account(email, password):
	while(True):
		account_id = generate_account_id()
		if check_account_number_exists(account_id) == False: break
	#encrypt password
	newAccount = Account(id=account_id, email=email, password=password, balance=1000)
	db.session.add(newAccount)
	db.session.commit()


def check_email_exists(email):
	account = db.session.query(Account).filter(Account.email == email).first()
	return False if account is None else True


def get_account(email):
	return db.session.query(Account).filter(Account.email == email).first()


def check_account_number_exists(id):
	return False if db.session.get(Account, id) is None else True


def get_account_holdings(account_number):
	entries = db.session.query(Holdings).filter(Holdings.account_number == account_number).all()
	holdings = []
	for entry in entries:
		holdings.append({"id": entry.id, "symbol": entry.symbol, "quantity": entry.shares, "base_cost":entry.base_cost})
	return holdings


def get_account_transactions(account_number):
	entries = db.session.query(Transactions).filter(Transactions.account_number == account_number).all()
	transactions = []
	for entry in entries:
		transactions.append({"id": entry.id, "date": entry.date, "symbol": entry.symbol, "quantity": entry.shares, "price":entry.price})
	return transactions


if __name__ == "__main__":
	app.run(debug=True,port=5001)