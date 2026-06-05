import pandas as pd
from flask import Flask, render_template, request, redirect, url_for,abort,send_file,jsonify
from flask_sqlalchemy import SQLAlchemy # 1. 記得匯入這個
import os
from datetime import datetime 
import io 
from werkzeug.utils import secure_filename
import math
from datetime import datetime
import random
# 這兩行來載入免費地圖 API
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic

app = Flask(__name__)
geolocator = ArcGIS()
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

# ✨ 新增：據點設定資料庫
class Hub(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # 例如：南部據點
    address = db.Column(db.String(200), nullable=False)          # 據點真實地址

# 5. 在程式第一次執行時建立資料庫檔案
with app.app_context():
    db.create_all()

# --- 模擬距離計算的函式 ---
def get_real_distance(hub_name, req_address):
    """
    【ArcGIS 商用級地圖連線版】
    使用強大的 ArcGIS 引擎，精準解析台灣複雜地址！
    """
    hub = Hub.query.filter_by(name=hub_name).first()
    hub_address = hub.address if hub else ""
    req_address = str(req_address) if req_address else ""

    try:
        # 直接呼叫 ArcGIS 幫我們找座標
        location_hub = geolocator.geocode(hub_address, timeout=10)
        location_req = geolocator.geocode(req_address, timeout=10)

        # 如果成功拿到座標，計算精準直線距離
        if location_hub and location_req:
            coords_hub = (location_hub.latitude, location_hub.longitude)
            coords_req = (location_req.latitude, location_req.longitude)
            real_dist = geodesic(coords_hub, coords_req).kilometers
            return round(real_dist, 1)
            
    except Exception as e:
        print(f"ArcGIS API 查詢失敗: {e}")

    # =========================================================
    # 萬一連 ArcGIS 都查不到 (例如地址亂填)，最後的保底機制
    # =========================================================
    if "南投" in req_address: req_zone = "中部"
    elif any(city in req_address for city in ["苗栗", "台中", "彰化", "雲林", "嘉義"]): req_zone = "西部"
    elif any(city in req_address for city in ["台南", "高雄", "屏東"]): req_zone = "南部"
    elif any(city in req_address for city in ["台北", "新北", "基隆", "桃園", "新竹"]): req_zone = "北部"
    elif any(city in req_address for city in ["宜蘭", "花蓮", "台東"]): req_zone = "東部"
    else: req_zone = "未知"

    if "南部" in hub_name: return 25.0 if req_zone == "南部" else 150.0
    elif "西部" in hub_name: return 25.0 if req_zone == "西部" else 100.0
    elif "中部" in hub_name: return 25.0 if req_zone == "中部" else 120.0
    elif "北部" in hub_name: return 25.0 if req_zone == "北部" else 150.0
    elif "東部" in hub_name: return 25.0 if req_zone == "東部" else 200.0

    return 99.9  # 絕對防呆值

# --- 配對演算法的路由 ---
@app.route('/match/<int:donation_id>')
def match_algorithm(donation_id):
    # 抓出要處理的這筆捐贈物資
    donation = Donation.query.get_or_404(donation_id)
    
    # 從資料庫找出所有「尚未結案」，而且「需要相同物資」的申請
    # (例如捐贈輪椅，就只跟需要輪椅的申請配對)
    open_requests = RequestItem.query.filter_by(
        is_fulfilled=False, 
        item_name=donation.item_name
    ).all()
    
    match_results = []
    
    for req in open_requests:
        # A. 計算距離 (不會是 0)
        distance = get_real_distance(donation.address, req.address)
        
        # B. 計算等待時間 (小時為單位)
        time_diff = datetime.now() - req.timestamp
        hours_waiting = time_diff.total_seconds() / 3600
        
        # C. 帶入你的演算法公式
        # 注意：因為 1/distance 很小，而 hours_waiting 可能很大，這裡我幫你調整了權重比例，讓分數較平衡
        w1, w2, w3 = 100, 10, 0.5 
        score = (w1 * (1 / distance)) + (w2 * req.urgency) + (w3 * hours_waiting)
        
        # 將計算結果存入清單
        match_results.append({
            'request': req,
            'distance': distance,
            'hours_waiting': round(hours_waiting, 1),
            'score': round(score, 2)
        })
        
    # 根據演算法算出的 Score，由高到低進行排序
    match_results = sorted(match_results, key=lambda x: x['score'], reverse=True)
    
    return render_template('match.html', donation=donation, matches=match_results)

#--- 針對需求申請的配對演算法路由 ---
@app.route('/match_request/<int:request_id>')
def match_request_algorithm(request_id):
    # 1. 抓出這筆急待處理的需求申請
    req = RequestItem.query.get_or_404(request_id)
    
    # 2. 找出庫存中「名稱符合」的捐贈物資
    available_donations = Donation.query.filter_by(
        item_name=req.item_name
    ).all()
    
    match_results = []
    
    # 計算等待時間 (小時為單位)
    time_diff = datetime.now() - req.timestamp
    hours_waiting = time_diff.total_seconds() / 3600
    
    for donation in available_donations:
        # A. 計算距離 (呼叫我們剛剛寫的 get_real_distance)
        # 注意：你的 donation.address 其實存的就是據點名稱 (例如"南部據點")
        distance = get_real_distance(donation.address, req.address)
        
        # B. 帶入演算法公式
        w1, w2, w3 = 100, 10, 0.5 
        score = (w1 * (1 / distance)) + (w2 * req.urgency) + (w3 * hours_waiting)
        
        # 存入結果清單
        match_results.append({
            'donation': donation,
            'distance': distance,
            'score': round(score, 2)
        })
        
    # 根據分數由高到低排序
    match_results = sorted(match_results, key=lambda x: x['score'], reverse=True)
    
    return render_template('match_request.html', req=req, matches=match_results, waiting_hours=round(hours_waiting, 1))

# --- 真正執行配對並更新資料庫的路由 ---
@app.route('/allocate_match/<int:request_id>/<int:donation_id>')
def allocate_match(request_id, donation_id):
    req = RequestItem.query.get_or_404(request_id)
    donation = Donation.query.get_or_404(donation_id)
    
    if donation.quantity > req.quantity:
        # 情況 A：庫存 > 需求 
        donation.quantity -= req.quantity  
        req.is_fulfilled = True  # ✨ 不刪除了！把需求單標記為「已結案」
        
    elif donation.quantity == req.quantity:
        # 情況 B：庫存 = 需求 
        db.session.delete(donation)      
        req.is_fulfilled = True  # ✨ 不刪除了！把需求單標記為「已結案」
        
    else:
        # 情況 C：庫存 < 需求 
        req.quantity -= donation.quantity 
        db.session.delete(donation)      
        
    db.session.commit()
    return redirect('/admin?password=1234')

#--- 顯示已結案的需求清單 ---
@app.route('/history')
def request_history():
    # 專門把「已結案」的需求單撈出來
    completed_requests = RequestItem.query.filter_by(is_fulfilled=True).all()
    
    # 這裡你可以先暫時印在畫面上測試，確認資料有留下來
    result_text = "<h2>✅ 已完成的需求清單：</h2><hr>"
    for req in completed_requests:
        result_text += f"<p>單位：{req.requester_name} | 獲得物資：{req.item_name} (數量: 滿編) | 送達地址：{req.address}</p>"
    
    result_text += "<br><a href='/admin?password=1234'>返回後台</a>"
    return result_text

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
            
        # 處理照片上傳的邏輯 
        photo = request.files.get('photo')
        filename = None # 預設為沒有照片
        if photo and photo.filename != '':
            # 💡 聰明重新命名大法：抓取副檔名 (例如 .jpg 或 .png)
            import os
            import time
            ext = os.path.splitext(photo.filename)[1] 
            
            # 用當前時間的數字當作新檔名 (例如 1717567200.jpg)，保證不重複且沒有中文問題！
            filename = f"{int(time.time())}{ext}"
            
            # 存檔到指定的資料夾
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # 建立資料庫物件
        new_item = Donation(
            item_name=item,
            quantity=request.form.get('quantity'),
            donor_name=request.form.get('donor_name'),
            condition=request.form.get('condition'),
            address=request.form.get('address'),
            phone=request.form.get('phone'),
            image_filename=filename, # ✨【關鍵修復】把圖片檔名乖乖寫入資料庫！
            remarks=request.form.get('remarks') # ✨【新增】抓取表單中的備註資料
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('list_donations'))
        
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
    # 1. 檢查密碼
    if request.args.get('password') != '1234':
        return "密碼錯誤，拒絕存取！"
    
    # 2. 抓取據點資料 
    hubs_data = Hub.query.all()
    
    # 3. 排序與抓取【捐贈物資】
    sort_type = request.args.get('sort', 'timestamp')
    if sort_type == 'name':
        donations_data = Donation.query.order_by(Donation.donor_name).all()
    elif sort_type == 'item':
        donations_data = Donation.query.order_by(Donation.item_name).all()
    else: 
        donations_data = Donation.query.order_by(Donation.timestamp.desc()).all()
        
    # 4. ✨ 分類抓取【需求申請】✨
    # A. 待處理清單 (只抓 is_fulfilled=False，並保留你原本的急迫性排序)
    pending_requests = RequestItem.query.filter_by(is_fulfilled=False).order_by(RequestItem.urgency.desc(), RequestItem.timestamp.desc()).all()
    
    # B. 已完成清單 (只抓 is_fulfilled=True，依完成時間排序)
    completed_requests = RequestItem.query.filter_by(is_fulfilled=True).order_by(RequestItem.timestamp.desc()).all()
        
    # 5. 確保所有資料都有打包送給前端！
    # 注意：原本的 requests 變成了 pending_requests，並且新增了 completed_requests
    return render_template('admin.html', 
                           donations=donations_data, 
                           requests=pending_requests, 
                           hubs=hubs_data,
                           completed_requests=completed_requests)

#--- 匯出 Excel 的路由 ---
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
    # ⚡ 關鍵修改：只抓取尚未結案 (is_fulfilled=False) 的需求清單
    req_items = RequestItem.query.filter_by(is_fulfilled=False).all()
    
    # 1. 建立一個大的 DataFrame
    data = [{
        "ID": req.id,
        "申請單位 / 聯絡人": req.requester_name,
        "需求物資": req.item_name,
        "數量": req.quantity,
        "需求地址": req.address,
        "急迫性 (1-5)": req.urgency,
        "處理狀態": "⏳ 等待媒合中",  # 這裡直接寫死，因為抓出來的肯定都還沒結案！
        "申請時間": req.timestamp.strftime('%Y-%m-%d %H:%M')
    } for req in req_items]
    
    df_all = pd.DataFrame(data)
    
    # 2. 準備在記憶體中建立 Excel
    output = io.BytesIO()
    
    # 3. 使用 ExcelWriter 來寫入多個 Sheet
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        # 【防呆機制】：如果目前沒有任何需求，就只印出空表頭
        if df_all.empty:
            df_all.to_excel(writer, sheet_name='待處理需求資料', index=False)
        else:
            # Sheet 1: 所有資料總表
            df_all.to_excel(writer, sheet_name='待處理需求資料', index=False)
            
            # Sheet 2, 3, ... : 依照需求物資名稱分組
            unique_items = df_all['需求物資'].unique()
            for item_name in unique_items:
                df_subset = df_all[df_all['需求物資'] == item_name]
                writer_name = str(item_name)[:31]
                df_subset.to_excel(writer, sheet_name=writer_name, index=False)
    
    output.seek(0)
    # 匯出檔名不變，還是 requests_report.xlsx
    return send_file(output, download_name="requests_report.xlsx", as_attachment=True)
# --- 新增一個專門匯出「已結案需求」的 Excel 路由，讓管理員可以專門下載歷史紀錄 ---
@app.route('/export_history')
def export_history_excel():
    # 1. 撈出所有已結案的需求 (依照時間新到舊排序)
    completed_requests = RequestItem.query.filter_by(is_fulfilled=True).order_by(RequestItem.timestamp.desc()).all()
    
    # ⚡ 防呆機制：如果根本沒有歷史紀錄，就回傳提示，避免 Pandas 處理空資料報錯
    if not completed_requests:
        return "目前還沒有已結案的歷史紀錄可以匯出喔！<br><a href='/admin?password=1234'>返回後台</a>"
    
    # 2. 建立資料字典給 Pandas
    data = [{
        "紀錄編號": req.id,
        "受贈單位 / 聯絡人": req.requester_name,
        "獲配物資": req.item_name,
        "數量": req.quantity,
        "送達地址": req.address,
        "急迫性 (滿分5)": req.urgency,
        "建立時間": req.timestamp.strftime('%Y-%m-%d %H:%M')
    } for req in completed_requests]
    
    df_all = pd.DataFrame(data)
    
    # 3. 準備在記憶體中建立 Excel
    output = io.BytesIO()
    
    # 4. 使用 ExcelWriter 寫入 (保留你原本超讚的多 Sheet 分類功能)
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: 所有歷史紀錄總表
        df_all.to_excel(writer, sheet_name='全部結案紀錄', index=False)
        
        # Sheet 2, 3, ... : 依照獲配物資名稱分組
        unique_items = df_all['獲配物資'].unique()
        for item_name in unique_items:
            # 篩選出該物資的紀錄
            df_subset = df_all[df_all['獲配物資'] == item_name]
            # Excel sheet 名稱限制 31 字以內
            writer_name = str(item_name)[:31] 
            df_subset.to_excel(writer, sheet_name=writer_name, index=False)
    
    output.seek(0)
    # 下載的檔名改成 history_report
    return send_file(output, download_name="history_report.xlsx", as_attachment=True)

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

# 處理工作人員修改據點資料的 POST 路由
@app.route('/update_hub', methods=['POST'])
def update_hub():
    hub_id = request.form.get('hub_id')
    new_address = request.form.get('address')
    
    hub = Hub.query.filter_by(id=hub_id).first()
    if hub:    
        hub.address = new_address
        db.session.commit()
        
    # 修改成功後，自動導回後台 (帶上密碼才不會被擋)
    return redirect('/admin?password=1234')

@app.route('/init_data')
def init_data():
    # 1. 核彈級清空，重建乾淨的表
    db.drop_all()
    db.create_all()
    
    # 2. 建立五大據點
    initial_hubs = [
        Hub(name="南部據點", address="高雄市大樹區學城路一段1號"),
        Hub(name="西部據點", address="台中市西屯區台灣大道"),
        Hub(name="中部據點", address="南投縣埔里鎮中山路"),
        Hub(name="北部據點", address="台北市大安區羅斯福路"),
        Hub(name="東部據點", address="花蓮縣花蓮市中央路")
    ]
    db.session.add_all(initial_hubs)
    
    # 3. 建立測試用【庫存物資】(✨ 這裡有電話！)
    initial_donations = [
        Donation(item_name="成人尿布", quantity=10, condition="全新", donor_name="善心人A", address="南部據點", phone="0911111111"),
        Donation(item_name="成人尿布", quantity=5, condition="全新", donor_name="善心人B", address="西部據點", phone="0922222222"),
        Donation(item_name="輪椅", quantity=1, condition="二手", donor_name="李大明", address="中部據點", phone="0933333333"),
        Donation(item_name="輪椅", quantity=2, condition="全新", donor_name="張阿姨", address="北部據點", phone="0944444444"),
        Donation(item_name="血壓計", quantity=3, condition="全新", donor_name="陳建國", address="東部據點", phone="0955555555"),
        Donation(item_name="血壓計", quantity=5, condition="二手", donor_name="王先生", address="南部據點", phone="0966666666")
    ]
    db.session.add_all(initial_donations)
    
    # 4. 建立測試用【需求申請】(✨ 這裡沒有電話！)
    initial_requests = [
        RequestItem(item_name="成人尿布", quantity=2, requester_name="彰化吳老先生", address="彰化縣彰化市介壽里建興路1號", urgency=4),
        RequestItem(item_name="輪椅", quantity=1, requester_name="南投仁愛之家", address="南投縣仁愛鄉大同村", urgency=5),
        RequestItem(item_name="輪椅", quantity=1, requester_name="桃園李爺爺", address="桃園市中壢區", urgency=3),
        RequestItem(item_name="血壓計", quantity=1, requester_name="台北林奶奶", address="台北市信義區", urgency=2),
        RequestItem(item_name="血壓計", quantity=2, requester_name="高雄長照中心", address="高雄市三民區", urgency=5)
    ]
    db.session.add_all(initial_requests)
    
    # 5. 一次把所有新資料寫入資料庫！
    db.session.commit()
    
    return "✅ 據點、物資、需求資料已全數初始化成功！請點擊這裡回到 <a href='/admin?password=1234'>管理員後台</a> 查看。"

@app.route('/api/items')
def get_items():
    items = Donation.query.all()
    # 把資料包成 JSON 格式
    return jsonify([{
        "id": i.id, "item": i.item_name, "qty": i.quantity, "donor": i.donor_name
    } for i in items])

# 確保資料庫表格都有被建立
with app.app_context():
    db.create_all()
if __name__ == '__main__':
    app.run(debug=True)