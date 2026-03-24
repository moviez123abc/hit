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
        customer_data = {
            "sheet_id": request.form.get("sheet_id"),
            "sl_no": request.form.get("sl_no"),
            "customer_name": request.form.get("customer_name"),
            "join_date": request.form.get("join_date"),
            "acc_no": request.form.get("acc_no"),
            "product_name": request.form.get("product_name"),
            "delivery_date": request.form.get("delivery_date"),
            "unit_price": request.form.get("unit_price"),
            "cost_price": request.form.get("cost_price"),
            "profit": request.form.get("profit"),
            "total_price": request.form.get("total_price")
        }
        
        customers_col.insert_one(customer_data)
        flash("সদস্য সফলভাবে যুক্ত হয়েছে!", "success")
        return redirect(url_for('view_sheet', sheet_id=customer_data["sheet_id"]))
    except Exception as e:
        flash(f"সেভ করতে সমস্যা হয়েছে: {e}", "danger")
        return redirect(url_for('add_customer_page'))

@app.route('/kisti_sheets')
def kisti_sheets_list():
    # সব শিট দেখানোর লজিক
    all_sheets = list(sheets_col.find().sort("_id", -1))
    return render_template('kisti_sheets_select.html', sheets=all_sheets)

@app.route('/kisti_sheet/<sheet_id>')
def view_kisti_sheet(sheet_id):
    try:
        # ১. শিট এবং কাস্টমার ডাটা নিয়ে আসা
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        
        if not sheet:
            flash("শিটটি পাওয়া যায়নি!", "warning")
            return redirect(url_for('kisti_sheets_list'))

        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        
        # ২. ডাটাবেস থেকে manual_dates নিন। 
        # যদি ৫টি তারিখ না থাকে, তবে ৫টি ডিফল্ট নাম দিয়ে লিস্টটি পূর্ণ করুন।
        col_dates = sheet.get('manual_dates')
        
        if not col_dates or len(col_dates) < 5:
            col_dates = ['কিস্তি-১', 'কিস্তি-২', 'কিস্তি-৩', 'কিস্তি-৪', 'কিস্তি-৫']
        
        return render_template('kisti_sheet.html', sheet=sheet, customers=customers, col_dates=col_dates)
        
    except Exception as e:
        flash(f"শিট লোড করতে সমস্যা: {e}", "danger")
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
        # sheet_id এর আন্ডারে থাকা সব কাস্টমার খুঁজে বের করা
        customers = list(customers_col.find({"sheet_id": sheet_id}))
        
        for customer in customers:
            cid = str(customer['_id'])
            
            # কিস্তি ডাটা সংগ্রহ (১ থেকে ৫ নম্বর কিস্তি)
            # HTML-এ n_1, n_2... এবং m_1, m_2... নামে ইনপুট আছে
            kisti_data = [float(request.form.get(f'n_{i}_{cid}', 0) or 0) for i in range(1, 6)]
            price_data = [float(request.form.get(f'm_{i}_{cid}', 0) or 0) for i in range(1, 6)]
            
            # কাস্টমার ইনফো এবং কালেকশন আপডেট
            customers_col.update_one({"_id": ObjectId(cid)}, {"$set": {
                "member_no": request.form.get(f'member_no_{cid}'),
                "product_name": request.form.get(f'item_name_{cid}'),
                "dist_date": request.form.get(f'dist_date_{cid}'),
                "price": float(request.form.get(f'item_price_{cid}', 0) or 0),
                "profit": float(request.form.get(f'item_profit_{cid}', 0) or 0),
                "per_kisti": float(request.form.get(f'per_kisti_{cid}', 0) or 0),
                
                "collections": {
                    "pre_due_n": float(request.form.get(f'pre_due_n_{cid}', 0) or 0),
                    "pre_due_m": float(request.form.get(f'pre_due_m_{cid}', 0) or 0),
                    "kisti_data": kisti_data,
                    "price_data": price_data,
                    "return_date": request.form.get(f'r_date_{cid}'),
                    "return_cash": float(request.form.get(f'r_cash_{cid}', 0) or 0),
                    "discount": float(request.form.get(f'discount_{cid}', 0) or 0),
                    
                    # নতুন যোগ করা হয়েছে: মূল্য ছাড় তারিখ
                    "discount_date": request.form.get(f'discount_date_{cid}'), 
                    
                    "comment": request.form.get(f'comment_{cid}')
                }
            }})
        
        flash("কিস্তি শিট সফলভাবে আপডেট করা হয়েছে!", "success")
    except Exception as e:
        print(f"Error saving kisti: {e}")
        flash("তথ্য সংরক্ষণ করতে সমস্যা হয়েছে। অনুগ্রহ করে ইনপুটগুলো চেক করুন।", "danger")
        
    return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))

@app.route('/print_kisti/<sheet_id>')
def print_kisti_sheet(sheet_id):
    try:
        sheet = sheets_col.find_one({"_id": ObjectId(sheet_id)})
        customers = list(customers_col.find({"sheet_id": sheet_id}).sort("sl_no", 1))
        col_dates = sheet.get('manual_dates', ['কিস্তি-১', 'কিস্তি-২', 'কিস্তি-৩', 'কিস্তি-৪'])

        # ডাটা ক্লিনজিং ফাংশন
        def to_num(val):
            try:
                return float(val) if val else 0.0
            except:
                return 0.0

        # প্রতিটি কাস্টমারের ডাটা লুপ করে সংখ্যায় রূপান্তর
        for c in customers:
            if 'collections' in c:
                col = c['collections']
                # কিস্তি এবং মূল্য ডাটা ক্লিন করা
                col['kisti_data'] = [to_num(x) for x in col.get('kisti_data', [0,0,0,0,0])]
                col['price_data'] = [to_num(x) for x in col.get('price_data', [0,0,0,0,0])]
                # বাকি ফিল্ডগুলোও ক্লিন করা
                col['pre_due'] = to_num(col.get('pre_due'))
                col['return_cash'] = to_num(col.get('return_cash'))
                col['discount'] = to_num(col.get('discount'))

        return render_template('print_sheet.html', sheet=sheet, customers=customers, col_dates=col_dates)
    except Exception as e:
        print(f"Print Error: {e}")
        flash(f"প্রিন্ট করতে সমস্যা: {e}", "danger")
        return redirect(url_for('view_kisti_sheet', sheet_id=sheet_id))

from bson.objectid import ObjectId # নিশ্চিত করুন এটি একদম উপরে আছে

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

@app.errorhandler(404)
def page_not_found(e):
    return "404 - পেজটি খুঁজে পাওয়া যায়নি", 404

if __name__ == '__main__':
    app.run(debug=True)
