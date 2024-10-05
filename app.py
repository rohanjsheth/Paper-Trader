import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """returns currently held shares"""
    user_id = session.get("user_id")
    purchase_history = db.execute("SELECT ticker, SUM(shares), AVG(IIF(share_price >= 0, share_price, NULL)) FROM purchases WHERE user_id = ? GROUP BY ticker", user_id)
    print(purchase_history)
    invested_assets = 0

    for rows in purchase_history:
        rows["AVG(IIF(share_price >= 0, share_price, NULL))"] = lookup(rows['ticker'])['price']
        rows["net_effect"] = float('{0:.2f}'.format(rows["SUM(shares)"] * rows["AVG(IIF(share_price >= 0, share_price, NULL))"]))
        invested_assets+=rows["net_effect"]


    purchase_history = [item for item in purchase_history if item["SUM(shares)"] >= 1]
    account_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']
    total_held = account_balance+invested_assets

    return render_template("index.html", purchase_history=purchase_history, account_balance=account_balance, invested_assets=invested_assets, total_held=total_held)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Purchase stocks"""
    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":
        ticker = request.form.get("ticker")

        try:
            price = lookup(ticker)["price"]
        except:
            return apology(f"Could not find Ticker for: {ticker}")

        try:
            share_num = int(request.form.get("shares"))
        except:
            return apology("Must enter a number of shares")

        if share_num < 1:
            return apology("Invalid number of shares")

        purchase = price * share_num
        print(purchase)
        user_id = session.get("user_id")

        account_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']
        print(account_balance)

        if purchase > account_balance:
            return apology("sorry, this account has insufficent funds to make this purchase")

        #unnegatived "price"
        db.execute("INSERT into purchases (ticker, shares, share_price, user_id) VALUES (?, ?, ?, ?)", ticker, share_num, price, user_id)
        db.execute("UPDATE users SET cash = ?", (account_balance - purchase))

        flash(f"You have succesfully made a purchase of {share_num} shares of {ticker} for ${purchase}", "purchase_messages")
        return redirect("/")



@app.route("/history")
@login_required
def history():
    user_id = session.get("user_id")
    purchase_history = db.execute("SELECT ticker, shares, share_price from purchases WHERE user_id = ?", user_id)
    print(purchase_history)

    for rows in purchase_history:
        rows["net_effect"] = -float('{0:.2f}'.format(rows["share_price"] * rows["shares"]))
        rows["share_price"] = abs(rows["share_price"])


    print(purchase_history)

    return render_template("history.html", purchase_history=purchase_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    if request.method == "POST":
        query = request.form.get("ticker")
        if not query:
            return apology("Please enter a ticker symbol to search")

        query_results = lookup(query)
        if not query_results:
            return apology("Sorry, could not find ticker")

        name = query_results["name"]
        price = query_results["price"]
        ticker = query_results["symbol"]

        return render_template("quoteresults.html", name=name, price=price, ticker=ticker)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")


    if request.method == "POST":
        username = request.form.get("username")
        password1 = request.form.get("password1")
        password2 = request.form.get("password2")


        if not username:
            return apology("must provide username")
        if len(db.execute(f"SELECT username FROM users WHERE username = ?", username)) != 0:
            return apology("Sorry, username is taken")
        if not password1:
            return apology("must provide password")
        if not password1 == password2:
            return apology("passwords must match")
        if len(password1) < 8:
            return apology("password must have at least 8 characters")

        special = re.compile("[~!@#$%^&*()-=]")
        numbers = re.compile("/d")
        if not any([special.search(password1), numbers.search(password1)]):
            return apology("password must at least have one special character and one number")

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, generate_password_hash(password1))

        return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        return render_template("sell.html")

    if request.method == "POST":

        ticker = request.form.get("ticker")
        user_id = session.get("user_id")
        account_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]['cash']

        try:
            price = lookup(ticker)["price"]
        except:
            return apology(f"Could not find Ticker for: {ticker}")

        try:
            share_num = int(request.form.get("shares"))
        except:
            return apology("Must enter a number of shares")

        if share_num < 1:
            return apology("Invalid number of shares")

        shares_held = db.execute("SELECT SUM(shares) from purchases where user_id = ? AND ticker = ?", user_id, ticker)
        shares_held = shares_held[0]['SUM(shares)']
        print(shares_held)

        if shares_held == None or shares_held == 0:
            return apology(f"You do not have any shares of {ticker}")

        if shares_held < share_num:
            return apology(f"You cannot sell more shares than you have")

        db.execute("UPDATE users SET cash = ?", account_balance + (share_num * price))
        db.execute("INSERT into purchases (ticker, shares, share_price, user_id) VALUES (?, ?, ?, ?)", ticker, -share_num, price, user_id)

        flash(f"You have succesfully made a sale of {share_num} shares of {ticker} for ${share_num * price}", "purchase_messages")
        return redirect("/")


