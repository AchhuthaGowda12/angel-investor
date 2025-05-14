from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from bson.objectid import ObjectId
import os
import datetime
import stripe
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import os
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey')

# MongoDB Configuration
app.config["MONGO_URI"] = "mongodb+srv://agowdan12:0SqTqhQ5dH7Mm3JM@cluster0.vtlr69c.mongodb.net/Donations?retryWrites=true&w=majority&appName=Cluster0"
mongo = PyMongo(app)

# Email configuration
smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
smtp_port = int(os.environ.get('SMTP_PORT', '587'))
smtp_username = os.environ.get('SMTP_USERNAME')
smtp_password = os.environ.get('SMTP_PASSWORD')

# URL safe serializer for generating tokens
serializer = URLSafeTimedSerializer(app.secret_key)


if mongo.db is None:
    print("MongoDB connection not established!")
else:
    print("MongoDB connection established!")


# Email sending functions
def send_email(to_email, subject, body):
    """Generic function to send emails"""
    if not all([smtp_username, smtp_password]):
        print("Error: SMTP credentials not properly configured")
        return False

    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False


def send_verification_email(email, name):
    """Send email verification token to user"""
    # Generate token
    token = serializer.dumps(email, salt='email-verification')
    
    # Build verification URL
    verify_url = url_for('verify_email', token=token, _external=True)
    
    # Email content
    subject = "Please Verify Your Email"
    body = f"""
    <html>
    <body>
        <h2>Welcome to our platform, {name}!</h2>
        <p>Thank you for registering. Please click the link below to verify your email address:</p>
        <p><a href="{verify_url}">Verify Email</a></p>
        <p>This link will expire in 24 hours.</p>
        <p>If you did not create an account, please ignore this email.</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, body)


def send_welcome_email(email, name):
    """Send welcome email after successful verification"""
    subject = "Welcome to Our Platform!"
    body = f"""
    <html>
    <body>
        <h2>Welcome aboard, {name}!</h2>
        <p>Your email has been successfully verified.</p>
        <p>You can now log in and start using our platform to connect with startups or investors.</p>
        <p>If you have any questions, feel free to contact our support team.</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, body)


def send_password_reset_email(email):
    """Send password reset token to user"""
    # Generate OTP
    otp = ''.join(random.choices(string.digits, k=6))
    
    # Store OTP in database with expiry
    expires_at = datetime.utcnow() + timedelta(minutes=30)
    mongo.db.password_reset_tokens.insert_one({
        "email": email,
        "otp": otp,
        "expires_at": expires_at,
        "used": False
    })
    
    # Email content
    subject = "Password Reset Request"
    body = f"""
    <html>
    <body>
        <h2>Password Reset</h2>
        <p>You requested a password reset. Here is your one-time passcode:</p>
        <h3>{otp}</h3>
        <p>This code will expire in 30 minutes.</p>
        <p>If you did not request this, please ignore this email.</p>
    </body>
    </html>
    """
    
    return send_email(email, subject, body)


@app.route("/")
def homepage():
    name = session.get("name", None)
    return render_template("homepage.html", name=name)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmPassword")
        age = request.form.get("age")
        role = request.form.get("role")
        
        if not all([name, email, phone, password, confirm_password, age, role]):
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if mongo.db.users.find_one({"email": email}):
            flash("Email already registered. Please login.", "error")
            return redirect(url_for("login"))
        
        hashed_password = generate_password_hash(password)
        
        # Insert user with verified status set to False
        user_id = mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "password": hashed_password,
            "phone": phone,
            "age": int(age),
            "role": role,
            "verified": False,
            "created_at": datetime.utcnow()
        }).inserted_id
        
        # Send verification email
        if send_verification_email(email, name):
            flash("Registration successful! Please check your email to verify your account.", "success")
        else:
            flash("Registration successful but we couldn't send verification email. Please contact support.", "warning")
        
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/verify-email/<token>")
def verify_email(token):
    try:
        # Verify token with 24-hour expiry
        email = serializer.loads(token, salt='email-verification', max_age=86400)
        
        # Update user verification status
        result = mongo.db.users.update_one(
            {"email": email, "verified": False},
            {"$set": {"verified": True}}
        )
        
        if result.modified_count > 0:
            # Get user info for welcome email
            user = mongo.db.users.find_one({"email": email})
            if user:
                send_welcome_email(email, user["name"])
            
            flash("Email verification successful! You can now log in.", "success")
        else:
            flash("Email already verified or not found.", "info")
        
        return redirect(url_for("login"))
        
    except SignatureExpired:
        flash("The verification link has expired. Please request a new one.", "error")
        return redirect(url_for("resend_verification"))
    except:
        flash("Invalid verification link.", "error")
        return redirect(url_for("register"))


