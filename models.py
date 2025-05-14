from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta

class User:
    def __init__(self, db):
        self.collection = db["users"]

    def create_user(self, name, email, password, phone, age, role, verified=False):
        user_data = {
            "name": name,
            "email": email,
            "password": password,  # Passwords should be hashed before calling this
            "phone": phone,
            "age": age,
            "role": role,
            "verified": verified,
            "created_at": datetime.utcnow()
        }
        return self.collection.insert_one(user_data).inserted_id

    def find_by_email(self, email):
        return self.collection.find_one({"email": email})

    def find_by_id(self, user_id):
        return self.collection.find_one({"_id": ObjectId(user_id)})

    def set_verified(self, email):
        return self.collection.update_one(
            {"email": email},
            {"$set": {"verified": True}}
        )


class Project:
    def __init__(self, db):
        self.collection = db["projects"]

    def create_project(self, title, description, funding_goal, deadline, startup_id, total_equity):
        project_data = {
            "title": title,
            "description": description,
            "funding_goal": funding_goal,
            "current_funding": 0,
            "deadline": deadline,
            "startup_id": ObjectId(startup_id),
            "total_equity": total_equity,      # Total equity being offered
            "remaining_equity": total_equity,  # Initially same as total equity
            "status": "active",                # Project status: active, Approved, completed, etc.
            "investments": []                  # List to track investments
        }
        return self.collection.insert_one(project_data).inserted_id

    def find_all_approved_projects(self):
        return list(self.collection.find({"status": "Approved"}))

    def find_by_id(self, project_id):
        return self.collection.find_one({"_id": ObjectId(project_id)})

    def approve_project(self, project_id):
        return self.collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"status": "Approved"}}
        )

    def update_project_status(self, project_id):
        project = self.find_by_id(project_id)
        if project and project["current_funding"] >= project["funding_goal"]:
            return self.collection.update_one(
                {"_id": ObjectId(project_id)},
                {"$set": {"status": "completed"}}
            )
        return None


class Investor:
    def __init__(self, db):
        self.collection = db["projects"]  # Investor investments are kept within projects

    def invest_in_project(self, project_id, investor_id, amount, equity_percentage):
        project = self.collection.find_one({"_id": ObjectId(project_id)})
        if not project:
            return False
        remaining_equity = project.get("remaining_equity", 0)
        if remaining_equity < equity_percentage:
            return False

        new_funding = project.get("current_funding", 0) + amount
        new_remaining_equity = remaining_equity - equity_percentage

        investment = {
            "investor_id": ObjectId(investor_id),
            "amount": amount,
            "equity_percentage": equity_percentage,
            "date": datetime.utcnow()
        }

        update_result = self.collection.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "current_funding": new_funding,
                    "remaining_equity": new_remaining_equity
                },
                "$push": {
                    "investments": investment
                }
            }
        )

        if update_result.modified_count > 0:
            if new_funding >= project["funding_goal"]:
                self.collection.update_one(
                    {"_id": ObjectId(project_id)},
                    {"$set": {"status": "completed"}}
                )
            return True

        return False


class PasswordResetToken:
    def __init__(self, db):
        self.collection = db["password_reset_tokens"]

    def create_token(self, email, otp):
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        token_data = {
            "email": email,
            "otp": otp,
            "expires_at": expires_at,
            "used": False
        }
        return self.collection.insert_one(token_data).inserted_id

    def find_valid_token(self, email, otp):
        return self.collection.find_one({
            "email": email,
            "otp": otp,
            "expires_at": {"$gt": datetime.utcnow()},
            "used": False
        })

    def mark_token_as_used(self, token_id):
        return self.collection.update_one(
            {"_id": ObjectId(token_id)},
            {"$set": {"used": True}}
        )

