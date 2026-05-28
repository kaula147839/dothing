from flask import Flask, render_template

app = Flask(__name__)

# 這是首頁，告訴伺服器當有人輸入網址時要顯示什麼
@app.route('/')
def home():
    return "<h1>這是我們的慈善媒合系統首頁</h1><p>歡迎來到物資媒合平台！</p>"

if __name__ == '__main__':
    app.run(debug=True)