@app.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email")
        
        user = mongo.db.users.find_one({"email": email})
        if not user:
            flash("Email not found.", "error")
            return redirect(url_for("resend_verification"))
            
        if user.get("verified", False):
            flash("This email is already verified.", "info")
            return redirect(url_for("login"))
            
        if send_verification_email(email, user["name"]):
            flash("Verification email sent! Please check your inbox.", "success")
            return redirect(url_for("login"))
        else:
            flash("Failed to send verification email. Please try again later.", "error")
            
    return render_template("resend_verification.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        
        user = mongo.db.users.find_one({"email": email})
        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))
        
        if not user.get("verified", False):
            flash("Please verify your email before logging in.", "error")
            return redirect(url_for("login"))

        session["user_id"] = str(user["_id"])
        session["role"] = user["role"]
        session["name"] = user["name"]

        # Redirect based on user role
        if role == "admin":
            return redirect(url_for("admin_panel"))
        elif role == "investor":
            return redirect(url_for("investor_dashboard"))
        elif role == "entrepreneur":
            return redirect(url_for("startup_dashboard"))
        else:
            return redirect(url_for("homepage"))
            
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        
        user = mongo.db.users.find_one({"email": email})
        if not user:
            # Security: still show success message even if email not found
            flash("If your email exists in our system, you will receive a password reset link.", "info")
            return redirect(url_for("login"))
        
        if send_password_reset_email(email):
            flash("Password reset instructions sent to your email.", "success")
            return redirect(url_for("reset_password"))
        else:
            flash("Failed to send reset email. Please try again later.", "error")
    
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email")
        otp = request.form.get("otp")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if new_password != confirm_password:
            flash("Passwords don't match.", "error")
            return redirect(url_for("reset_password"))
            
        # Verify OTP
        token = mongo.db.password_reset_tokens.find_one({
            "email": email,
            "otp": otp,
            "expires_at": {"$gt": datetime.utcnow()},
            "used": False
        })
        
        if not token:
            flash("Invalid or expired OTP.", "error")
            return redirect(url_for("reset_password"))
            
        # Update password
        hashed_password = generate_password_hash(new_password)
        mongo.db.users.update_one(
            {"email": email},
            {"$set": {"password": hashed_password}}
        )
        
        # Mark token as used
        mongo.db.password_reset_tokens.update_one(
            {"_id": token["_id"]},
            {"$set": {"used": True}}
        )
        
        flash("Password reset successful! You can now log in with your new password.", "success")
        return redirect(url_for("login"))
        
    return render_template("reset_password.html")


# Dashboard route for Startups
@app.route("/startup-dashboard")
def startup_dashboard():
    if "role" in session and session["role"] == "entrepreneur":
        user_id = session["user_id"]
        
        # Aggregation pipeline to get projects with investor details
        pipeline = [
            {
                "$match": {"startup_id": ObjectId(user_id)}
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "investments.investor_id",
                    "foreignField": "_id",
                    "as": "investor_details"
                }
            }
        ]
        
        try:
            projects = list(mongo.db.projects.aggregate(pipeline))
            
            # Process each project to add investor names
            for project in projects:
                # Create a map of investor IDs to names
                investor_map = {str(investor['_id']): investor['name'] 
                              for investor in project.get('investor_details', [])}
                
                # Add investor names to investments
                if 'investments' in project:
                    for investment in project['investments']:
                        investor_id = str(investment['investor_id'])
                        investment['investor_name'] = investor_map.get(investor_id, 'Unknown Investor')
                        # Format amount to 2 decimal places
                        investment['amount'] = float(investment['amount'])
            
            return render_template("startup_dashboard.html", name=session["name"], projects=projects)
            
        except Exception as e:
            print(f"Error fetching projects: {e}")
            return render_template("startup_dashboard.html", name=session["name"], projects=[])
            
    return redirect("/login")


# Route to create a project (Startup)
@app.route("/create-project", methods=["GET", "POST"])
def create_project():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        funding_goal = float(request.form.get("funding_goal"))
        deadline = request.form.get("deadline")
        total_equity = float(request.form.get("total_equity", 0))  # New field
        user_id = session["user_id"]

        # Insert project into database
        project = {
            "title": title,
            "description": description,
            "funding_goal": funding_goal,
            "current_funding": 0,
            "deadline": deadline,
            "startup_id": ObjectId(user_id),
            "total_equity": total_equity,            # Total equity being offered
            "remaining_equity": total_equity,        # Initially same as total equity
            "status": "active",                     # Project status
            "investments": []                       # List to track investments
        }
        mongo.db.projects.insert_one(project)
        return redirect("/startup-dashboard")
    return render_template("create_project.html")


