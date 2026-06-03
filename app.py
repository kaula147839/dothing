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

# 5. 在程式第一次執行時建立資料庫檔案
with app.app_context():
    db.create_all()

@app.route('/list')
def list_items():
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
        
    return render_template('list.html', items=items, query=search_query, sort=sort_type)

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
        return redirect(url_for('list_items')) # 或 redirect(url_for('home'))
        
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


# 新增一個刪除功能
@app.route('/admin', methods=['GET'])
def admin_panel():
    # 1. 檢查密碼
    if request.args.get('password') != '1234':
        return "密碼錯誤，拒絕存取！"
    
    # 2. 獲取排序參數
    sort_type = request.args.get('sort', 'timestamp')
    
    # 3. 根據參數決定查詢方式
    if sort_type == 'name':
        items = Donation.query.order_by(Donation.donor_name).all()
    elif sort_type == 'item':
        items = Donation.query.order_by(Donation.item_name).all()
    else: # 預設依時間排序 (最新排在最上面)
        items = Donation.query.order_by(Donation.timestamp.desc()).all()
        
    return render_template('admin.html', items=items)


@app.route('/export')
def export_excel():
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

@app.route('/api/items')
def get_items():
    items = Donation.query.all()
    # 把資料包成 JSON 格式
    return jsonify([{
        "id": i.id, "item": i.item_name, "qty": i.quantity, "donor": i.donor_name
    } for i in items])

if __name__ == '__main__':
    app.run(debug=True)