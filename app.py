import pandas as pd
from flask import Flask, render_template, request, redirect, url_for,abort,send_file,jsonify
from flask_sqlalchemy import SQLAlchemy # 1. 記得匯入這個
import os
from datetime import datetime 
import io 
app = Flask(__name__)

# 2. 設定資料庫檔案的路徑
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'charity.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. 初始化 db 物件 (這就是為什麼之前會報錯，因為沒這行)
db = SQLAlchemy(app)

# 4. 定義資料表模型
class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    donor_name = db.Column(db.String(100), nullable=False)
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
        
        # 如果使用者選「其他」，就改用自定義的那個欄位
        if item == '其他':
            item = request.form.get('other_item')
            
        new_item = Donation(
            item_name=item, # 存入判斷後的名稱
            quantity=request.form.get('quantity'),
            donor_name=request.form.get('donor_name')
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('home'))
        
    return render_template('donate.html')

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

@app.route('/export')
def export_excel():
    # 1. 把所有資料抓出來
    items = Donation.query.all()
    
    # 2. 轉換成 pandas 的 DataFrame 格式
    data = [{
        "ID": item.id,
        "物資名稱": item.item_name,
        "數量": item.quantity,
        "捐贈者": item.donor_name,
        "捐贈時間": item.timestamp.strftime('%Y-%m-%d %H:%M')
    } for item in items]
    
    df = pd.DataFrame(data)
    
    # 3. 把 Excel 存在記憶體中，不用真的存一個檔案在硬碟裡
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    
    # 4. 回傳給瀏覽器下載
    return send_file(output, download_name="donations.xlsx", as_attachment=True)

@app.route('/api/items')
def get_items():
    items = Donation.query.all()
    # 把資料包成 JSON 格式
    return jsonify([{
        "id": i.id, "item": i.item_name, "qty": i.quantity, "donor": i.donor_name
    } for i in items])

if __name__ == '__main__':
    app.run(debug=True)