@app.route("/investor-dashboard")
def investor_dashboard():
    if "role" in session and session["role"] == "investor":
        user_id = session["user_id"]
        
        # Fetch projects the user has invested in
        user_investments = []
        investments = mongo.db.projects.find({"investments.investor_id": ObjectId(user_id)})
        
        total_invested = 0
        for project in investments:
            for investment in project["investments"]:
                if str(investment["investor_id"]) == user_id:
                    # Add investment date and transaction ID
                    user_investments.append({
                        "project_title": project["title"],
                        "project_description": project["description"],
                        "amount": investment["amount"],
                        "equity_percentage": investment["equity_percentage"],
                        "status": project["status"],
                        "deadline": project["deadline"],
                        "investment_date": investment.get("date"),
                        "transaction_id": investment.get("transaction_id"),
                        "project_id": str(project["_id"])  # Add project ID for tracking
                    })
                    total_invested += investment["amount"]
        
        # Fetch only approved and not fully funded projects
        projects = list(mongo.db.projects.find({
            "status": "Approved",
            "$expr": {
                "$lt": ["$current_funding", "$funding_goal"]
            }
        }).sort("deadline", 1))  # Sort by deadline ascending
        
        for project in projects:
            try:
                # Calculate current funding if not already set
                if "current_funding" not in project:
                    current_funding = sum(inv["amount"] for inv in project.get("investments", []))
                    # Update the project document with current funding
                    mongo.db.projects.update_one(
                        {"_id": project["_id"]},
                        {"$set": {"current_funding": current_funding}}
                    )
                    project["current_funding"] = current_funding
                
                # Calculate remaining funding
                project["remaining_funding"] = project["funding_goal"] - project["current_funding"]
                
                # Calculate remaining equity
                total_equity_taken = sum(inv["equity_percentage"] for inv in project.get("investments", []))
                project["remaining_equity"] = project.get("total_equity", 0) - total_equity_taken
                
                # Calculate funding progress percentage
                project["funding_progress"] = (project["current_funding"] / project["funding_goal"]) * 100
                
                # Add time remaining calculation
                if isinstance(project["deadline"], str):
                    deadline = datetime.strptime(project["deadline"], "%Y-%m-%d")
                else:
                    deadline = project["deadline"]
                project["days_remaining"] = (deadline - datetime.now()).days
                
                # Remove projects that are fully funded or have no remaining equity
                if project["remaining_funding"] <= 0 or project["remaining_equity"] <= 0:
                    projects.remove(project)
                    
            except Exception as e:
                app.logger.error(f"Error processing project {project.get('_id')}: {str(e)}")
                continue
        
        return render_template(
            "investor_dashboard.html",
            name=session["name"],
            projects=projects,
            user_investments=user_investments,
            total_invested=total_invested
        )
    return redirect("/login")


@app.route('/logout')
def logout():
    # Clear the session data
    session.clear()
    # Redirect the user to the login page (or homepage)
    return redirect(url_for('homepage'))


#Admin Panel Route
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if "role" in session and session["role"] == "admin":
        # Fetch all users and projects
        users = list(mongo.db.users.find({}, {"password": 0}))  # Exclude passwords for security
        projects = list(mongo.db.projects.find())

        if request.method == "POST":
            # Approve or Reject a project
            project_id = request.form.get("project_id")
            action = request.form.get("action")

            if project_id:
                if action == "approve":
                    mongo.db.projects.update_one(
                        {"_id": ObjectId(project_id)},
                        {"$set": {"status": "Approved"}}
                    )
                elif action == "reject":
                    mongo.db.projects.delete_one({"_id": ObjectId(project_id)})

            # Redirect to the admin page after the action
            return redirect(url_for("admin_panel"))

        return render_template("admin_dashboard.html", users=users, projects=projects)

    return redirect("/login")


