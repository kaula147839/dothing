from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy # 1. 記得匯入這個
import os

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

# 5. 在程式第一次執行時建立資料庫檔案
with app.app_context():
    db.create_all()

# 在 app.py 中增加這個函數
@app.route('/list')
def list_items():
    # 查詢所有 Donation 表格裡的資料
    items = Donation.query.all()
    # 傳給 list.html 頁面
    return render_template('list.html', items=items)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/donate', methods=['GET', 'POST'])
def donate():
    # 定義好清單
    item_options = ["輪椅", "血壓計", "成人尿布", "看護墊", "拐杖", "其他"]
    
    if request.method == 'POST':
        # ... (存入資料庫的邏輯不變) ...
        return "登記成功！"
    
    # 把清單傳給網頁
    return render_template('donate.html', options=item_options)

if __name__ == '__main__':
    app.run(debug=True)