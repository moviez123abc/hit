from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson import ObjectId
import os
import pdfkit 
from datetime import datetime
from functools import wraps
import uuid

app = Flask(__name__)
app.secret_key = "hit_secret_key_123"

# --- MongoDB Configuration ---
MONGO_URI = "mongodb+srv://texlablog_db_user:1buBUXPsE1CBo1Re@testforcustomers.mlm5xxn.mongodb.net"
client = MongoClient(MONGO_URI)
db = client['HIT_Database']
sheets_col = db['Sheets']
customers_col = db['Customers']
users_col = db['Users']

def create_default_admin():
    # Users কালেকশনে ইউজারনেম '1' আছে কি না চেক করা
    admin_exists = db.Users.find_one({"username": "1"})
    
    if not admin_exists:
        db.Users.insert_one({
            "username": "1",
            "password": "1",
            "role": "admin",
            "assigned_sheets": [] # অ্যাডমিনের জন্য সব শীট ওপেন থাকবে লজিকে
        })
        print("Default Admin Created: Username: 1, Password: 1")

# লগইন রিকোয়ার্ড ডেকোরেটর (সুরক্ষার জন্য)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ১. লগইন রাউট (Device Tracking সহ) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # ডাটাবেস থেকে ইউজার খোঁজা (db.Users কালেকশন ব্যবহার করা হয়েছে)
        user = db.Users.find_one({"username": username, "password": password})
        
        if user:
            # ডিভাইস ইনফো সংগ্রহ
            ua_string = request.headers.get('User-Agent')
            user_agent = parse(ua_string)
            
            device_info = {
                "device_id": str(uuid.uuid4())[:8],
                "device_model": user_agent.device.family,
                "os": user_agent.os.family,
                "browser": user_agent.browser.family,
                "ip": request.remote_addr,
                "login_time": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
                "status": "current"
            }

            # নিরাপত্তা: আগের সব ডিভাইসের স্ট্যাটাস 'past' করা (যদি devices ফিল্ড থাকে)
            if 'devices' in user:
                db.Users.update_one(
                    {"_id": user['_id']},
                    {"$set": {"devices.$[].status": "past"}}
                )

            # নতুন ডিভাইসটি লিস্টে যোগ করা
            db.Users.update_one(
                {"_id": user['_id']},
                {"$push": {"devices": device_info}}
            )

            # সেশন সেট করা
            session['user'] = user['username']
            session['role'] = user['role']
            session['user_id'] = str(user['_id'])
            
            flash(f"স্বাগতম, {username}!", "success")
            return redirect(url_for('index'))
        else:
            flash("ভুল ইউজারনেম বা পাসওয়ার্ড!", "danger")
            
    return render_template('login.html')


# --- ২. অ্যাডমিন ডিভাইস লগ পেজ (Data Retrieval) ---
@app.route('/admin/device_logs')
def device_logs():
    try:
        # সব ইউজার যাদের 'devices' লিস্ট আছে তাদের নিয়ে আসা
        # লগইন রাউটের সাথে মিল রেখে db.Users ব্যবহার করা হয়েছে
        users = list(db.Users.find({"devices": {"$exists": True, "$not": {"$size": 0}}}))
        
        # ডিবাগ করার জন্য (টার্মিনালে দেখা যাবে ডাটা আসছে কি না)
        print(f"DEBUG: Found {len(users)} users with login logs")
        
        return render_template('admin_device_logs.html', users=users)
    except Exception as e:
        print(f"Error loading logs: {e}")
        flash("লগ লোড করতে সমস্যা হয়েছে।", "danger")
        return redirect(url_for('index'))