@app.route("/invest/<project_id>", methods=["POST"])
def invest(project_id):
    if "role" not in session or session["role"] != "investor":
        return jsonify({"error": "Please login as an investor"}), 401
        
    try:
        # Get the investment amount from the form
        amount = float(request.form.get("investment"))
        
        # Fetch project details
        project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
        if not project:
            return jsonify({"error": "Project not found"}), 404
            
        # Validate project status
        if project.get("status") != "Approved":
            return jsonify({"error": "Project is not approved for investments"}), 400
            
        # Calculate equity percentage
        total_equity = project.get("total_equity", 0)
        funding_goal = project.get("funding_goal", 1)
        equity_percentage = (amount / funding_goal) * total_equity
        
        # Validate remaining equity
        current_equity_taken = sum(inv.get("equity_percentage", 0) for inv in project.get("investments", []))
        remaining_equity = total_equity - current_equity_taken
        
        if equity_percentage > remaining_equity:
            return jsonify({"error": f"Not enough equity available. Maximum available equity is {remaining_equity}%"}), 400
            
        # Store investment details in session
        session['pending_investment'] = {
            'amount': amount,
            'equity_percentage': equity_percentage,
            'project_id': str(project["_id"])
        }
            
        # Return success response with redirect URL
        return jsonify({
            "success": True,
            "redirect": url_for('payment', 
                              project_id=project_id, 
                              amount=amount, 
                              equity_percentage=equity_percentage)
        })
        
    except ValueError:
        return jsonify({"error": "Invalid investment amount"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/payment/<project_id>')
def payment(project_id):
    if "role" not in session or session["role"] != "investor":
        return redirect(url_for("login"))
        
    try:
        # Get pending investment from session
        pending_investment = session.get('pending_investment')
        if not pending_investment or pending_investment['project_id'] != project_id:
            return redirect(url_for('investor_dashboard'))
            
        # Fetch project details from database
        project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
        if not project:
            return redirect(url_for('investor_dashboard'))
            
        return render_template(
            "payment.html",
            project=project,
            amount=pending_investment['amount'],
            equity_percentage=pending_investment['equity_percentage'],
            name=session.get("name")
        )
        
    except Exception as e:
        print(f"Error in payment route: {str(e)}")
        return redirect(url_for('investor_dashboard'))


@app.route("/create-payment-intent/<project_id>", methods=["POST"])
def create_payment_intent(project_id):
    if "role" not in session or session["role"] != "investor":
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        # Get investment details from session
        pending_investment = session.get('pending_investment')
        if not pending_investment or pending_investment['project_id'] != project_id:
            return jsonify({"error": "Invalid investment session - please try investing again"}), 400
            
        amount = pending_investment['amount']
        equity_percentage = pending_investment['equity_percentage']
        
        print(f"Creating payment intent for project {project_id}, amount: {amount}, equity: {equity_percentage}")  # Debug log
        
        # Create Stripe PaymentIntent
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency="usd",
            automatic_payment_methods={
                "enabled": True
            },
            metadata={
                "project_id": project_id,
                "investor_id": session["user_id"],
                "equity_percentage": equity_percentage
            }
        )
        
        print(f"Payment intent created successfully: {intent.id}")  # Debug log
        
        return jsonify({
            "clientSecret": intent.client_secret
        })
        
    except Exception as e:
        print(f"Error creating payment intent: {str(e)}")  # Debug log
        return jsonify({"error": f"Payment initialization failed: {str(e)}"}), 400


@app.route("/confirm-investment/<project_id>")
def confirm_investment(project_id):
    if "role" not in session or session["role"] != "investor":
        return redirect(url_for('login'))
        
    try:
        payment_intent_id = request.args.get('payment_intent')
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if payment_intent.status == "succeeded":
            # Get investment details from pending investment in session
            pending_investment = session.get('pending_investment')
            if not pending_investment or pending_investment['project_id'] != project_id:
                flash("Invalid investment session", "error")
                return redirect(url_for('investor_dashboard'))
            
            amount = pending_investment['amount']
            equity_percentage = pending_investment['equity_percentage']
            
            # Update project with new investment
            now = datetime.utcnow()
            investment_data = {
                "investor_id": ObjectId(session["user_id"]),
                "amount": amount,
                "equity_percentage": equity_percentage,
                "date": now,
                "transaction_id": payment_intent_id
            }
            
            # Update project document
            result = mongo.db.projects.update_one(
                {
                    "_id": ObjectId(project_id),
                    "remaining_equity": {"$gte": equity_percentage}
                },
                {
                    "$push": {"investments": investment_data},
                    "$inc": {
                        "current_funding": amount,
                        "remaining_equity": -equity_percentage
                    }
                }
            )
            
            if result.modified_count == 1:
                session.pop('pending_investment', None)
                flash("Investment successful!", "success")
            else:
                # If investment fails, initiate refund
                stripe.Refund.create(payment_intent=payment_intent_id)
                flash("Investment failed, payment refunded", "error")
                
        else:
            flash("Payment failed or was cancelled", "error")
            
        return redirect(url_for('investor_dashboard'))
            
    except Exception as e:
        print(f"Error in confirm_investment: {str(e)}")  # Add logging
        flash(f"An error occurred during payment processing", "error")
        return redirect(url_for('investor_dashboard'))


# if __name__ == "__main__":
#     app.run(debug=True)

# if __name__ == '__main__':
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))



    
# from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
# from flask_pymongo import PyMongo
# from werkzeug.security import generate_password_hash, check_password_hash
# from itsdangerous import URLSafeTimedSerializer, SignatureExpired
# from flask_mail import Mail, Message
# from bson.objectid import ObjectId
# import os
# import datetime
# import stripe

# stripe.api_key = "sk_test_51QgOg4Kjkoqs3fx5f4CvkSHpYZazFpaNxOhWSj9oOU4yJ5lxMcAXdZQ0klppdvjzWSGDt4pL1fbBni3S4vFuGCrf00gcrqu6qU"

