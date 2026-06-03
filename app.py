import pandas as pd
from flask import Flask, render_template, request, redirect, url_for,abort,send_file,jsonify
from flask_sqlalchemy import SQLAlchemy # 1. 記得匯入這個
import os
from datetime import datetime 
import io 
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 2. 設定資料庫檔案的路徑
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'charity.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# 建立上傳資料夾的路徑設定
app.config['UPLOAD_FOLDER'] = 'static/uploads'
# 自動建立資料夾（如果不存在的話），避免程式找不到地方存檔而報錯
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 3. 初始化 db 物件 (這就是為什麼之前會報錯，因為沒這行)
db = SQLAlchemy(app)

# 4. 定義資料表模型
class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    donor_name = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(10), nullable=False) 
    # 新增這行：記錄地址
    address = db.Column(db.String(200), nullable=False)
    # 新增這行：記錄聯絡電話
    phone = db.Column(db.String(20), nullable=False)
    # 新增這行：記錄照片的檔名 (允許空白)
    image_filename = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)

class RequestItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False) # 需要什麼物資
    quantity = db.Column(db.Integer, nullable=False)      # 需要多少
    requester_name = db.Column(db.String(100), nullable=False) # 申請單位/人
    
    # 對應你的演算法變數：
    address = db.Column(db.String(50), nullable=False)    # 據點位置 (用來算 Distance)
    urgency = db.Column(db.Integer, nullable=False)       # 急迫性 1~5 分 (用來算 Urgency_Level)
    timestamp = db.Column(db.DateTime, default=datetime.now) # 申請時間 (用來算 Duration_Of_Waiting)
    
    # 紀錄是否已經被滿足 (預設為 False 代表還在等)
    is_fulfilled = db.Column(db.Boolean, default=False)

# 5. 在程式第一次執行時建立資料庫檔案
with app.app_context():
    db.create_all()

@app.route('/donations')
def list_donations():
    # 1. 取得參數
    search_query = request.args.get('q', '')
    sort_type = request.args.get('sort', 'timestamp')
    
    # 2. 先建立一個基礎查詢 (Base Query)
    query = Donation.query
    
    # 3. 如果有搜尋關鍵字，先進行過濾
    if search_query:
        query = query.filter(
            (Donation.donor_name.contains(search_query)) | 
            (Donation.item_name.contains(search_query))
            (Donation.address.contains(search_query))
        )
    
    # 4. 再進行排序 (這時候 query 已經被過濾過了)
    if sort_type == 'name':
        items = query.order_by(Donation.donor_name).all()
    elif sort_type == 'item':
        items = query.order_by(Donation.item_name).all()
    else:
        items = query.order_by(Donation.timestamp.desc()).all()
        
    return render_template('donations.html', items=items, query=search_query, sort=sort_type)

@app.route('/')
def home():
    # 計算目前總共有幾筆捐贈
    count = Donation.query.count()
    return render_template('index.html', total_donations=count)

@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if request.method == 'POST':
        item = request.form.get('item_name')
        if item == '其他':
            item = request.form.get('other_item')
            
        # 新增：處理照片上傳的邏輯 
        photo = request.files.get('photo')
        filename = None # 預設為沒有照片
        if photo and photo.filename != '':
            # 過濾檔名確保安全
            filename = secure_filename(photo.filename)
            # 存檔到 static/uploads/ 裡面
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_item = Donation(
            item_name=item,
            quantity=request.form.get('quantity'),
            donor_name=request.form.get('donor_name'),
            # 新增這行：抓取表單中的 condition 數值
            condition=request.form.get('condition'),
            # 新增這行：抓取表單中的地址資料
            address=request.form.get('address'),
            # 新增這行：抓取表單中的電話資料
            phone=request.form.get('phone')
            )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('list_donations')) # 或 redirect(url_for('home'))
        
    return render_template('donate.html')