# --- ৩. ডিভাইস রিমুভ রাউট (Force Logout) ---
@app.route('/admin/remove_device/<user_id>/<device_id>', methods=['POST'])
def remove_device(user_id, device_id):
    try:
        # নির্দিষ্ট ইউজারের devices লিস্ট থেকে p_id অনুযায়ী ডাটা রিমুভ করা
        db.Users.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"devices": {"device_id": device_id}}}
        )
        return {"status": "success", "message": "ডিভাইসটি সরানো হয়েছে"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
        
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    if session['role'] == 'admin':
        # অ্যাডমিন সব শীট দেখবে
        sheets = list(db.Sheets.find())
    else:
        # এমপ্লয়ি শুধু তার বরাদ্দকৃত শীট দেখবে
        user = db.Users.find_one({"username": session['user']})
        assigned_ids = [ObjectId(sid) for sid in user.get('assigned_sheets', [])]
        sheets = list(db.Sheets.find({"_id": {"$in": assigned_ids}}))
        
    return render_template('index.html', sheets=sheets)

@app.route('/admin/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if session.get('role') != 'admin':
        return "Access Denied"
        
    if request.method == 'POST':
        emp_data = {
            "username": request.form.get('username'),
            "password": request.form.get('password'),
            "role": "employee",
            "assigned_sheets": request.form.getlist('sheets') # মাল্টিপল শীট সিলেক্ট
        }
        db.Users.insert_one(emp_data)
        flash("নতুন এমপ্লয়ি যোগ করা হয়েছে", "success")
        
    all_sheets = list(db.Sheets.find())
    return render_template('add_employee.html', sheets=all_sheets)

@app.route('/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    # শুধুমাত্র অ্যাডমিন এই পেজে ঢুকতে পারবে
    if session.get('role') != 'admin':
        flash("আপনার এই পেজে প্রবেশের অনুমতি নেই।", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        assigned_sheets = request.form.getlist('assigned_sheets') # মাল্টিপল আইডি লিস্ট

        if not username or not password:
            flash("ইউজারনেম এবং পাসওয়ার্ড উভয়ই প্রয়োজন।", "warning")
        else:
            # চেক করা যে এই ইউজারনেম আগে থেকে আছে কি না
            existing_user = db.Users.find_one({"username": username})

            if existing_user:
                # ইউজার থাকলে তার পাসওয়ার্ড এবং শীট আপডেট হবে
                db.Users.update_one(
                    {"username": username},
                    {"$set": {
                        "password": password,
                        "assigned_sheets": assigned_sheets
                    }}
                )
                flash(f"ইউজার '{username}' এর তথ্য আপডেট করা হয়েছে।", "success")
            else:
                # নতুন ইউজার তৈরি
                new_user = {
                    "username": username,
                    "password": password,
                    "role": "employee", # ডিফল্টভাবে এমপ্লয়ি
                    "assigned_sheets": assigned_sheets
                }
                db.Users.insert_one(new_user)
                flash(f"নতুন এমপ্লয়ি '{username}' যোগ করা হয়েছে।", "success")

        return redirect(url_for('manage_users'))

    # GET রিকোয়েস্ট: ডাটা লোড করা
    # ১. সব ইউজার লিস্ট (অ্যাডমিন ছাড়া বাকিদের বা সবাইকে দেখাতে পারেন)
    users_list = list(db.Users.find())
    
    # ২. সব শীট লিস্ট (ড্রপডাউনে দেখানোর জন্য)
    all_sheets = list(db.Sheets.find())

    return render_template('manage_users.html', users=users_list, all_sheets=all_sheets)

# ইউজার ডিলিট করার রুট (প্রয়োজন হলে)
@app.route('/delete_user/<username>')
@login_required
def delete_user(username):
    # অ্যাডমিন কি না এবং নিজের ইউজারনেম ডিলিট করছে কি না চেক
    if session.get('role') == 'admin':
        if username == session.get('user'):
            flash("অ্যাডমিন নিজেকে ডিলিট করতে পারবে না।", "danger")
        else:
            # কালেকশনের নাম 'Users' না 'users' সেটি নিশ্চিত হয়ে নিন (কেস সেনসিটিভ)
            result = db.Users.delete_one({"username": username})
            if result.deleted_count > 0:
                flash(f"ইউজার '{username}' মুছে ফেলা হয়েছে।", "info")
            else:
                flash("ইউজারটি খুঁজে পাওয়া যায়নি।", "warning")
    else:
        flash("আপনার অনুমতি নেই।", "danger")
        
    return redirect(url_for('manage_users'))

@app.route('/save_data_pending', methods=['POST'])
def save_data_pending():
    data = request.form.to_dict()
    data['status'] = 'pending'
    data['submitted_by'] = session['user']
    db.Pending_Data.insert_one(data)
    return "অ্যাডমিনের অনুমোদনের জন্য পাঠানো হয়েছে।"

@app.route('/admin/approve/<pending_id>')
@login_required
def approve_data(pending_id):
    if session.get('role') != 'admin':
        return "Access Denied"
        
    pending_item = db.Pending_Data.find_one({"_id": ObjectId(pending_id)})
    if pending_item:
        # পেন্ডিং ডাটা থেকে অরিজিনাল কাস্টমার আইডি খুঁজে বের করা
        original_cust_id = pending_item.get('customer_id') 
        
        # ডাটা ক্লিন করা (আইডি রিমুভ করা যাতে কনফ্লিক্ট না হয়)
        update_data = dict(pending_item)
        update_data.pop('_id', None)
        update_data['status'] = 'approved'

        # মূল কালেকশনে আপডেট
        customers_col.update_one({"_id": ObjectId(original_cust_id)}, {"$set": update_data})
        
        # পেন্ডিং থেকে ডিলিট
        db.Pending_Data.delete_one({"_id": ObjectId(pending_id)})
        flash("ডাটা অনুমোদিত হয়েছে!", "success")
        
    return redirect(url_for('index'))

@app.route('/update_user/<user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if session.get('role') != 'admin':
        return redirect('/')
        
    new_username = request.form.get('username')
    new_password = request.form.get('password')
    assigned_sheets = request.form.getlist('assigned_sheets') # একাধিক শীট নেওয়ার জন্য getlist
    
    update_data = {
        "username": new_username,
        "assigned_sheets": assigned_sheets
    }
    
    # যদি পাসওয়ার্ড ফিল্ডে কিছু লেখা থাকে তবেই সেটি আপডেট হবে
    if new_password:
        update_data["password"] = new_password # বাস্তব প্রজেক্টে হাশ ব্যবহার করা উচিত
        
    users_col.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    flash("ইউজার সফলভাবে আপডেট করা হয়েছে!", "success")
    return redirect(url_for('manage_users'))

from flask import render_template, redirect, url_for, flash, session, request
from bson import ObjectId

# ১. পেন্ডিং অনুমোদন তালিকার মেইন পেজ
@app.route('/pending_approvals')
@login_required
def pending_approvals():
    if session.get('role') != 'admin':
        flash("আপনার এই পেজে প্রবেশের অনুমতি নেই!", "danger")
        return redirect('/')
    
    try:
        # নতুন কাস্টমার যারা 'pending' স্ট্যাটাসে আছে
        pending_customers = list(customers_col.find({"status": "pending"}).sort("entry_at", -1))
        for p in pending_customers:
            sheet = sheets_col.find_one({"_id": ObjectId(p['sheet_id'])})
            p['sheet_name'] = f"{sheet['group_name']} ({sheet['code_no']})" if sheet else "Unknown Sheet"

        # কিস্তি আপডেট যা 'pending_updates' কালেকশনে আছে
        pending_updates = list(db.pending_updates.find().sort("entry_at", -1))
        for u in pending_updates:
            sheet = sheets_col.find_one({"_id": ObjectId(u['sheet_id'])})
            u['sheet_name'] = f"{sheet['group_name']} ({sheet['code_no']})" if sheet else "Unknown Sheet"

        return render_template(
            'pending_approvals.html', 
            customers=pending_customers, 
            kisti=pending_updates
        )
    except Exception as e:
        print(f"Error: {e}")
        flash("ডাটা লোড করতে সমস্যা হয়েছে।", "danger")
        return redirect('/')

# --- কিস্তি (Kisti) অনুমোদন ও বাতিল রুটস ---

@app.route('/approve_sheet_update/<update_id>')
@login_required
def approve_sheet_update(update_id):
    if session.get('role') != 'admin': return redirect('/')
    try:
        pending_data = db.pending_updates.find_one({"_id": ObjectId(update_id)})
        if pending_data:
            customers_col.update_one(
                {"_id": ObjectId(pending_data['customer_id'])},
                {"$set": pending_data['update_data']}
            )
            db.pending_updates.delete_one({"_id": ObjectId(update_id)})
            flash("কিস্তি অনুমোদিত হয়েছে!", "success")
    except Exception as e: flash(f"Error: {e}", "danger")
    return redirect(url_for('pending_approvals'))

@app.route('/reject_kisti/<k_id>')
@login_required
def reject_kisti(k_id):
    if session.get('role') != 'admin': return redirect('/')
    db.pending_updates.delete_one({"_id": ObjectId(k_id)})
    flash("কিস্তি বাতিল করা হয়েছে।", "warning")
    return redirect(url_for('pending_approvals'))

@app.route('/bulk_approve_kisti', methods=['POST'])
@login_required
def bulk_approve_kisti():
    if session.get('role') != 'admin': return redirect('/')
    selected_ids = request.form.getlist('ids')
    count = 0
    for update_id in selected_ids:
        pending_data = db.pending_updates.find_one({"_id": ObjectId(update_id)})
        if pending_data:
            customers_col.update_one(
                {"_id": ObjectId(pending_data['customer_id'])},
                {"$set": pending_data['update_data']}
            )
            db.pending_updates.delete_one({"_id": ObjectId(update_id)})
            count += 1
    flash(f"সফলভাবে {count}টি কিস্তি অনুমোদিত!", "success")
    return redirect(url_for('pending_approvals'))

@app.route('/bulk_reject_kisti', methods=['POST'])
@login_required
def bulk_reject_kisti():
    if session.get('role') != 'admin': return redirect('/')
    selected_ids = request.form.getlist('ids')
    if selected_ids:
        db.pending_updates.delete_many({"_id": {"$in": [ObjectId(i) for i in selected_ids]}})
        flash(f"{len(selected_ids)}টি কিস্তি বাতিল করা হয়েছে।", "danger")
    return redirect(url_for('pending_approvals'))


# --- নতুন সদস্য (Customer) অনুমোদন ও বাতিল রুটস ---

@app.route('/approve_customer/<c_id>')
@login_required
def approve_customer(c_id):
    if session.get('role') == 'admin':
        customers_col.update_one({"_id": ObjectId(c_id)}, {"$set": {"status": "approved"}})
        flash("সদস্য অনুমোদিত হয়েছে!", "success")
    return redirect(url_for('pending_approvals'))

@app.route('/reject_customer/<c_id>')
@login_required
def reject_customer(c_id):
    if session.get('role') == 'admin':
        customers_col.delete_one({"_id": ObjectId(c_id)})
        flash("সদস্যের আবেদন বাতিল করা হয়েছে।", "warning")
    return redirect(url_for('pending_approvals'))

@app.route('/bulk_approve_customers', methods=['POST'])
@login_required
def bulk_approve_customers():
    if session.get('role') != 'admin': return redirect('/')
    selected_ids = request.form.getlist('ids')
    if selected_ids:
        customers_col.update_many(
            {"_id": {"$in": [ObjectId(i) for i in selected_ids]}},
            {"$set": {"status": "approved"}}
        )
        flash(f"{len(selected_ids)} জন সদস্য অনুমোদিত হয়েছে!", "success")
    return redirect(url_for('pending_approvals'))

@app.route('/bulk_reject_customers', methods=['POST'])
@login_required
def bulk_reject_customers():
    if session.get('role') != 'admin': return redirect('/')
    selected_ids = request.form.getlist('ids')
    if selected_ids:
        customers_col.delete_many({"_id": {"$in": [ObjectId(i) for i in selected_ids]}})
        flash(f"{len(selected_ids)} জন সদস্যের আবেদন বাতিল!", "danger")
    return redirect(url_for('pending_approvals'))

@app.route('/create_sheet', methods=['POST'])
def create_sheet():
    try:
        sheet_data = {
            "group_name": request.form.get("group_name"),
            "code_no": request.form.get("code_no"),
            "reg_no": request.form.get("reg_no"),
            "branch": request.form.get("branch"),
            "month": request.form.get("month"),
            "year": request.form.get("year"),
            "village": request.form.get("village"),
            "post_office": request.form.get("post_office"),
            "union": request.form.get("union"),
            "upazila": request.form.get("upazila"),
            "district": request.form.get("district"),
            "collection_day": request.form.get("collection_day"),
            "leader_name": request.form.get("leader_name")
        }
        if not sheet_data["group_name"]:
            flash("দলের নাম দেওয়া আবশ্যিক!", "warning")
            return redirect(url_for('index'))

        sheets_col.insert_one(sheet_data)
        flash("নতুন কালেকশন শীট সফলভাবে তৈরি হয়েছে।", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"শীট তৈরি করতে সমস্যা হয়েছে: {e}", "danger")
        return redirect(url_for('index'))

@app.route('/sheet/<sheet_id>')
def view_sheet(sheet_id):
    try:
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        if not sheet:
            flash("দুঃখিত, শীটটি খুঁজে পাওয়া যায়নি।", "warning")
            return redirect(url_for('index'))
            
        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        return render_template('sheet_details.html', sheet=sheet, customers=customers)
    except Exception as e:
        flash(f"শীট লোড করতে সমস্যা: {e}", "danger")
        return redirect(url_for('index'))

# --- পিডিএফ তৈরির নতুন রুট (এটি মিসিং ছিল) ---
@app.route('/download_pdf/<sheet_id>')
def download_pdf(sheet_id):
    try:
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        customers = list(customers_col.find({"sheet_id": sheet_id}))
        
        rendered = render_template('pdf_template.html', sheet=sheet, customers=customers)
        
        # wkhtmltopdf কনফিগারেশন (উইন্ডোজের জন্য পাথ প্রয়োজন হতে পারে)
        options = {
            'encoding': "UTF-8",
            'enable-local-file-access': None
        }
        
        pdf = pdfkit.from_string(rendered, False, options=options)
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={sheet["group_name"]}.pdf'
        return response
    except Exception as e:
        flash(f"পিডিএফ তৈরিতে সমস্যা: {e}", "danger")
        return redirect(url_for('view_sheet', sheet_id=sheet_id))

@app.route('/add_customer_page')
@login_required
def add_customer_page():
    try:
        user_role = session.get('role')
        user_name = session.get('user')
        
        if user_role == 'admin':
            # অ্যাডমিন সব শীট দেখতে পাবে
            all_sheets = list(sheets_col.find().sort("group_name", 1))
        else:
            # এমপ্লয়ির ডাটা রিট্রিভ করা
            user_data = users_col.find_one({"username": user_name})
            
            #assigned_sheets থেকে আইডিগুলো নেওয়া (খালি থাকলে খালি লিস্ট)
            assigned_list = user_data.get('assigned_sheets', [])
            
            if not assigned_list:
                # যদি কোনো শীট অ্যাসাইন করা না থাকে
                all_sheets = []
                flash("আপনার জন্য কোনো শীট বরাদ্দ করা হয়নি। অ্যাডমিনের সাথে যোগাযোগ করুন।", "warning")
            else:
                # স্ট্রিং আইডিগুলোকে ObjectId তে রূপান্তর করা
                assigned_ids = [ObjectId(sid) for sid in assigned_list]
                all_sheets = list(sheets_col.find({"_id": {"$in": assigned_ids}}).sort("group_name", 1))
            
        return render_template('add_customer.html', sheets=all_sheets, now=datetime.now())

    except Exception as e:
        print(f"Error loading add customer page: {e}")
        return f"পেজ লোড করতে সমস্যা হয়েছে: {e}"
    

@app.route('/save_customer', methods=['POST'])
@login_required
def save_customer():
    try:
        sheet_id = request.form.get("sheet_id")
        role = session.get('role')
        
        # ডাটা স্ট্রাকচার তৈরি
        customer_data = {
            "sheet_id": sheet_id,
            "sl_no": request.form.get("sl_no"),
            "customer_name": request.form.get("customer_name"),
            "join_date": request.form.get("join_date"),
            "acc_no": request.form.get("acc_no"),
            "product_name": request.form.get("product_name"),
            "delivery_date": request.form.get("delivery_date"),
            "total_months": int(request.form.get("total_months") or 0),
            "cost_price": float(request.form.get("cost_price") or 0),
            "profit": float(request.form.get("profit") or 0),
            "total_price": float(request.form.get("total_price") or 0),
            
            # ট্র্যাকিং তথ্য
            "added_by": session.get('user'),
            "entry_date": datetime.now(),
            "status": "approved" if role == 'admin' else "pending", # এমপ্লয়ি করলে পেন্ডিং থাকবে
            
            "collections": {
                "pre_due_n": float(request.form.get("pre_due_n") or 0),
                "pre_due_m": float(request.form.get("pre_due_m") or 0),
                "kisti_data": [], 
                "price_data": [], 
                "return_cash": 0,
                "discount": 0,
                "comment": ""
            }
        }
        
        # ডাটাবেসে ইনসার্ট
        customers_col.insert_one(customer_data)
        
        if role == 'admin':
            flash("সদস্য সফলভাবে যুক্ত হয়েছে!", "success")
        else:
            flash("সদস্য যুক্ত হয়েছে এবং অ্যাডমিনের অনুমোদনের জন্য অপেক্ষমান।", "info")
            
        return redirect(url_for('view_sheet', sheet_id=sheet_id))
        
    except Exception as e:
        flash(f"সেভ করতে সমস্যা হয়েছে: {str(e)}", "danger")
        return redirect(url_for('add_customer_page'))

@app.route('/kisti_sheets')
@login_required
def kisti_sheets_list():
    try:
        user_role = session.get('role')
        user_name = session.get('user')

        if user_role == 'admin':
            # অ্যাডমিন সব শীট দেখতে পাবে
            all_sheets = list(sheets_col.find().sort("_id", -1))
        else:
            # এমপ্লয়ির তথ্য ডাটাবেস থেকে খুঁজে বের করা
            user_data = users_col.find_one({"username": user_name})
            
            # এমপ্লয়ির সাথে যুক্ত শীট আইডিগুলোর লিস্ট (String থেকে ObjectId তে রূপান্তর)
            assigned_sheet_ids = [ObjectId(sid) for sid in user_data.get('assigned_sheets', [])]
            
            # শুধুমাত্র assigned শীটগুলো ফিল্টার করে আনা
            all_sheets = list(sheets_col.find({"_id": {"$in": assigned_sheet_ids}}).sort("_id", -1))

        return render_template('kisti_sheets_select.html', sheets=all_sheets)
        
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/kisti_sheet/<sheet_id>')
def view_kisti_sheet(sheet_id):
    try:
        # ১. শীট ডাটা নিয়ে আসা (এখানে ObjectId ই লাগবে)
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        
        if not sheet:
            flash("শীটটি পাওয়া যায়নি!", "warning")
            return redirect(url_for('kisti_sheets_list'))

        # ২. কাস্টমার ডাটা খোঁজা (String অথবা ObjectId দুই ভাবেই চেক করা হচ্ছে)
        # এটি নিশ্চিত করবে যে ডাটা যেভাবে সেভ হোক না কেন, তা লোড হবে।
        customers = list(customers_col.find({
            "$or": [
                {"sheet_id": sheet_id},           # যদি String হিসেবে থাকে
                {"sheet_id": ObjectId(sheet_id)}  # যদি ObjectId হিসেবে থাকে
            ]
        }).sort("sl_no", 1))
        
        # ৩. তারিখ চেক
        col_dates = sheet.get('manual_dates')
        if not col_dates or len(col_dates) < 5:
            col_dates = ['কিস্তি-১', 'কিস্তি-২', 'কিস্তি-৩', 'কিস্তি-৪', 'কিস্তি-৫']
        
        return render_template('kisti_sheet.html', sheet=sheet, customers=customers, col_dates=col_dates)
        
    except Exception as e:
        print(f"Error in view_kisti_sheet: {e}") # কনসোলে আসল এরর দেখার জন্য
        return redirect(url_for('kisti_sheets_list'))
    
@app.route('/set_dates/<sheet_id>', methods=['GET', 'POST'])
def set_collection_dates(sheet_id):
    try:
        # স্ট্রিং আইডিকে অবজেক্ট আইডিতে রূপান্তর
        obj_id = ObjectId(sheet_id)
        
        if request.method == 'POST':
            # ফর্ম থেকে মাসের নাম সংগ্রহ
            new_month = request.form.get('month', '').strip()
            
            # ফর্ম থেকে ৫টি তারিখ সংগ্রহ
            dates = [
                request.form.get('date1', '').strip(),
                request.form.get('date2', '').strip(),
                request.form.get('date3', '').strip(),
                request.form.get('date4', '').strip(),
                request.form.get('date5', '').strip()
            ]
            
            # ডাটাবেসে আপডেট (এখন month এবং manual_dates দুটোই আপডেট হবে)
            update_data = {
                "manual_dates": dates
            }
            
            # যদি ইউজার মাসের নাম ইনপুট দেয়, তবে সেটিও আপডেট লিস্টে যোগ হবে
            if new_month:
                update_data["month"] = new_month

            result = db.Sheets.update_one(
                {"_id": obj_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0 or result.matched_count > 0:
                flash("মাস এবং ৫টি তারিখ সফলভাবে আপডেট করা হয়েছে!", "success")
            else:
                flash("কোনো পরিবর্তন করা হয়নি বা শীটটি পাওয়া যায়নি।", "warning")
                
            return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))
        
        # GET মেথড: ডাটা লোড করা
        sheet = db.Sheets.find_one({"_id": obj_id})
        return render_template('set_dates.html', sheet=sheet)
        
    except Exception as e:
        print(f"Update Error: {e}")
        flash(f"ত্রুটি: {e}", "danger")
        return redirect(url_for('kisti_sheets_list'))

@app.route('/save_kisti/<sheet_id>', methods=['POST'])
@login_required
def save_kisti(sheet_id):
    try:
        user_role = session.get('role')
        user_name = session.get('user')
        
        # শীটের অধীনে থাকা সব কাস্টমার নিয়ে আসা
        customers = list(customers_col.find({"sheet_id": sheet_id}))
        
        all_updates = [] # এমপ্লয়িদের জন্য সব ডাটা এখানে জমা হবে

        for customer in customers:
            cid = str(customer['_id'])
            
            # ডাটা সংগ্রহের হেল্পার ফাংশন
            def get_val(f):
                v = request.form.get(f'{f}_{cid}', '0').strip()
                return float(v) if v else 0.0

            def get_text(f):
                return request.form.get(f'{f}_{cid}', '').strip()

            # ডাটা স্ট্রাকচার তৈরি (নতুন এডিটেবল কিস্তি কলাম সহ)
            kisti_data = [get_val(f'n_{i}') for i in range(1, 6)]
            price_data = [get_val(f'm_{i}') for i in range(1, 6)]
            
            update_body = {
                "join_date": get_text('join_date'), 
                "duration_months": get_text('duration'), 
                "product_name": get_text('item_name'),
                "delivery_date": get_text('dist_date'),
                "cost_price": get_val('item_price'),
                "profit": get_val('item_profit'),
                "per_kisti": get_val('per_kisti'),
                "total_kisti": int(get_val('total_kisti')), # নতুন যুক্ত করা হয়েছে
                "paid_kisti": int(get_val('paid_kisti')), # নতুন যুক্ত করা হয়েছে
                "collections": {
                    "running_kisti": int(get_val('running_kisti')),
                    "pre_due_n": get_val('pre_due_n'),
                    "pre_due_m": get_val('pre_due_m'),
                    "kisti_data": kisti_data,
                    "price_data": price_data,
                    "return_date": get_text('r_date'),
                    "return_cash": get_val('r_cash'),
                    "discount_date": get_text('discount_date'),
                    "discount": get_val('discount'),
                    "comment": get_text('comment')
                }
            }

            if user_role == 'admin':
                # অ্যাডমিন হলে সরাসরি আপডেট
                customers_col.update_one({"_id": ObjectId(cid)}, {"$set": update_body})
            else:
                # এমপ্লয়ি হলে পেন্ডিং লিস্টে রাখা
                all_updates.append({
                    "customer_id": cid,
                    "customer_name": customer.get('customer_name'),
                    "sheet_id": sheet_id,
                    "update_data": update_body,
                    "added_by": user_name,
                    "type": "sheet_update",
                    "status": "pending",
                    "entry_at": datetime.now()
                })

        if user_role == 'admin':
            flash("শীট সরাসরি আপডেট করা হয়েছে!", "success")
        else:
            if all_updates:
                # সব আপডেট একসাথে পেন্ডিং কালেকশনে সেভ করা
                db.pending_updates.insert_many(all_updates)
                flash("আপনার আপডেটগুলো অ্যাডমিন অনুমোদনের জন্য পাঠানো হয়েছে।", "info")
            else:
                flash("কোনো পরিবর্তন পাওয়া যায়নি।", "warning")
        
    except Exception as e:
        print(f"Error saving kisti: {e}")
        flash(f"তথ্য সংরক্ষণ করতে সমস্যা হয়েছে: {str(e)}", "danger")
        
    return redirect(url_for('kisti_sheets_list'))

@app.route('/print_kisti/<sheet_id>')
def print_kisti_sheet(sheet_id):
    try:
        # ১. ডাটাবেস থেকে তথ্য সংগ্রহ
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        # স্লাগ বা সিরিয়াল নম্বর অনুযায়ী সর্ট করা
        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        
        # ২. কিস্তির নাম/তারিখ সংগ্রহ
        col_dates = sheet.get('manual_dates', ['কিস্তি-১', 'কিস্তি-২', 'কিস্তি-৩', 'কিস্তি-৪', 'কিস্তি-৫'])

        # ৩. ডাটা ক্লিন করার জন্য হেল্পার ফাংশন
        def safe_num(val):
            try:
                if val is None or str(val).strip() == "" or str(val).lower() == "none":
                    return 0.0
                return float(val)
            except:
                return 0.0

        for c in customers:
            # সকল প্রয়োজনীয় ফিল্ড নিশ্চিত করা যাতে HTML এ এরর না আসে
            c['cost_price'] = safe_num(c.get('cost_price', 0))
            c['profit'] = safe_num(c.get('profit', 0))
            c['per_kisti'] = safe_num(c.get('per_kisti', 0))
            
            col = c.get('collections', {})
            if not isinstance(col, dict): col = {}
            
            # কিস্তি এবং মূল্য আদায়ের ৫টি ঘর নিশ্চিত করা
            k_list = col.get('kisti_data', [])
            p_list = col.get('price_data', [])
            col['kisti_data'] = [safe_num(x) for x in k_list]
            col['price_data'] = [safe_num(x) for x in p_list]
            
            while len(col['kisti_data']) < 5: col['kisti_data'].append(0.0)
            while len(col['price_data']) < 5: col['price_data'].append(0.0)

            col['pre_due_n'] = safe_num(col.get('pre_due_n', 0))
            col['pre_due_m'] = safe_num(col.get('pre_due_m', 0))
            col['return_cash'] = safe_num(col.get('return_cash', 0))
            col['discount'] = safe_num(col.get('discount', 0))
            
            c['collections'] = col

        return render_template('print_sheet.html', sheet=sheet, customers=customers, col_dates=col_dates)
    
    except Exception as e:
        print(f"Print Error: {e}")
        return f"প্রিন্ট করতে সমস্যা হয়েছে: {str(e)}"

from bson.objectid import ObjectId

@app.route('/delete_sheet/<string:id>')  # এখানে <string:id> দিলে ফ্ল্যাস্ক নিশ্চিত হয় এটি স্ট্রিং
def delete_sheet(id):
    try:
        # স্ট্রিং আইডি-কে অবজেক্ট আইডিতে রূপান্তর
        obj_id = ObjectId(id)
        
        # ডিলিট অপারেশন
        result = db.sheets.delete_one({'_id': obj_id})
        
        if result.deleted_count > 0:
            print(f"Successfully deleted ID: {id}")
        else:
            print(f"No document found with ID: {id}")
            
    except Exception as e:
        print(f"Error occurred during delete: {e}")
        
    return redirect(url_for('index')) # আপনার প্রধান পেজের ফাংশন নাম দিন

@app.route('/manage_customers_page')
def manage_customers_page():
    try:
        # সব কাস্টমারকে নিয়ে আসা
        customers = list(customers_col.find().sort("customer_name", 1))
        
        for c in customers:
            # ডাটাবেস থেকে আসা ভ্যালুগুলোকে নিরাপদভাবে সংখ্যায় রূপান্তর (Safe Conversion)
            # যদি ভ্যালু না থাকে বা স্ট্রিং হয়, তবে সেটি ০.০ হয়ে যাবে
            try:
                c['cost_price'] = float(c.get('cost_price') or 0)
                c['profit'] = float(c.get('profit') or 0)
                c['per_kisti'] = float(c.get('per_kisti') or 0)
            except (ValueError, TypeError):
                c['cost_price'] = 0.0
                c['profit'] = 0.0
                c['per_kisti'] = 0.0
                
        return render_template('manage_customers.html', customers=customers)
    
    except Exception as e:
        print(f"Error: {e}")
        return "Internal Server Error", 500

# কাস্টমার ডিলিট করার রাউট
@app.route('/delete_customer_direct/<cust_id>')
def delete_customer_direct(cust_id):
    customers_col.delete_one({"_id": ObjectId(cust_id)})
    flash("গ্রাহক সফলভাবে মুছে ফেলা হয়েছে", "warning")
    return redirect(url_for('manage_customers_page'))

# --- ১. এডিট পেজ ভিউ (Edit Customer Page) ---
@app.route('/edit_customer/<cust_id>')
def edit_customer(cust_id):
    try:
        customer = customers_col.find_one({"_id": ObjectId(cust_id)})
        all_sheets = list(sheets_col.find({}, {"group_name": 1}))
        
        if customer:
            # ডিফল্ট ভ্যালু সেট করা যাতে টেমপ্লেটে এরর না আসে
            customer['cost_price'] = customer.get('cost_price', 0)
            customer['profit'] = customer.get('profit', 0)
            customer['per_kisti'] = customer.get('per_kisti', 0)
            customer['extra_products'] = customer.get('extra_products', [])
            
            return render_template('edit_customer.html', c=customer, all_sheets=all_sheets)
        
        flash("গ্রাহক খুঁজে পাওয়া যায়নি!", "danger")
        return redirect(url_for('manage_customers_page'))
            
    except Exception as e:
        flash("ভুল আইডি বা ডাটাবেস ত্রুটি!", "danger")
        return redirect(url_for('manage_customers_page'))


# --- ২. কাস্টমার তথ্য ও নতুন এক্সট্রা পণ্য আপডেট (Update Customer) ---
@app.route('/update_customer/<cust_id>', methods=['POST'])
def update_customer(cust_id):
    try:
        sheet_id = request.form.get('sheet_id')
        name = request.form.get('name')
        acc_no = request.form.get('acc_no')
        
        update_data = {
            "$set": {
                "customer_name": name,
                "acc_no": acc_no,
                "sheet_id": sheet_id
            }
        }

        # নতুন এক্সট্রা পণ্য যোগ করার লজিক
        new_p_name = request.form.get('new_product')
        if new_p_name:
            new_entry = {
                "p_id": str(uuid.uuid4())[:8], # ডিলিট করার সুবিধার জন্য ইউনিক আইডি
                "p_name": new_p_name,
                "p_price": float(request.form.get('new_price') or 0),
                "p_profit": float(request.form.get('new_profit') or 0),
                "p_kisti": float(request.form.get('new_per_kisti') or 0),
                "added_date": request.form.get('new_date') or datetime.now().strftime("%Y-%m-%d")
            }
            update_data["$push"] = {"extra_products": new_entry}

        customers_col.update_one({"_id": ObjectId(cust_id)}, update_data)
        
        flash("তথ্য সফলভাবে আপডেট করা হয়েছে!", "success")
        return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id) if sheet_id else url_for('manage_customers_page'))

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('manage_customers_page'))


# --- ৩. এক্সট্রা পণ্য ডিলিট (Delete Extra Product) ---
@app.route('/delete_extra_product/<cust_id>/<p_id>', methods=['POST'])
def delete_extra_product(cust_id, p_id):
    try:
        # $pull ব্যবহার করে এরের (Array) ভেতর থেকে নির্দিষ্ট p_id ওয়ালা অবজেক্ট ফেলে দেওয়া
        result = customers_col.update_one(
            {"_id": ObjectId(cust_id)},
            {"$pull": {"extra_products": {"p_id": p_id}}}
        )
        if result.modified_count > 0:
            return {"status": "success", "message": "পণ্যটি ডিলিট হয়েছে"}, 200
        return {"status": "error", "message": "পণ্যটি পাওয়া যায়নি"}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


# --- ৪. মূল পণ্য রিসেট/ডিলিট (Delete/Reset Main Product) ---
@app.route('/delete_main_product/<cust_id>', methods=['POST'])
def delete_main_product(cust_id):
    try:
        # মূল পণ্যের ফিল্ডগুলোকে জিরো বা খালি করে দেওয়া
        customers_col.update_one(
            {"_id": ObjectId(cust_id)},
            {"$set": {
                "product_name": "",
                "cost_price": 0,
                "profit": 0,
                "delivery_date": "",
                "per_kisti": 0,
                "total_kisti": 0,
                "paid_kisti": 0
            }}
        )
        return {"status": "success", "message": "মূল পণ্যটি রিমুভ হয়েছে"}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/sheet_data')
def sheet_data():
    try:
        # ১. সঠিক কালেকশন থেকে সব শীট নিয়ে আসা (বড় হাতের Sheets_col ব্যবহার করে)
        all_sheets = list(sheets_col.find({}))
        summary_list = []

        for sheet in all_sheets:
            sheet_id_str = str(sheet['_id'])
            
            # ২. কাস্টমার কালেকশন থেকে এই শীটের সকল মেম্বার খুঁজে বের করা
            # আপনার কোড অনুযায়ী sheet_id এখানে স্ট্রিং হিসেবে সেভ হয়
            customers = list(customers_col.find({"sheet_id": sheet_id_str}))
            
            # মেম্বার না থাকলে এই শীটটি সামারিতে দেখানোর দরকার নেই অথবা ০ দেখাবে
            t_val, t_cash, t_rem_n, t_rem_m = 0, 0, 0, 0
            
            for c in customers:
                try:
                    # সংখ্যায় রূপান্তর (নিরাপদভাবে)
                    cost = float(c.get('cost_price') or 0)
                    profit = float(c.get('profit') or 0)
                    total_val = cost + profit
                    
                    col = c.get('collections', {})
                    k_list = [float(x or 0) for x in col.get('kisti_data', [])]
                    p_list = [float(x or 0) for x in col.get('price_data', [])]
                    
                    k_sum = sum(k_list)
                    p_sum = sum(p_list)
                    
                    # অফিস ক্যালকুলেশন লজিক
                    pre_n = float(col.get('pre_due_n') or 0)
                    ret_cash = float(col.get('return_cash') or 0)
                    rem_n = pre_n - (k_sum - ret_cash)
                    
                    pre_m = float(col.get('pre_due_m') or 0)
                    discount = float(col.get('discount') or 0)
                    rem_m = (pre_m + total_val) - (p_sum + discount)
                    
                    t_val += total_val
                    t_cash += k_sum
                    t_rem_n += rem_n
                    t_rem_m += rem_m
                except Exception as e:
                    print(f"Error in customer {c.get('customer_name')}: {e}")
                    continue

            summary_list.append({
                'group_name': sheet.get('group_name', 'Unnamed Group'),
                'code_no': sheet.get('code_no', 'N/A'),
                'member_count': len(customers),
                'total_value': t_val,
                'collected_cash': t_cash,
                'pending_cash': t_rem_n,
                'pending_product_val': t_rem_m,
                'sheet_id': sheet_id_str
            })

        return render_template('sheet_data.html', summary=summary_list)
    
    except Exception as e:
        print(f"Detailed Error: {e}")
        return f"ডাটাবেস কানেকশন বা কুয়েরি ত্রুটি: {str(e)}"

@app.route('/print_summary')
def print_summary():
    try:
        all_sheets = list(sheets_col.find({}))
        summary_list = []
        for sheet in all_sheets:
            sheet_id_str = str(sheet['_id'])
            customers = list(customers_col.find({"sheet_id": sheet_id_str}))
            
            t_val, t_cash, t_rem_n, t_rem_m = 0, 0, 0, 0
            for c in customers:
                cost = float(c.get('cost_price') or 0)
                profit = float(c.get('profit') or 0)
                total_val = cost + profit
                col = c.get('collections', {})
                k_sum = sum([float(x or 0) for x in col.get('kisti_data', [])])
                p_sum = sum([float(x or 0) for x in col.get('price_data', [])])
                
                rem_n = float(col.get('pre_due_n') or 0) - (k_sum - float(col.get('return_cash') or 0))
                rem_m = (float(col.get('pre_due_m') or 0) + total_val) - (p_sum + float(col.get('discount') or 0))
                
                t_val += total_val
                t_cash += k_sum
                t_rem_n += rem_n
                t_rem_m += rem_m

            summary_list.append({
                'group_name': sheet.get('group_name', 'Unnamed Group'),
                'code_no': sheet.get('code_no', 'N/A'),
                'member_count': len(customers),
                'total_value': t_val,
                'collected_cash': t_cash,
                'pending_cash': t_rem_n,
                'pending_product_val': t_rem_m
            })

        return render_template('print_summary_final.html', summary=summary_list, now=datetime.now())
    except Exception as e:
        return f"Error: {str(e)}"


from bson import ObjectId  # এটি ফাইলের উপরে ইম্পোর্ট করা থাকতে হবে

@app.route('/update_sheet/<id>', methods=['POST'])
@login_required
def update_sheet(id):
    try:
        # স্ট্রিং আইডি-কে ObjectId তে রূপান্তর করা হচ্ছে
        query_id = ObjectId(id) if ObjectId.is_valid(id) else id
        
        updated_data = {
            "group_name": request.form.get('group_name'),
            "code_no": request.form.get('code_no'),
            "reg_no": request.form.get('reg_no'),
            "branch": request.form.get('branch'),
            "month": request.form.get('month'),
            "year": request.form.get('year'),
            "village": request.form.get('village'),
            "post_office": request.form.get('post_office'),
            "union": request.form.get('union'),
            "upazila": request.form.get('upazila'),
            "district": request.form.get('district'),
            "collection_day": request.form.get('collection_day'),
            "leader_name": request.form.get('leader_name')
        }

        result = db.sheets.update_one({"_id": query_id}, {"$set": updated_data})

        if result.matched_count > 0:
            flash('তথ্য সফলভাবে আপডেট করা হয়েছে!', 'success')
        else:
            flash('শীটটি খুঁজে পাওয়া যায়নি (ID Mismatch)।', 'danger') # এখানে সমস্যা হচ্ছিল
            
    except Exception as e:
        flash(f'ত্রুটি: {str(e)}', 'danger')
        
    return redirect(url_for('index'))

@app.route('/print-docs')
@login_required
def print_docs():
    # এখানে পিডিএফ ফাইলের নামগুলো লিস্ট আকারে পাঠাতে পারেন অথবা সরাসরি HTML এ লিখতে পারেন
    return render_template('print_docs.html')

@app.errorhandler(404)
def page_not_found(e):
    return "404 - পেজটি খুঁজে পাওয়া যায়নি", 404

if __name__ == '__main__':
    create_default_admin() # এই লাইনটি যোগ করা হয়েছে
    app.run(debug=True)