# app = Flask(__name__)
# app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey')

# # MongoDB Configuration
# # app.config["MONGO_URI"] = os.getenv("MONGO_URI")
# app.config["MONGO_URI"] = "mongodb+srv://agowdan12:0SqTqhQ5dH7Mm3JM@cluster0.vtlr69c.mongodb.net/Donations?retryWrites=true&w=majority&appName=Cluster0"
# mongo = PyMongo(app)

# # if not mongo.db:
# #     print("MongoDB connection not established!")
# if mongo.db is None:
#     print("MongoDB connection not established!")
# else:
#     print("MongoDB connection established!")



# # Flask-Mail Configuration
# app.config["MAIL_SERVER"] = "smtp.gmail.com"
# app.config["MAIL_PORT"] = 587
# app.config["MAIL_USE_TLS"] = True
# app.config["MAIL_USERNAME"] = os.environ.get('bindushree.is22@bmsce.ac.in')
# app.config["MAIL_PASSWORD"] = os.environ.get('Kusuma@0808')
# mail = Mail(app)
# s = URLSafeTimedSerializer(app.secret_key)

# @app.route("/")
# def homepage():
#     name = session.get("name", None)
#     return render_template("homepage.html", name=name)

# @app.route("/register", methods=["GET", "POST"])
# def register():
#     if request.method == "POST":
#         name = request.form.get("name")
#         email = request.form.get("email")
#         phone = request.form.get("phone")
#         password = request.form.get("password")
#         confirm_password = request.form.get("confirmPassword")
#         age = request.form.get("age")
#         role = request.form.get("role")
        
#         if not all([name, email, phone, password, confirm_password, age, role]):
#             flash("Please fill in all fields.", "error")
#             return redirect(url_for("register"))

#         if password != confirm_password:
#             flash("Passwords do not match.", "error")
#             return redirect(url_for("register"))

#         if mongo.db.users.find_one({"email": email}):
#             flash("Email already registered. Please login.", "error")
#             return redirect(url_for("login"))
        
#         hashed_password = generate_password_hash(password)
#         token = s.dumps(email, salt="email-confirm")
#         verification_url = url_for("confirm_email", token=token, _external=True)

#         try:
#             msg = Message("Confirm Your Email", sender=app.config["MAIL_USERNAME"], recipients=[email])
#             msg.body = f"Please click the link to confirm your email address: {verification_url}"
#             mail.send(msg)
#         except Exception as e:
#             flash("Error sending email. Please try again later.", "error")
#             print(f"Email send error: {e}")
#             return redirect(url_for("register"))
        
#         mongo.db.users.insert_one({
#             "name": name,
#             "email": email,
#             "password": hashed_password,
#             "phone": phone,
#             "age": int(age),
#             "role": role,
#             "verified": False,
#             "created_at": datetime.datetime.utcnow()
#         })
#         flash("A confirmation email has been sent. Please verify your email.", "success")
#         return redirect(url_for("login"))

#     return render_template("register.html")

# @app.route("/confirm_email/<token>")
# def confirm_email(token):
#     try:
#         email = s.loads(token, salt="email-confirm", max_age=3600)
#         mongo.db.users.update_one({"email": email}, {"$set": {"verified": True}})
#         flash("Email verified successfully! You can now login.", "success")
#         return redirect(url_for("login"))
#     except SignatureExpired:
#         flash("The confirmation link has expired. Please try again.", "error")
#         return redirect(url_for("register"))

# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         email = request.form.get("email")
#         password = request.form.get("password")
#         role = request.form.get("role")
        
#         user = mongo.db.users.find_one({"email": email})
#         if not user or not check_password_hash(user["password"], password):
#             flash("Invalid email or password.", "error")
#             return redirect(url_for("login"))
        
#         if not user.get("verified", False):
#             flash("Please verify your email before logging in.", "error")
#             return redirect(url_for("login"))

#         session["user_id"] = str(user["_id"])
#         session["role"] = user["role"]
#         session["name"] = user["name"]

#         # Redirect investors to investor dashboard after login
#         # Redirect based on user role
#         if role == "admin":
#             return redirect(url_for("admin_panel"))  # Redirect to the admin dashboard if the user is an admin
#         elif role == "investor":
#             # return redirect(url_for("investor_dashboard"))  # Investor dashboard if role is investor
#             return render_template("homepage.html")
#         elif role == "entrepreneur":
#             # return redirect(url_for("startup_dashboard"))  # Startup dashboard if role is startup
#             return render_template("homepage.html")
    
#     print(f"Failed login attempt for user: {email}")
#     return jsonify({"error": "Invalid credentials"}), 401



# # @app.route("/login", methods=["GET", "POST"])
# # def login():
# #     if request.method == "POST":
# #         try:
# #             if not mongo:
# #                 return jsonify({"error": "Database connection error"}), 500

