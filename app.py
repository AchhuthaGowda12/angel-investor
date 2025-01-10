from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import os
from bson.objectid import ObjectId
import datetime
from models import Investor


app = Flask(__name__)

# Configuration
app.config["MONGO_URI"] = "mongodb+srv://amogh5533:2AehyekZzcrEIV9m@cluster0.kc2as.mongodb.net/angelfundr?retryWrites=true&w=majority&appName=Cluster0"
app.secret_key = "your_secret_key_here"  # Replace with a strong secret key

# Initialize MongoDB connection with error handling
try:
    mongo = PyMongo(app)
    # Test the connection
    mongo.db.command('ping')
    print("Connected successfully to MongoDB!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    mongo = None

@app.route("/")
def homepage():
    name = session.get("name", None)  # Retrieve the user's name from the session
    return render_template("homepage.html", name=name)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            # Check if MongoDB connection is available
            if not mongo:
                print("MongoDB connection is not available")
                return jsonify({"error": "Database connection error"}), 500

            # Get form data with debug logging
            name = request.form.get("name")
            email = request.form.get("email")
            phone = request.form.get("phone")
            password = request.form.get("password")
            confirm_password = request.form.get("confirmPassword")
            age = request.form.get("age")
            role = request.form.get("role")

            print(f"Received registration data - Email: {email}, Role: {role}")  # Debug log

            # Basic validation with detailed error messages
            if not all([name, email, phone, password, confirm_password, age, role]):
                missing_fields = [field for field, value in {
                    'name': name, 'email': email, 'phone': phone,
                    'password': password, 'confirmPassword': confirm_password,
                    'age': age, 'role': role
                }.items() if not value]
                print(f"Missing fields: {missing_fields}")  # Debug log
                return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

            if password != confirm_password:
                return jsonify({"error": "Passwords do not match"}), 400

            try:
                age = int(age)
                if age <= 0:
                    return jsonify({"error": "Age must be a positive number"}), 400
            except ValueError:
                return jsonify({"error": "Age must be a valid number"}), 400

            # Check if user already exists
            existing_user = mongo.db.users.find_one({"email": email})
            if existing_user:
                return jsonify({"error": "Email already registered"}), 400

            # Hash password
            hashed_password = generate_password_hash(password)

            # Create user document
            user_data = {
                "name": name,
                "email": email,
                "password": hashed_password,
                "phone": phone,
                "age": age,
                "role": role,
                "created_at": datetime.datetime.utcnow()
            }

            # Insert user with debug logging
            print("Attempting to insert user document...")  # Debug log
            result = mongo.db.users.insert_one(user_data)
            
            if result.inserted_id:
                print(f"User registered successfully with ID: {result.inserted_id}")  # Debug log
                return redirect(url_for("login"))
            else:
                print("User insertion failed - no inserted_id returned")  # Debug log
                return jsonify({"error": "Registration failed - database error"}), 500

        except Exception as e:
            print(f"Detailed registration error: {str(e)}")  # Debug log
            return jsonify({"error": f"Registration error: {str(e)}"}), 500

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            if not mongo:
                return jsonify({"error": "Database connection error"}), 500

            email = request.form.get("email")
            password = request.form.get("password")
            role = request.form.get("role")

            print(f"Login attempt - Email: {email}, Role: {role}")

            if not all([email, password, role]):
                return jsonify({"error": "All fields are required"}), 400

            user = mongo.db.users.find_one({"email": email})

            if user and check_password_hash(user["password"], password) and user["role"] == role:
                session["user_id"] = str(user["_id"])
                session["role"] = user["role"]
                session["name"] = user["name"]
                print(f"Successful login for user: {email}")
                
                # Redirect investors to investor dashboard after login
                # Redirect based on user role
                if role == "admin":
                    return redirect(url_for("admin_panel"))  # Redirect to the admin dashboard if the user is an admin
                elif role == "investor":
                    return redirect(url_for("investor_dashboard"))  # Investor dashboard if role is investor
                elif role == "entrepreneur":
                    return redirect(url_for("startup_dashboard"))  # Startup dashboard if role is startup

                # if role == "admin":
                #     return redirect(url_for("admin_dashboard"))
                # return redirect(url_for("homepage"))
            
            print(f"Failed login attempt for user: {email}")
            return jsonify({"error": "Invalid credentials"}), 401

        except Exception as e:
            print(f"Login error: {str(e)}")
            return jsonify({"error": f"Login error: {str(e)}"}), 500

    # Get the next parameter if it exists
    next_page = request.args.get('next')
    return render_template("login.html", next=next_page)

# Dashboard route for Startups
@app.route("/startup-dashboard")
def startup_dashboard():
    if "role" in session and session["role"] == "entrepreneur":
        user_id = session["user_id"]
        projects = list(mongo.db.projects.find({"startup_id": ObjectId(user_id)}))
        return render_template("startup_dashboard.html", name=session["name"], projects=projects)
    return redirect("/login")

# Dashboard route for Investors
@app.route("/investor-dashboard")
def investor_dashboard():
    if "role" in session and session["role"] == "investor":
        # Get all projects and ensure they have the required fields
        projects = list(mongo.db.projects.find())
        for project in projects:
            # Add missing fields if they don't exist
            if 'total_equity' not in project:
                project['total_equity'] = 0
            if 'remaining_equity' not in project:
                project['remaining_equity'] = project['total_equity']
            if 'status' not in project:
                project['status'] = 'active'
            if 'investments' not in project:
                project['investments'] = []
        return render_template("investor_dashboard.html", name=session["name"], projects=projects)
    return redirect("/login")


# Route to create a project (Startup)
# Route to create a project (Startup)
# Update the create_project route
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

# Update the invest route
@app.route("/invest/<project_id>", methods=["POST"])
def invest(project_id):
    if session["role"] == "investor":
        try:
            # Get the investment amount from the form
            amount = float(request.form.get("investment"))
            
            # Fetch project details
            project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})
            if not project:
                return jsonify({"error": "Project not found"}), 404
            
            # Check if the project is active
            if project.get("status") != "active":
                return jsonify({"error": "Project is not accepting investments"}), 400
            
            # Calculate equity percentage
            total_equity = project.get("total_equity", 0)
            funding_goal = project.get("funding_goal", 1)  # Avoid division by zero
            equity_percentage = (amount / funding_goal) * total_equity
            
            # Ensure the equity percentage is available
            remaining_equity = project.get("remaining_equity", total_equity)
            if equity_percentage > remaining_equity:
                return jsonify({"error": "Not enough equity available"}), 400
            
            # Create an instance of the Investor class
            investor = Investor(mongo.db)
            
            # Process the investment
            if investor.invest_in_project(project_id, session["user_id"], amount, equity_percentage):
                return redirect(url_for("investor_dashboard"))
            else:
                return jsonify({"error": "Investment failed"}), 400
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return redirect("/login")


