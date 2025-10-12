from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import os
import requests
import jwt
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
CORS(app, supports_credentials=True, origins=['*'])

# Discord OAuth2 settings
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', '')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID', '')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith('postgres'))

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("🐘 Using PostgreSQL database")
else:
    import sqlite3
    DATABASE_URL = 'map_pins.db'
    print("📁 Using SQLite database")

def get_db():
    """Connect to the database (SQLite or PostgreSQL)."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        db = sqlite3.connect(DATABASE_URL)
        db.row_factory = sqlite3.Row
        return db

def dict_from_row(row):
    """Convert database row to dictionary."""
    if USE_POSTGRES:
        return dict(row)
    else:
        return dict(row)

def init_db():
    """Initialize the database with pins table."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        if USE_POSTGRES:
            # PostgreSQL version
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pins (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    discord_user_id TEXT NOT NULL,
                    discord_username TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.commit()
            print("✅ PostgreSQL database initialized successfully!")
        else:
            # SQLite version with migration support
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pins'")
            table_exists = cursor.fetchone()
            
            if table_exists:
                cursor.execute("PRAGMA table_info(pins)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if 'discord_user_id' not in columns:
                    print("🔄 Migrating SQLite database...")
                    cursor.execute("ALTER TABLE pins RENAME TO pins_old")
                    
                    cursor.execute("""
                        CREATE TABLE pins (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            description TEXT,
                            category TEXT NOT NULL,
                            lat REAL NOT NULL,
                            lng REAL NOT NULL,
                            discord_user_id TEXT NOT NULL,
                            discord_username TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    cursor.execute("""
                        INSERT INTO pins (id, title, description, category, lat, lng, discord_user_id, discord_username, created_at)
                        SELECT id, title, description, category, lat, lng, 'legacy-user', 'Legacy User', 
                               COALESCE(created_at, CURRENT_TIMESTAMP)
                        FROM pins_old
                    """)
                    
                    migrated = cursor.rowcount
                    cursor.execute("DROP TABLE pins_old")
                    print(f"✅ Migrated {migrated} existing pins")
            else:
                cursor.execute("""
                    CREATE TABLE pins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT,
                        category TEXT NOT NULL,
                        lat REAL NOT NULL,
                        lng REAL NOT NULL,
                        discord_user_id TEXT NOT NULL,
                        discord_username TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                print("✅ SQLite database initialized successfully!")
        
        db.commit()
        cursor.close()
        db.close()
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        raise

def create_token(user_data):
    """Create a JWT token for the user."""
    payload = {
        'discord_id': user_data['id'],
        'username': user_data['username'],
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

def verify_token(token):
    """Verify and decode a JWT token."""
    try:
        return jwt.decode(token, app.secret_key, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {e}")
        return None

def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization token provided'}), 401
        
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header
        user_data = verify_token(token)
        
        if not user_data:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.user = user_data
        return f(*args, **kwargs)
    
    return decorated_function

# ==================== ROUTES ====================

@app.route('/')
def home():
    """Serve the interactive map HTML."""
    return send_from_directory('.', 'index.html')

@app.route('/AshesMapVerra.jpg')
def serve_map_image():
    """Serve the map image."""
    return send_from_directory('.', 'AshesMapVerra.jpg')

@app.route('/tiles/<int:z>/<int:x>/<int:y>.webp')
def serve_tile(z, x, y):
    """Serve map tiles."""
    try:
        tile_path = f'tiles/{z}/{x}/{y}.webp'
        if os.path.exists(tile_path):
            return send_from_directory('tiles', f'{z}/{x}/{y}.webp')
        else:
            # Return 404 for missing tiles (frontend will show transparent)
            return '', 404
    except Exception as e:
        print(f"Error serving tile {z}/{x}/{y}: {e}")
        return '', 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy', 
        'message': 'Map API is running',
        'database': 'PostgreSQL' if USE_POSTGRES else 'SQLite',
        'discord_configured': bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET)
    })

@app.route('/login', methods=['GET'])
def login():
    """Return Discord OAuth2 authorization URL."""
    if not DISCORD_CLIENT_ID:
        return jsonify({'error': 'Discord OAuth not configured'}), 500
    
    params = {
        'client_id': DISCORD_CLIENT_ID,
        'redirect_uri': DISCORD_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify guilds'
    }
    
    param_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    auth_url = f"{DISCORD_API_ENDPOINT}/oauth2/authorize?{param_string}"
    
    return jsonify({'auth_url': auth_url})

@app.route('/callback')
def callback():
    """Handle Discord OAuth2 callback."""
    code = request.args.get('code')
    
    if not code:
        return '<html><body><p>Error: No authorization code received</p></body></html>', 400
    
    try:
        # Exchange code for access token
        token_data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DISCORD_REDIRECT_URI
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_response = requests.post(
            f"{DISCORD_API_ENDPOINT}/oauth2/token", 
            data=token_data, 
            headers=headers,
            timeout=10
        )
        
        if token_response.status_code != 200:
            print(f"Token exchange failed: {token_response.text}")
            return f'<html><body><p>Error getting access token: {token_response.status_code}</p></body></html>', 400
        
        token_json = token_response.json()
        access_token = token_json['access_token']
        
        # Get user info from Discord
        user_headers = {'Authorization': f"Bearer {access_token}"}
        user_response = requests.get(
            f"{DISCORD_API_ENDPOINT}/users/@me", 
            headers=user_headers,
            timeout=10
        )
        
        if user_response.status_code != 200:
            print(f"User info fetch failed: {user_response.text}")
            return '<html><body><p>Error getting user info</p></body></html>', 400
        
        user_data = user_response.json()
        print(f"✅ User logged in: {user_data['username']}")
        
        # Check guild membership if DISCORD_GUILD_ID is set
        if DISCORD_GUILD_ID:
            guilds_response = requests.get(
                f"{DISCORD_API_ENDPOINT}/users/@me/guilds", 
                headers=user_headers,
                timeout=10
            )
            
            if guilds_response.status_code == 200:
                guilds = guilds_response.json()
                is_member = any(guild['id'] == DISCORD_GUILD_ID for guild in guilds)
                
                if not is_member:
                    print(f"⛔ User {user_data['username']} is not a member of the required guild")
                    return '''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Access Denied</title>
                        <style>
                            body {
                                background: #0a0a0a;
                                color: #d4a574;
                                font-family: 'Segoe UI', sans-serif;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                height: 100vh;
                                margin: 0;
                            }
                            .message {
                                text-align: center;
                                padding: 40px;
                                border: 2px solid #c41e3a;
                                border-radius: 8px;
                                background: rgba(20, 20, 20, 0.95);
                            }
                            h2 { color: #c41e3a; }
                        </style>
                    </head>
                    <body>
                        <div class="message">
                            <h2>❌ Access Denied</h2>
                            <p>You must be a member of the Obsidian Empire Discord server to access this map.</p>
                            <p style="margin-top: 20px; font-size: 12px; color: #8b8b8b;">You can close this window now.</p>
                        </div>
                        <script>
                            setTimeout(function() {
                                window.close();
                            }, 5000);
                        </script>
                    </body>
                    </html>
                    ''', 403
                
                print(f"✅ User {user_data['username']} is a member of Obsidian Empire")
            else:
                print(f"⚠️ Could not verify guild membership for {user_data['username']}")
        
        # Create JWT token
        jwt_token = create_token(user_data)
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body {{
                    background: #0a0a0a;
                    color: #d4a574;
                    font-family: 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }}
                .message {{
                    text-align: center;
                    padding: 40px;
                    border: 2px solid #8b4513;
                    border-radius: 8px;
                    background: rgba(20, 20, 20, 0.95);
                }}
            </style>
        </head>
        <body>
            <div class="message">
                <h2>✅ Authentication Successful!</h2>
                <p>Welcome, {user_data['username']}!</p>
                <p>You can close this window now.</p>
            </div>
            <script>
                window.opener.postMessage({{
                    type: 'discord_auth',
                    token: '{jwt_token}',
                    username: '{user_data['username']}'
                }}, '*');
                
                setTimeout(function() {{
                    window.close();
                }}, 2000);
            </script>
        </body>
        </html>
        '''
        
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        return f'<html><body><p>Error during authentication: {str(e)}</p></body></html>', 500

@app.route('/verify', methods=['GET'])
def verify():
    """Verify a token and return user info."""
    auth_header = request.headers.get('Authorization')
    
    if not auth_header:
        return jsonify({'authenticated': False}), 401
    
    token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header
    user_data = verify_token(token)
    
    if not user_data:
        return jsonify({'authenticated': False}), 401
    
    return jsonify({
        'authenticated': True,
        'discord_id': user_data['discord_id'],
        'username': user_data['username']
    })

@app.route('/pins', methods=['GET'])
def get_pins():
    """Get all pins (no auth required)."""
    try:
        db = get_db()
        
        if USE_POSTGRES:
            cursor = db.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM pins ORDER BY created_at DESC')
            pins = cursor.fetchall()
            cursor.close()
        else:
            cursor = db.cursor()
            cursor.execute('SELECT * FROM pins ORDER BY created_at DESC')
            pins = [dict(row) for row in cursor.fetchall()]
            cursor.close()
        
        db.close()
        
        print(f"📍 Returning {len(pins)} pins")
        return jsonify(pins)
        
    except Exception as e:
        print(f"❌ Error getting pins: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins', methods=['POST'])
@require_auth
def create_pin():
    """Create a new pin (auth required)."""
    try:
        data = request.json
        print(f"📝 Creating pin: {data.get('title')} by {request.user['username']}")
        
        if not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400
        
        if not data.get('category'):
            return jsonify({'error': 'Category is required'}), 400
        
        if data.get('lat') is None or data.get('lng') is None:
            return jsonify({'error': 'Coordinates are required'}), 400
        
        db = get_db()
        cursor = db.cursor()
        
        if USE_POSTGRES:
            cursor.execute('''
                INSERT INTO pins (title, description, category, lat, lng, discord_user_id, discord_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            ''', (
                data['title'],
                data.get('description', ''),
                data['category'],
                float(data['lat']),
                float(data['lng']),
                request.user['discord_id'],
                request.user['username']
            ))
            pin = cursor.fetchone()
        else:
            cursor.execute('''
                INSERT INTO pins (title, description, category, lat, lng, discord_user_id, discord_username)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['title'],
                data.get('description', ''),
                data['category'],
                float(data['lat']),
                float(data['lng']),
                request.user['discord_id'],
                request.user['username']
            ))
            cursor.execute('SELECT * FROM pins WHERE id = ?', (cursor.lastrowid,))
            pin = dict(cursor.fetchone())
        
        db.commit()
        cursor.close()
        db.close()
        
        pin_dict = dict(pin) if USE_POSTGRES else pin
        print(f"✅ Pin created: ID {pin_dict['id']}")
        return jsonify(pin_dict), 201
        
    except Exception as e:
        print(f"❌ Error creating pin: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['DELETE'])
@require_auth
def delete_pin(pin_id):
    """Delete a pin (only if user owns it or is admin)."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if pin exists
        if USE_POSTGRES:
            cursor.execute('SELECT * FROM pins WHERE id = %s', (pin_id,))
        else:
            cursor.execute('SELECT * FROM pins WHERE id = ?', (pin_id,))
        
        pin = cursor.fetchone()
        
        if not pin:
            cursor.close()
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
        pin_dict = dict(pin)
        
        # Check if user is admin
        is_admin = request.user['username'].lower() == 'randmiester'
        
        # Check ownership or admin status
        if pin_dict['discord_user_id'] != request.user['discord_id'] and not is_admin:
            cursor.close()
            db.close()
            print(f"⛔ User {request.user['username']} tried to delete pin owned by {pin_dict['discord_username']}")
            return jsonify({'error': 'You can only delete your own pins'}), 403
        
        # Delete the pin
        if USE_POSTGRES:
            cursor.execute('DELETE FROM pins WHERE id = %s', (pin_id,))
        else:
            cursor.execute('DELETE FROM pins WHERE id = ?', (pin_id,))
        
        db.commit()
        cursor.close()
        db.close()
        
        if is_admin and pin_dict['discord_user_id'] != request.user['discord_id']:
            print(f"👑 Admin {request.user['username']} deleted pin {pin_id} owned by {pin_dict['discord_username']}")
        else:
            print(f"🗑️ Pin {pin_id} deleted by {request.user['username']}")
        
        return jsonify({'message': 'Pin deleted successfully'})
        
    except Exception as e:
        print(f"❌ Error deleting pin: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['PUT'])
@require_auth
def update_pin(pin_id):
    """Update a pin (only if user owns it)."""
    try:
        data = request.json
        db = get_db()
        cursor = db.cursor()
        
        # Check if pin exists
        if USE_POSTGRES:
            cursor.execute('SELECT * FROM pins WHERE id = %s', (pin_id,))
        else:
            cursor.execute('SELECT * FROM pins WHERE id = ?', (pin_id,))
        
        pin = cursor.fetchone()
        
        if not pin:
            cursor.close()
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
        pin_dict = dict(pin)
        
        # Check ownership
        if pin_dict['discord_user_id'] != request.user['discord_id']:
            cursor.close()
            db.close()
            return jsonify({'error': 'You can only edit your own pins'}), 403
        
        # Update pin
        if USE_POSTGRES:
            cursor.execute('''
                UPDATE pins 
                SET title = %s, description = %s, category = %s, lat = %s, lng = %s
                WHERE id = %s
                RETURNING *
            ''', (
                data.get('title', pin_dict['title']),
                data.get('description', pin_dict['description']),
                data.get('category', pin_dict['category']),
                data.get('lat', pin_dict['lat']),
                data.get('lng', pin_dict['lng']),
                pin_id
            ))
            updated_pin = cursor.fetchone()
        else:
            cursor.execute('''
                UPDATE pins 
                SET title = ?, description = ?, category = ?, lat = ?, lng = ?
                WHERE id = ?
            ''', (
                data.get('title', pin_dict['title']),
                data.get('description', pin_dict['description']),
                data.get('category', pin_dict['category']),
                data.get('lat', pin_dict['lat']),
                data.get('lng', pin_dict['lng']),
                pin_id
            ))
            cursor.execute('SELECT * FROM pins WHERE id = ?', (pin_id,))
            updated_pin = dict(cursor.fetchone())
        
        db.commit()
        cursor.close()
        db.close()
        
        result = dict(updated_pin) if USE_POSTGRES else updated_pin
        print(f"✏️ Pin {pin_id} updated by {request.user['username']}")
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error updating pin: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== STARTUP ====================

if __name__ == '__main__':
    init_db()
    print("🚀 Starting development server...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    init_db()
    print("🚀 Running with Gunicorn...")