# #             email = request.form.get("email")
# #             password = request.form.get("password")
# #             role = request.form.get("role")

# #             print(f"Login attempt - Email: {email}, Role: {role}")

# #             if not all([email, password, role]):
# #                 return jsonify({"error": "All fields are required"}), 400

# #             user = mongo.db.users.find_one({"email": email})

# #             if user and check_password_hash(user["password"], password) and user["role"] == role:
# #                 session["user_id"] = str(user["_id"])
# #                 session["role"] = user["role"]
# #                 session["name"] = user["name"]
# #                 print(f"Successful login for user: {email}")
                
# #                 # Redirect investors to investor dashboard after login
# #                 # Redirect based on user role
# #                 if role == "admin":
# #                     return redirect(url_for("admin_panel"))  # Redirect to the admin dashboard if the user is an admin
# #                 elif role == "investor":
# #                     # return redirect(url_for("investor_dashboard"))  # Investor dashboard if role is investor
# #                     return render_template("homepage.html")
# #                 elif role == "entrepreneur":
# #                     # return redirect(url_for("startup_dashboard"))  # Startup dashboard if role is startup
# #                     return render_template("homepage.html")
            
# #             print(f"Failed login attempt for user: {email}")
# #             return jsonify({"error": "Invalid credentials"}), 401

# #         except Exception as e:
# #             print(f"Login error: {str(e)}")
# #             return jsonify({"error": f"Login error: {str(e)}"}), 500

# #     # Get the next parameter if it exists
# #     next_page = request.args.get('next')
# #     return render_template("login.html", next=next_page)



# # Dashboard route for Startups
# @app.route("/startup-dashboard")
# def startup_dashboard():
#     if "role" in session and session["role"] == "entrepreneur":
#         user_id = session["user_id"]
        
#         # Aggregation pipeline to get projects with investor details
#         pipeline = [
#             {
#                 "$match": {"startup_id": ObjectId(user_id)}
#             },
#             {
#                 "$lookup": {
#                     "from": "users",
#                     "localField": "investments.investor_id",
#                     "foreignField": "_id",
#                     "as": "investor_details"
#                 }
#             }
#         ]
        
#         try:
#             projects = list(mongo.db.projects.aggregate(pipeline))
            
#             # Process each project to add investor names
#             for project in projects:
#                 # Create a map of investor IDs to names
#                 investor_map = {str(investor['_id']): investor['name'] 
#                               for investor in project.get('investor_details', [])}
                
#                 # Add investor names to investments
#                 if 'investments' in project:
#                     for investment in project['investments']:
#                         investor_id = str(investment['investor_id'])
#                         investment['investor_name'] = investor_map.get(investor_id, 'Unknown Investor')
#                         # Format amount to 2 decimal places
#                         investment['amount'] = float(investment['amount'])
            
#             return render_template("startup_dashboard.html", name=session["name"], projects=projects)
            
#         except Exception as e:
#             print(f"Error fetching projects: {e}")
#             return render_template("startup_dashboard.html", name=session["name"], projects=[])
            
#     return redirect("/login")



# # Route to create a project (Startup)
# # Route to create a project (Startup)
# # Update the create_project route
# @app.route("/create-project", methods=["GET", "POST"])
# def create_project():
#     if request.method == "POST":
#         title = request.form.get("title")
#         description = request.form.get("description")
#         funding_goal = float(request.form.get("funding_goal"))
#         deadline = request.form.get("deadline")
#         total_equity = float(request.form.get("total_equity", 0))  # New field
#         user_id = session["user_id"]

#         # Insert project into database
#         project = {
#             "title": title,
#             "description": description,
#             "funding_goal": funding_goal,
#             "current_funding": 0,
#             "deadline": deadline,
#             "startup_id": ObjectId(user_id),
#             "total_equity": total_equity,            # Total equity being offered
#             "remaining_equity": total_equity,        # Initially same as total equity
#             "status": "active",                     # Project status
#             "investments": []                       # List to track investments
#         }
#         mongo.db.projects.insert_one(project)
#         return redirect("/startup-dashboard")
#     return render_template("create_project.html")


# @app.route("/investor-dashboard")
# def investor_dashboard():
#     if "role" in session and session["role"] == "investor":
#         user_id = session["user_id"]
        
#         # Fetch projects the user has invested in
#         user_investments = []
#         investments = mongo.db.projects.find({"investments.investor_id": ObjectId(user_id)})
        
#         total_invested = 0
#         for project in investments:
#             for investment in project["investments"]:
#                 if str(investment["investor_id"]) == user_id:
#                     # Add investment date and transaction ID
#                     user_investments.append({
#                         "project_title": project["title"],
#                         "project_description": project["description"],
#                         "amount": investment["amount"],
#                         "equity_percentage": investment["equity_percentage"],
#                         "status": project["status"],
#                         "deadline": project["deadline"],
#                         "investment_date": investment.get("date"),
#                         "transaction_id": investment.get("transaction_id"),
#                         "project_id": str(project["_id"])  # Add project ID for tracking
#                     })
#                     total_invested += investment["amount"]
        
