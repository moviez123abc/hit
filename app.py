from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import pdfkit 
from datetime import datetime

app = Flask(__name__)
app.secret_key = "hit_secret_key_123"

# --- MongoDB Configuration ---
MONGO_URI = "mongodb+srv://texlablog_db_user:1buBUXPsE1CBo1Re@testforcustomers.mlm5xxn.mongodb.net"
client = MongoClient(MONGO_URI)
db = client['HIT_Database']
sheets_col = db['Sheets']
customers_col = db['Customers']

# --- Routes ---

@app.route('/')
def index():
    try:
        all_sheets = list(sheets_col.find().sort("_id", -1))
        return render_template('index.html', sheets=all_sheets)
    except Exception as e:
        flash(f"ডাটাবেস কানেকশনে সমস্যা: {e}", "danger")
        return render_template('index.html', sheets=[])

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
        flash("নতুন কালেকশন শিট সফলভাবে তৈরি হয়েছে।", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"শিট তৈরি করতে সমস্যা হয়েছে: {e}", "danger")
        return redirect(url_for('index'))

@app.route('/sheet/<sheet_id>')
def view_sheet(sheet_id):
    try:
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        if not sheet:
            flash("দুঃখিত, শিটটি খুঁজে পাওয়া যায়নি।", "warning")
            return redirect(url_for('index'))
            
        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        return render_template('sheet_details.html', sheet=sheet, customers=customers)
    except Exception as e:
        flash(f"শিট লোড করতে সমস্যা: {e}", "danger")
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
def add_customer_page():
    try:
        all_sheets = list(sheets_col.find())
        return render_template('add_customer.html', sheets=all_sheets)
    except Exception as e:
        return f"Error: {e}"

@app.route('/save_customer', methods=['POST'])
def save_customer():
    try:
        # ফর্ম থেকে ডাটা সংগ্রহ
        sheet_id = request.form.get("sheet_id")
        
        # ক্যালকুলেশনের সুবিধার্থে নাম্বার ফিল্ডগুলোকে float/int এ রূপান্তর
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
            
            # কালেকশন শিটের জন্য ইনিশিয়াল ডাটা স্ট্রাকচার (Nested Collections)
            "collections": {
                "pre_due_n": float(request.form.get("pre_due_n") or 0),
                "pre_due_m": float(request.form.get("pre_due_m") or 0),
                "kisti_data": [], # কিস্তি আদায়ের লিস্ট
                "price_data": [], # মূল্য আদায়ের লিস্ট
                "return_cash": 0,
                "discount": 0,
                "comment": ""
            }
        }
        
        # ডাটাবেসে ইনসার্ট
        customers_col.insert_one(customer_data)
        
        flash("সদস্য সফলভাবে যুক্ত হয়েছে!", "success")
        return redirect(url_for('view_sheet', sheet_id=sheet_id))
        
    except Exception as e:
        flash(f"সেভ করতে সমস্যা হয়েছে: {str(e)}", "danger")
        return redirect(url_for('add_customer_page')) # আপনার অ্যাড কাস্টমার পেজ ফাংশনের নাম দিন

@app.route('/kisti_sheets')
def kisti_sheets_list():
    # সব শিট দেখানোর লজিক
    all_sheets = list(sheets_col.find().sort("_id", -1))
    return render_template('kisti_sheets_select.html', sheets=all_sheets)

@app.route('/kisti_sheet/<sheet_id>')
def view_kisti_sheet(sheet_id):
    try:
        # ১. শিট ডাটা নিয়ে আসা (এখানে ObjectId ই লাগবে)
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        
        if not sheet:
            flash("শিটটি পাওয়া যায়নি!", "warning")
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
        flash(f"শিট লোড করতে সমস্যা হয়েছে!", "danger")
        return redirect(url_for('kisti_sheets_list'))
    
@app.route('/set_dates/<sheet_id>', methods=['GET', 'POST'])
def set_collection_dates(sheet_id):
    try:
        # স্ট্রিং আইডিকে অবজেক্ট আইডিতে রূপান্তর
        obj_id = ObjectId(sheet_id)
        
        if request.method == 'POST':
            # ফর্ম থেকে ৫টি তারিখ সংগ্রহ
            dates = [
                request.form.get('date1', '').strip(),
                request.form.get('date2', '').strip(),
                request.form.get('date3', '').strip(),
                request.form.get('date4', '').strip(),
                request.form.get('date5', '').strip()
            ]
            
            # ডাটাবেসে সরাসরি আপডেট (Sheets কালেকশনে)
            result = db.Sheets.update_one(
                {"_id": obj_id},
                {"$set": {"manual_dates": dates}}
            )
            
            if result.modified_count > 0 or result.matched_count > 0:
                flash("৫টি তারিখ সফলভাবে আপডেট করা হয়েছে!", "success")
            else:
                flash("কোনো পরিবর্তন করা হয়নি বা শিটটি পাওয়া যায়নি।", "warning")
                
            return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))
        
        # GET মেথড: ডাটা লোড করা
        sheet = db.Sheets.find_one({"_id": obj_id})
        return render_template('set_dates.html', sheet=sheet)
        
    except Exception as e:
        print(f"Update Error: {e}")
        flash(f"ত্রুটি: {e}", "danger")
        return redirect(url_for('kisti_sheets_list'))