@app.route('/delete/<int:id>')
def delete_item(id):
    # 獲取密碼以維持權限
    pwd = request.args.get('password')
    
    # 根據 ID 找到資料並刪除
    item_to_delete = Donation.query.get_or_404(id)
    db.session.delete(item_to_delete)
    db.session.commit()
    
    # 刪除後跳回管理頁面，並帶上密碼參數
    return redirect(url_for('admin_panel', password=pwd))


@app.route('/admin', methods=['GET'])
def admin_panel():
    # 1. 檢查密碼 (保留你的安全機制)
    if request.args.get('password') != '1234':
        return "密碼錯誤，拒絕存取！"
    
    # 2. 獲取排序參數 (保留你的排序功能)
    sort_type = request.args.get('sort', 'timestamp')
    
    # 3. 根據參數決定【捐贈物資】的查詢方式 
    # (小修改：把變數名稱 items 改成 donations，對應新的 admin.html)
    if sort_type == 'name':
        donations_data = Donation.query.order_by(Donation.donor_name).all()
    elif sort_type == 'item':
        donations_data = Donation.query.order_by(Donation.item_name).all()
    else: # 預設依時間排序 (最新排在最上面)
        donations_data = Donation.query.order_by(Donation.timestamp.desc()).all()
        
    # 4. ✨ 新增：抓取【需求申請】的資料，並優先處理最緊急的！
    requests_data = RequestItem.query.order_by(RequestItem.urgency.desc(), RequestItem.timestamp.desc()).all()
        
    # 5. 把兩包資料一起傳給 admin.html
    return render_template('admin.html', donations=donations_data, requests=requests_data)


@app.route('/export_donations')
def export_donations_excel():
    items = Donation.query.all()
    
    # 1. 建立一個大的 DataFrame
    data = [{
        "ID": item.id,
        "物資名稱": item.item_name,
        "數量": item.quantity,
        "捐贈者": item.donor_name,
        "捐贈時間": item.timestamp.strftime('%Y-%m-%d %H:%M'),
        "物品狀況": item.condition,       
        "捐贈據點": item.address, 
        "聯絡電話": item.phone,
        # 這裡用一個簡單的 if 判斷式，如果有檔名就顯示檔名，沒有就顯示「無照片」
        "照片檔案": item.image_filename if item.image_filename else "無照片"
    } for item in items]
    df_all = pd.DataFrame(data)
    
    # 2. 準備在記憶體中建立 Excel
    output = io.BytesIO()
    
    # 3. 使用 ExcelWriter 來寫入多個 Sheet
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: 所有資料總表
        df_all.to_excel(writer, sheet_name='全部資料', index=False)
        
        # Sheet 2, 3, ... : 依照物資名稱分組
        # 取得所有獨特的物資名稱
        unique_items = df_all['物資名稱'].unique()
        for item_name in unique_items:
            # 篩選出該物資的資料
            df_subset = df_all[df_all['物資名稱'] == item_name]
            # 寫入對應名稱的 Sheet (Excel 的 sheet 名稱限制 31 字以內)
            writer_name = str(item_name)[:31]
            df_subset.to_excel(writer, sheet_name=writer_name, index=False)
    
    output.seek(0)
    return send_file(output, download_name="donations_report.xlsx", as_attachment=True)