#         # Fetch only approved and not fully funded projects
#         projects = list(mongo.db.projects.find({
#             "status": "Approved",
#             "$expr": {
#                 "$lt": ["$current_funding", "$funding_goal"]
#             }
#         }).sort("deadline", 1))  # Sort by deadline ascending
        
#         for project in projects:
#             try:
#                 # Calculate current funding if not already set
#                 if "current_funding" not in project:
#                     current_funding = sum(inv["amount"] for inv in project.get("investments", []))
#                     # Update the project document with current funding
#                     mongo.db.projects.update_one(
#                         {"_id": project["_id"]},
#                         {"$set": {"current_funding": current_funding}}
#                     )
#                     project["current_funding"] = current_funding
                
#                 # Calculate remaining funding
#                 project["remaining_funding"] = project["funding_goal"] - project["current_funding"]
                
#                 # Calculate remaining equity
#                 total_equity_taken = sum(inv["equity_percentage"] for inv in project.get("investments", []))
#                 project["remaining_equity"] = project.get("total_equity", 0) - total_equity_taken
                
#                 # Calculate funding progress percentage
#                 project["funding_progress"] = (project["current_funding"] / project["funding_goal"]) * 100
                
#                 # Add time remaining calculation
#                 if isinstance(project["deadline"], str):
#                     deadline = datetime.strptime(project["deadline"], "%Y-%m-%d")
#                 else:
#                     deadline = project["deadline"]
#                 project["days_remaining"] = (deadline - datetime.now()).days
                
#                 # Remove projects that are fully funded or have no remaining equity
#                 if project["remaining_funding"] <= 0 or project["remaining_equity"] <= 0:
#                     projects.remove(project)
                    
#             except Exception as e:
#                 app.logger.error(f"Error processing project {project.get('_id')}: {str(e)}")
#                 continue
        
#         return render_template(
#             "investor_dashboard.html",
#             name=session["name"],
#             projects=projects,
#             user_investments=user_investments,
#             total_invested=total_invested
#         )
#     return redirect("/login")



# @app.route('/logout')
# def logout():
#     # Clear the session data
#     session.clear()
#     # Redirect the user to the login page (or homepage)
#     return redirect(url_for('homepage'))  # Replace 'login' with your login route name

# #####################333
# #Admin Panel Route
# @app.route("/admin", methods=["GET", "POST"])
# def admin_panel():
#     if "role" in session and session["role"] == "admin":
#         # Fetch all users and projects
#         users = list(mongo.db.users.find({}, {"password": 0}))  # Exclude passwords for security
#         projects = list(mongo.db.projects.find())

#         if request.method == "POST":
#             # Approve or Reject a project
#             project_id = request.form.get("project_id")
#             action = request.form.get("action")

#             if project_id:
#                 if action == "approve":
#                     mongo.db.projects.update_one(
#                         {"_id": ObjectId(project_id)},
#                         {"$set": {"status": "Approved"}}
#                     )
#                 elif action == "reject":
#                     mongo.db.projects.delete_one({"_id": ObjectId(project_id)})

#             # Redirect to the admin page after the action
#             return redirect(url_for("admin_panel"))

#         return render_template("admin_dashboard.html", users=users, projects=projects)

#     return redirect("/login")




# from datetime import datetime

# # Backend route (app.py)
# @app.route("/invest/<project_id>", methods=["POST"])
# def invest(project_id):
#     if "role" not in session or session["role"] != "investor":
#         return jsonify({"error": "Please login as an investor"}), 401
        
#     try:
#         # Get the investment amount from the form
#         amount = float(request.form.get("investment"))
        
#         # Fetch project details
#         project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
#         if not project:
#             return jsonify({"error": "Project not found"}), 404
            
#         # Validate project status
#         if project.get("status") != "Approved":
#             return jsonify({"error": "Project is not approved for investments"}), 400
            
#         # Calculate equity percentage
#         total_equity = project.get("total_equity", 0)
#         funding_goal = project.get("funding_goal", 1)
#         equity_percentage = (amount / funding_goal) * total_equity
        
#         # Validate remaining equity
#         current_equity_taken = sum(inv.get("equity_percentage", 0) for inv in project.get("investments", []))
#         remaining_equity = total_equity - current_equity_taken
        
#         if equity_percentage > remaining_equity:
#             return jsonify({"error": f"Not enough equity available. Maximum available equity is {remaining_equity}%"}), 400
            