class ProjectAnalytics:
    def __init__(self, db):
        self.collection = db["investments"]
        self.projects = db["projects"]
        self.users = db["users"]

    def get_project_metrics(self, project_id):
        project = self.projects.find_one({"_id": ObjectId(project_id)})
        investments = list(self.collection.find({"project_id": ObjectId(project_id)}))

        total_raised = sum(inv["amount"] for inv in investments)
        investor_count = len(set(str(inv["investor_id"]) for inv in investments))

        metrics = {
            "total_raised": total_raised,
            "goal_progress": (total_raised / project["funding_goal"]) * 100 if project else 0,
            "investor_count": investor_count,
            "days_remaining": (project["deadline"] - datetime.utcnow()).days if project else 0
        }
        return metrics

    def get_investment_timeline(self, project_id):
        pipeline = [
            {"$match": {"project_id": ObjectId(project_id)}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                "daily_total": {"$sum": "$amount"}
            }},
            {"$sort": {"_id": 1}}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_investor_demographics(self, project_id):
        pipeline = [
            {"$match": {"project_id": ObjectId(project_id)}},
            {"$lookup": {
                "from": "users",
                "localField": "investor_id",
                "foreignField": "_id",
                "as": "investor"
            }},
            {"$unwind": "$investor"},
            {"$group": {
                "_id": {"$floor": {"$divide": ["$investor.age", 10]}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_investment_distribution(self, project_id):
        pipeline = [
            {"$match": {"project_id": ObjectId(project_id)}},
            {"$bucket": {
                "groupBy": "$amount",
                "boundaries": [0, 1000, 5000, 10000, 50000, 100000],
                "default": "100000+",
                "output": {
                    "count": {"$sum": 1},
                    "total": {"$sum": "$amount"}
                }
            }}
        ]
        return list(self.collection.aggregate(pipeline))



# from flask_pymongo import PyMongo
# from bson.objectid import ObjectId
# from datetime import datetime

# class User:
#     def __init__(self, db):
#         self.collection = db["users"]

#     def create_user(self, name, email, password, phone, age, role,verify):
#         user_data = {
#             "name": name,
#             "email": email,
#             "password": password,  # Note: Hash passwords in production
#             "phone": phone,
#             "age": age,
#             "role": role,
#             "verified":verify
#         }
#         return self.collection.insert_one(user_data).inserted_id

#     def find_by_email(self, email):
#         return self.collection.find_one({"email": email})

#     def find_by_id(self, user_id):
#         return self.collection.find_one({"_id": ObjectId(user_id)})

# class Project:
#     def __init__(self, db):
#         self.collection = db["projects"]

#     def create_project(self, title, description, funding_goal, deadline, startup_id, total_equity):
#         project_data = {
#             "title": title,
#             "description": description,
#             "funding_goal": funding_goal,
#             "current_funding": 0,
#             "deadline": deadline,
#             "startup_id": ObjectId(startup_id),
#             "approved": False,  # Default state is not approved
#             "total_equity": total_equity,  # Total equity being offered
#             "remaining_equity": total_equity,  # Remaining equity available
#             "status": "active",  # Status can be: active, completed, expired
#             "investments": []  # List to track all investments
#         }
#         return self.collection.insert_one(project_data).inserted_id

#     def find_all_approved_projects(self):
#         return list(self.collection.find({"approved": True}))

#     def find_by_id(self, project_id):
#         return self.collection.find_one({"_id": ObjectId(project_id)})

#     def approve_project(self, project_id):
#         return self.collection.update_one(
#             {"_id": ObjectId(project_id)},
#             {"$set": {"approved": True}}
#         )
    
#     def update_project_status(self, project_id):
#         project = self.find_by_id(project_id)
#         if project and project["current_funding"] >= project["funding_goal"]:
#             return self.collection.update_one(
#                 {"_id": ObjectId(project_id)},
#                 {"$set": {"status": "completed"}}
#             )
#         return None

# class Investor:
#     def __init__(self, db):
#         self.collection = db["projects"]  # Note: We're using the projects collection

#     def invest_in_project(self, project_id, investor_id, amount, equity_percentage):
#         project = self.collection.find_one({"_id": ObjectId(project_id)})
#         if project and project["remaining_equity"] >= equity_percentage:
#             new_funding = project.get("current_funding", 0) + amount
#             new_remaining_equity = project["remaining_equity"] - equity_percentage
        
#         # Create investment record with investor details
#             investment = {
#                 "investor_id": ObjectId(investor_id),
#                 "amount": amount,
#                 "equity_percentage": equity_percentage,
#                 "timestamp": datetime.utcnow()
#                     }
        
#             update_result = self.collection.update_one(
#               {"_id": ObjectId(project_id)},
#                 {
#                 "$set": {
#                     "current_funding": new_funding,
#                     "remaining_equity": new_remaining_equity
#                 },
#                 "$push": {"investments": investment}
#             }
#         )
        
#             if update_result.modified_count > 0:
#                 if new_funding >= project["funding_goal"]:
#                     self.collection.update_one(
#                     {"_id": ObjectId(project_id)},
#                     {"$set": {"status": "completed"}}
#                 )
#                 return True
#         return False

# class ProjectAnalytics:
#     def _init_(self, db):
#         self.collection = db["investments"]
#         self.projects = db["projects"]
#         self.users = db["users"]

#     def get_project_metrics(self, project_id):
#         project = self.projects.find_one({"_id": ObjectId(project_id)})
#         investments = list(self.collection.find({"project_id": ObjectId(project_id)}))
        
#         total_raised = sum(inv["amount"] for inv in investments)
#         investor_count = len(set(str(inv["investor_id"]) for inv in investments))
        
#         metrics = {
#             "total_raised": total_raised,
#             "goal_progress": (total_raised / project["funding_goal"]) * 100 if project else 0,
#             "investor_count": investor_count,
#             "days_remaining": (project["deadline"] - datetime.utcnow()).days if project else 0
#         }
#         return metrics

#     def get_investment_timeline(self, project_id):
#         pipeline = [
#             {"$match": {"project_id": ObjectId(project_id)}},
#             {"$group": {
#                 "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
#                 "daily_total": {"$sum": "$amount"}
#             }},
#             {"$sort": {"_id": 1}}
#         ]
#         return list(self.collection.aggregate(pipeline))

#     def get_investor_demographics(self, project_id):
#         pipeline = [
#             {"$match": {"project_id": ObjectId(project_id)}},
#             {"$lookup": {
#                 "from": "users",
#                 "localField": "investor_id",
#                 "foreignField": "_id",
#                 "as": "investor"
#             }},
#             {"$unwind": "$investor"},
#             {"$group": {
#                 "_id": {"$floor": {"$divide": ["$investor.age", 10]}},
#                 "count": {"$sum": 1}
#             }},
#             {"$sort": {"_id": 1}}
#         ]
#         return list(self.collection.aggregate(pipeline))

#     def get_investment_distribution(self, project_id):
#         pipeline = [
#             {"$match": {"project_id": ObjectId(project_id)}},
#             {"$bucket": {
#                 "groupBy": "$amount",
#                 "boundaries": [0, 1000, 5000, 10000, 50000, 100000],
#                 "default": "100000+",
#                 "output": {
#                     "count": {"$sum": 1},
#                     "total": {"$sum": "$amount"}
#                 }
#             }}
#         ]
#         return list(self.collection.aggregate(pipeline))