@app.route('/export_requests')
def export_requests_excel():
    # 改成抓取需求清單的資料庫
    req_items = RequestItem.query.all()
    
    # 1. 建立一個大的 DataFrame (對應需求的欄位)
    data = [{
        "ID": req.id,
        "申請單位 / 聯絡人": req.requester_name,
        "需求物資": req.item_name,
        "數量": req.quantity,
        "需求地址": req.address,
        "急迫性 (1-5)": req.urgency,
        "處理狀態": "✅ 已結案" if req.is_fulfilled else "⏳ 等待媒合中",
        "申請時間": req.timestamp.strftime('%Y-%m-%d %H:%M')
    } for req in req_items]
    
    df_all = pd.DataFrame(data)
    
    # 2. 準備在記憶體中建立 Excel
    output = io.BytesIO()
    
    # 3. 使用 ExcelWriter 來寫入多個 Sheet
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # 【防呆機制】：如果目前沒有任何需求，就只印出空表頭，避免下面的迴圈報錯
        if df_all.empty:
            df_all.to_excel(writer, sheet_name='全部需求資料', index=False)
        else:
            # Sheet 1: 所有資料總表
            df_all.to_excel(writer, sheet_name='全部需求資料', index=False)
            
            # Sheet 2, 3, ... : 依照需求物資名稱分組
            # 取得所有獨特的需求物資名稱
            unique_items = df_all['需求物資'].unique()
            for item_name in unique_items:
                # 篩選出該物資的資料
                df_subset = df_all[df_all['需求物資'] == item_name]
                # 寫入對應名稱的 Sheet (Excel 的 sheet 名稱限制 31 字以內)
                # 如果使用者填了很長的「其他」物資名稱，這裡會自動截斷防止報錯
                writer_name = str(item_name)[:31]
                df_subset.to_excel(writer, sheet_name=writer_name, index=False)
    
    output.seek(0)
    # 下載的檔名改成 requests_report.xlsx
    return send_file(output, download_name="requests_report.xlsx", as_attachment=True)

@app.route('/request', methods=['GET', 'POST'])
def make_request():
    if request.method == 'POST':
        # 1. 先抓取物資名稱，判斷是不是選了「其他」
        item = request.form.get('item_name')
        if item == '其他':
            item = request.form.get('other_item') # 如果是，就改抓隱藏輸入框的字
            
        new_request = RequestItem(
            item_name=item,  # 這裡改成剛剛處理好的 item 變數
            quantity=request.form.get('quantity'),
            requester_name=request.form.get('requester_name'),
            address=request.form.get('address'),
            # 把急迫性轉成整數存進去
            urgency=int(request.form.get('urgency')) 
        )
        db.session.add(new_request)
        db.session.commit()
        
        # 確認一下你的首頁路由函式名稱是不是 home，如果是的話這行沒問題
        return redirect(url_for('home')) 
        
    # 2. 這裡要改成單數的 request.html (表單頁面)
    return render_template('request.html')

@app.route('/requests')
def list_requests():
    # 從資料庫抓出所有申請，並且「依照急迫性由高到低」排序，如果急迫性一樣則照時間排
    req_items = RequestItem.query.order_by(RequestItem.urgency.desc(), RequestItem.timestamp.desc()).all()
    
    # 這裡呼叫的是複數的 requests.html (清單頁面)
    return render_template('requests.html', requests=req_items)

# --- 管理員功能：刪除捐贈物資 ---
@app.route('/delete_donation/<int:id>')
def delete_donation(id):
    # 根據 ID 找到那筆資料，如果找不到就回傳 404 錯誤
    item_to_delete = Donation.query.get_or_404(id)
    try:
        db.session.delete(item_to_delete)
        db.session.commit()
    except:
        pass # 實務上這裡可以加上錯誤處理
    # 刪除完後，重新導回捐贈清單頁面
    return redirect(url_for('list_donations'))

# --- 管理員功能：更新需求狀態 (結案/刪除) ---
@app.route('/finish_request/<int:id>')
def finish_request(id):
    req = RequestItem.query.get_or_404(id)
    try:
        # 將狀態改為 True (已完成)
        req.is_fulfilled = True
        db.session.commit()
    except:
        pass
    # 更新完後，導回需求清單頁面
    return redirect(url_for('list_requests'))

@app.route('/api/items')
def get_items():
    items = Donation.query.all()
    # 把資料包成 JSON 格式
    return jsonify([{
        "id": i.id, "item": i.item_name, "qty": i.quantity, "donor": i.donor_name
    } for i in items])

if __name__ == '__main__':
    app.run(debug=True)