#         # Store investment details in session
#         session['pending_investment'] = {
#             'amount': amount,
#             'equity_percentage': equity_percentage,
#             'project_id': str(project["_id"])
#         }
            
#         # Return success response with redirect URL
#         return jsonify({
#             "success": True,
#             "redirect": url_for('payment', 
#                               project_id=project_id, 
#                               amount=amount, 
#                               equity_percentage=equity_percentage)
#         })
        
#     except ValueError:
#         return jsonify({"error": "Invalid investment amount"}), 400
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


# @app.route('/payment/<project_id>')
# def payment(project_id):
#     if "role" not in session or session["role"] != "investor":
#         return redirect(url_for("login"))
        
#     try:
#         # Get pending investment from session
#         pending_investment = session.get('pending_investment')
#         if not pending_investment or pending_investment['project_id'] != project_id:
#             return redirect(url_for('investor_dashboard'))
            
#         # Fetch project details from database
#         project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
#         if not project:
#             return redirect(url_for('investor_dashboard'))
            
#         return render_template(
#             "payment.html",
#             project=project,
#             amount=pending_investment['amount'],
#             equity_percentage=pending_investment['equity_percentage'],
#             name=session.get("name")
#         )
        
#     except Exception as e:
#         print(f"Error in payment route: {str(e)}")
#         return redirect(url_for('investor_dashboard'))
    




# @app.route("/create-payment-intent/<project_id>", methods=["POST"])
# def create_payment_intent(project_id):
#     if "role" not in session or session["role"] != "investor":
#         return jsonify({"error": "Unauthorized"}), 401
        
#     try:
#         # Get investment details from session
#         pending_investment = session.get('pending_investment')
#         if not pending_investment or pending_investment['project_id'] != project_id:
#             return jsonify({"error": "Invalid investment session - please try investing again"}), 400
            
#         amount = pending_investment['amount']
#         equity_percentage = pending_investment['equity_percentage']
        
#         print(f"Creating payment intent for project {project_id}, amount: {amount}, equity: {equity_percentage}")  # Debug log
        
#         # Create Stripe PaymentIntent
#         intent = stripe.PaymentIntent.create(
#             amount=int(amount * 100),  # Convert to cents
#             currency="usd",
#             automatic_payment_methods={
#                 "enabled": True
#             },
#             metadata={
#                 "project_id": project_id,
#                 "investor_id": session["user_id"],
#                 "equity_percentage": equity_percentage
#             }
#         )
        
#         print(f"Payment intent created successfully: {intent.id}")  # Debug log
        
#         return jsonify({
#             "clientSecret": intent.client_secret
#         })
        
#     except Exception as e:
#         print(f"Error creating payment intent: {str(e)}")  # Debug log
#         return jsonify({"error": f"Payment initialization failed: {str(e)}"}), 400



# @app.route("/confirm-investment/<project_id>")
# def confirm_investment(project_id):
#     if "role" not in session or session["role"] != "investor":
#         return redirect(url_for('login'))
        
#     try:
#         payment_intent_id = request.args.get('payment_intent')
#         payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
#         if payment_intent.status == "succeeded":
#             # Get investment details from pending investment in session
#             pending_investment = session.get('pending_investment')
#             if not pending_investment or pending_investment['project_id'] != project_id:
#                 flash("Invalid investment session", "error")
#                 return redirect(url_for('investor_dashboard'))
            
#             amount = pending_investment['amount']
#             equity_percentage = pending_investment['equity_percentage']
            
#             # Update project with new investment
#             now = datetime.utcnow()
#             investment_data = {
#                 "investor_id": ObjectId(session["user_id"]),
#                 "amount": amount,
#                 "equity_percentage": equity_percentage,
#                 "date": now,
#                 "transaction_id": payment_intent_id
#             }
            
#             # Update project document
#             result = mongo.db.projects.update_one(
#                 {
#                     "_id": ObjectId(project_id),
#                     "remaining_equity": {"$gte": equity_percentage}
#                 },
#                 {
#                     "$push": {"investments": investment_data},
#                     "$inc": {
#                         "current_funding": amount,
#                         "remaining_equity": -equity_percentage
#                     }
#                 }
#             )
            
#             if result.modified_count == 1:
#                 session.pop('pending_investment', None)
#                 flash("Investment successful!", "success")
#             else:
#                 # If investment fails, initiate refund
#                 stripe.Refund.create(payment_intent=payment_intent_id)
#                 flash("Investment failed, payment refunded", "error")
                
#         else:
#             flash("Payment failed or was cancelled", "error")
            
#         return redirect(url_for('investor_dashboard'))
            
#     except Exception as e:
#         print(f"Error in confirm_investment: {str(e)}")  # Add logging
#         flash(f"An error occurred during payment processing", "error")
#         return redirect(url_for('investor_dashboard'))




# if __name__ == "__main__":
#     app.run(debug=True)