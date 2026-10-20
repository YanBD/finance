import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


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
    """Show portfolio of stocks"""

    if request.method == "GET":
        # get user id from session
        user_id = session.get("user_id")

        # get user's cash balance
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

        # get user's stock holdings
        stocks = db.execute(
            "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
            user_id,
        )

        # calculate total value of each stock and overall portfolio value
        total_portfolio_value = cash
        for stock in stocks:
            quote = lookup(stock["symbol"])
            if quote:
                stock["name"] = quote["name"]
                stock["price"] = quote["price"]
                stock["total_value"] = stock["total_shares"] * quote["price"]
                total_portfolio_value += stock["total_value"]
            else:
                stock["name"] = "N/A"
                stock["price"] = 0
                stock["total_value"] = 0

        return render_template(
            "index.html",
            cash=usd(cash),
            stocks=stocks,
            total_portfolio_value=usd(total_portfolio_value),
        )
    else:
        return apology("Invalid request method", 405)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol", 400)

        if not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive integer for shares", 400)

        stock = lookup(symbol)
        if not stock:
            return apology("invalid symbol", 400)

        user_id = session.get("user_id")
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        total_cost = stock["price"] * int(shares)

        if total_cost > cash:
            return apology("insufficient funds", 400)

        # Update user's cash balance
        db.execute(
            "UPDATE users SET cash = cash - ? WHERE id = ?", total_cost, user_id
        )

        # Record the transaction
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
            user_id,
            stock["symbol"],
            int(shares),
            stock["price"],
        )

        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")



@app.route("/history", methods=["GET"])
@login_required
def history():
    """Show history of transactions"""

    if request.method == "GET":
        user_id = session.get("user_id")
        transactions = db.execute(
            "SELECT symbol, shares, price, transacted_at FROM transactions WHERE user_id = ? ORDER BY transacted_at ASC",
            user_id,
        )
        for transaction in transactions:
            if transaction["shares"] > 0:
                transaction["type"] = "BUY"
            else:
                transaction["type"] = "SELL"
                transaction["shares"] = -transaction["shares"]  # Make shares positive for display
        return render_template("history.html", transactions=transactions)
    else:
        return apology("Invalid request method", 405)



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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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

    # check that user is logged in

    if not session.get("user_id"):
        return redirect("/login")

    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("must provide symbol", 400)

        stock = lookup(symbol)

        if not stock:
            return apology("invalid symbol", 400)

        return render_template(
            "quoted.html",
            name=stock["name"],
            price=usd(stock["price"]),
            symbol=stock["symbol"],
        )
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # clear any user_id
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        if not request.form.get("password"):
            return apology("must provide password", 400)

        if not request.form.get("confirmation"):
            return apology("must provide password confirmation", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        if len(
            db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        ) > 0:
            return apology("username already exists", 400)

        if len(request.form.get("password")) < 8:
            return apology("password must be at least 8 characters long", 400)

        # insert new user into database
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)",
            request.form.get("username"),
            generate_password_hash(request.form.get("password")),
        )

        # redirect user to login page
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol", 400)

        if not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive integer for shares", 400)

        user_id = session.get("user_id")
        stock = lookup(symbol)
        if not stock:
            return apology("invalid symbol", 400)

        # Check if user owns enough shares to sell
        owned_shares = db.execute(
            "SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol",
            user_id,
            stock["symbol"],
        )
        total_owned_shares = owned_shares[0]["total_shares"] if owned_shares else 0

        if int(shares) > total_owned_shares:
            return apology("insufficient shares to sell", 400)

        # Update user's cash balance
        total_sale_value = stock["price"] * int(shares)
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?", total_sale_value, user_id
        )

        # Record the transaction (negative shares for selling)
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
            user_id,
            stock["symbol"],
            -int(shares),
            stock["price"],
        )

        flash("Sold!")
        return redirect("/")
    else:
        user_id = session.get("user_id")
        stocks = db.execute(
            "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
            user_id,
        )
        return render_template("sell.html", stocks=stocks)

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change user's password"""

    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        if not current_password:
            return apology("must provide current password", 403)

        if not new_password:
            return apology("must provide new password", 403)

        if not confirmation:
            return apology("must provide password confirmation", 403)

        if new_password != confirmation:
            return apology("new passwords do not match", 403)

        if len(new_password) < 8:
            return apology("new password must be at least 8 characters long", 403)

        user_id = session.get("user_id")
        user = db.execute("SELECT * FROM users WHERE id = ?", user_id)[0]

        if not check_password_hash(user["hash"], current_password):
            return apology("current password is incorrect", 403)

        # Update user's password
        db.execute(
            "UPDATE users SET hash = ? WHERE id = ?",
            generate_password_hash(new_password),
            user_id,
        )

        flash("Password changed successfully!")
        return redirect("/")

    else:
        return render_template("change_password.html")