@app.route('/save_kisti/<sheet_id>', methods=['POST'])
def save_kisti(sheet_id):
    try:
        # ১. শিটের অধীনে থাকা সকল কাস্টমার ডাটাবেস থেকে নিয়ে আসা
        # Note: customers_col আপনার কাস্টমার কালেকশনের নাম হতে হবে
        customers = list(customers_col.find({"sheet_id": sheet_id}))
        
        for customer in customers:
            cid = str(customer['_id'])
            
            # হেল্পার ফাংশন ১: ইনপুট থেকে সংখ্যা নেওয়া (ফ্লোট বা ইন্টিজার)
            def get_val(field_name):
                val = request.form.get(f'{field_name}_{cid}', '0').strip()
                try:
                    return float(val) if val else 0.0
                except ValueError:
                    return 0.0

            # হেল্পার ফাংশন ২: ইনপুট থেকে তারিখ বা টেক্সট নেওয়া
            def get_text(field_name):
                return request.form.get(f'{field_name}_{cid}', '').strip()

            # কিস্তি ও মূল্য আদায়ের লিস্ট তৈরি (১ থেকে ৫ পর্যন্ত)
            kisti_data = [get_val(f'n_{i}') for i in range(1, 6)]
            price_data = [get_val(f'm_{i}') for i in range(1, 6)]
            
            # ২. ডাটাবেসে আপডেট করার জন্য ডিকশনারি তৈরি
            update_data = {
                "join_date": get_text('join_date'), 
                "duration_months": get_text('duration'), 
                "product_name": get_text('item_name'),
                "delivery_date": get_text('dist_date'),
                "cost_price": get_val('item_price'),
                "profit": get_val('item_profit'),
                "per_kisti": get_val('per_kisti'),
                
                "collections": {
                    "pre_due_n": get_val('pre_due_n'),
                    "pre_due_m": get_val('pre_due_m'),
                    "kisti_data": kisti_data,
                    "price_data": price_data,
                    "return_date": get_text('r_date'),      # নগদ ফেরতের তারিখ
                    "return_cash": get_val('r_cash'),      # নগদ ফেরত টাকা
                    "discount_date": get_text('discount_date'), # মূল্য ছাড়ের তারিখ
                    "discount": get_val('discount'),       # ছাড়ের পরিমাণ
                    "comment": get_text('comment')         # ভর্তি/ফরম/বিবিধ
                }
            }

            # ৩. ডাটা আপডেট করা
            customers_col.update_one(
                {"_id": ObjectId(cid)}, 
                {"$set": update_data}
            )
        
        flash("কিস্তি শিট সফলভাবে আপডেট করা হয়েছে!", "success")
        
    except Exception as e:
        print(f"Error saving kisti: {e}")
        flash(f"তথ্য সংরক্ষণ করতে সমস্যা হয়েছে: {str(e)}", "danger")
        
    return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))

@app.route('/print_kisti/<sheet_id>')
def print_kisti_sheet(sheet_id):
    try:
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        col_dates = sheet.get('manual_dates', ['কিস্তি-১', 'কিস্তি-২', 'কিস্তি-৩', 'কিস্তি-৪', 'কিস্তি-৫'])

        # ডাটা টাইপ এরর দূর করার জন্য এই ফাংশনটি সবচেয়ে গুরুত্বপূর্ণ
        def safe_num(val):
            try:
                if val is None or str(val).strip() == "" or str(val).lower() == "none":
                    return 0.0
                return float(val)
            except:
                return 0.0

        for c in customers:
            # কাস্টমারের বেসিক ডাটা ক্লিন করা (String to Float)
            c['cost_price'] = safe_num(c.get('cost_price', 0))
            c['profit'] = safe_num(c.get('profit', 0))
            c['per_kisti'] = safe_num(c.get('per_kisti', 0))
            
            # কালেকশন ডাটা চেক
            col = c.get('collections', {})
            if not isinstance(col, dict): col = {}
            
            # কিস্তি এবং মূল্য ডাটা ক্লিন করা
            k_list = col.get('kisti_data', [])
            p_list = col.get('price_data', [])
            
            col['kisti_data'] = [safe_num(x) for x in k_list]
            col['price_data'] = [safe_num(x) for x in p_list]
            
            # নিশ্চিত করা যেন অন্তত ৫টি কিস্তি থাকে
            while len(col['kisti_data']) < 5: col['kisti_data'].append(0.0)
            while len(col['price_data']) < 5: col['price_data'].append(0.0)

            # অন্যান্য ফিল্ড ক্লিন করা
            col['pre_due_n'] = safe_num(col.get('pre_due_n', 0))
            col['pre_due_m'] = safe_num(col.get('pre_due_m', 0))
            col['return_cash'] = safe_num(col.get('return_cash', 0))
            col['discount'] = safe_num(col.get('discount', 0))
            
            # যোগফল বের করা (সবই এখন float, তাই concatenate এরর আসবে না)
            col['total_n'] = sum(col['kisti_data'])
            col['total_m'] = sum(col['price_data'])
            
            # কাস্টমার অবজেক্টে আবার কালেকশন সেট করা
            c['collections'] = col

        return render_template('print_sheet.html', sheet=sheet, customers=customers, col_dates=col_dates)
    
    except Exception as e:
        print(f"Error: {e}")
        return f"প্রিন্টে সমস্যা হয়েছে: {str(e)}"