# Update the invest_pay route
@app.route('/invest/<project_id>/pay', methods=['POST'])
def invest_pay(project_id):
    if session.get("role") == "investor":
        try:
            amount = float(request.form.get("investment")) * 100  # Amount in cents
            equity_percentage = float(request.form.get("equity_percentage"))
            
            intent = stripe.PaymentIntent.create(
                amount=int(amount),
                currency="usd",
                metadata={
                    "project_id": project_id,
                    "investor_id": session.get("user_id"),
                    "equity_percentage": equity_percentage
                },
            )
            return jsonify({"clientSecret": intent['client_secret']})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Unauthorized access"}), 401

# Route to invest in a project (Investor)
# @app.route("/invest/<project_id>", methods=["POST"])
# def invest(project_id):
#     if session["role"] == "investor":
#         amount = float(request.form.get("investment"))
#         project = mongo.db.projects.find_one({"_id": ObjectId(project_id)})

#         if project:
#             # Update project's current funding
#             new_funding = project["current_funding"] + amount
#             mongo.db.projects.update_one({"_id": ObjectId(project_id)}, {"$set": {"current_funding": new_funding}})

#             # Record the investment
#             investment = {
#                 "investor_id": ObjectId(session["user_id"]),
#                 "project_id": ObjectId(project_id),
#                 "amount": amount,
#                 "date": datetime.datetime.utcnow()
#             }
#             mongo.db.investments.insert_one(investment)
#             return redirect("/investor-dashboard")
#     return redirect("/login")

@app.route('/logout')
def logout():
    # Clear the session data
    session.clear()
    # Redirect the user to the login page (or homepage)
    return redirect(url_for('homepage'))  # Replace 'login' with your login route name

#####################333
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


if __name__ == "__main__":
    app.run(debug=True)