@app.route('/delete_sheet/<id>')
def delete_sheet(id):
    try:
        # আইডিটি কি অবজেক্ট আইডি নাকি সাধারণ স্ট্রিং তা চেক করা
        if ObjectId.is_valid(id):
            query = {"_id": ObjectId(id)}
        else:
            query = {"_id": id}

        # ১. শিটটি ডিলিট করার চেষ্টা করা
        result = db.sheets.delete_one(query)
        
        if result.deleted_count > 0:
            # ২. ওই শিটের সাথে যুক্ত সকল কাস্টমার ডাটা ডিলিট করা
            # এখানে 'sheet_id' স্ট্রিং বা অবজেক্ট আইডি যাই হোক, এটি সব মুছে ফেলবে
            db.customers.delete_many({
                "$or": [
                    {"sheet_id": id},
                    {"sheet_id": ObjectId(id) if ObjectId.is_valid(id) else None}
                ]
            })
            
            flash('শিটটি সফলভাবে মুছে ফেলা হয়েছে!', 'success')
        else:
            # ডিবাগ করার জন্য টার্মিনালে আইডিটি প্রিন্ট করুন
            print(f"Delete failed! ID was: {id}")
            flash('দুঃখিত, ডাটাবেসে এই শিটটি খুঁজে পাওয়া যায়নি।', 'warning')
            
    except Exception as e:
        print(f"Error occurred: {e}")
        flash('কারিগরি ত্রুটির কারণে ডিলিট করা সম্ভব হয়নি।', 'danger')
        
    return redirect(url_for('index'))

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

# ১. এডিট পেজ দেখানোর রাউট (GET)
@app.route('/edit_customer/<cust_id>')
def edit_customer(cust_id):
    try:
        # ObjectId কনভার্ট করার সময় চেক করা ভালো
        customer = customers_col.find_one({"_id": ObjectId(cust_id)})
        all_sheets = list(sheets_col.find({}, {"group_name": 1}))
        
        if customer:
            # ডাটাবেসে কোনো ফিল্ড না থাকলে ডিফল্ট ০ করে দেওয়া (TypeError এড়াতে)
            customer['cost_price'] = customer.get('cost_price', 0)
            customer['profit'] = customer.get('profit', 0)
            customer['per_kisti'] = customer.get('per_kisti', 0)
            
            return render_template('edit_customer.html', c=customer, all_sheets=all_sheets)
        else:
            flash("গ্রাহক খুঁজে পাওয়া যায়নি!", "danger")
            return redirect(url_for('manage_customers_page'))
            
    except Exception as e:
        # আইডি যদি ভুল ফরম্যাটের হয় (invalid ObjectId), তবে এটি হ্যান্ডেল করবে
        flash("ভুল আইডি বা ডাটাবেস ত্রুটি!", "danger")
        print(f"Error: {e}") 
        return redirect(url_for('manage_customers_page'))


@app.route('/update_customer/<cust_id>', methods=['POST'])
def update_customer(cust_id):
    try:
        # ফর্ম থেকে ডাটা নেওয়া
        name = request.form.get('name')
        acc_no = request.form.get('acc_no')
        sheet_id = request.form.get('sheet_id') # এখান থেকে শিট আইডি আসছে

        # যদি কোনো কারণে ফর্ম থেকে sheet_id না আসে, 
        # তবে ডাটাবেস থেকে বর্তমান আইডিটি ধরে রাখা ভালো
        if not sheet_id:
            current_data = customers_col.find_one({"_id": ObjectId(cust_id)})
            sheet_id = current_data.get('sheet_id')

        update_fields = {
            "customer_name": name,
            "acc_no": acc_no,
            "sheet_id": sheet_id, # এটি নিশ্চিত করবে আইডিটি ডিলিট হবে না
            "product_name": request.form.get('product'),
            "cost_price": float(request.form.get('price') or 0),
            "profit": float(request.form.get('profit') or 0),
            "per_kisti": float(request.form.get('per_kisti') or 0)
        }

        customers_col.update_one(
            {"_id": ObjectId(cust_id)},
            {"$set": update_fields}
        )
        
        flash("তথ্য আপডেট হয়েছে!", "success")
        return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))

    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for('manage_customers_page'))

@app.errorhandler(404)
def page_not_found(e):
    return "404 - পেজটি খুঁজে পাওয়া যায়নি", 404

if __name__ == '__main__':
    app.run(debug=True)