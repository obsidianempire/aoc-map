from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import sqlite3
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
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'

DATABASE = 'map_pins.db'

def get_db():
    """Connect to the SQLite database."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with pins table."""
    try:
        db = get_db()
        
        # Create pins table with Discord columns
        db.execute('''
            CREATE TABLE IF NOT EXISTS pins (
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
        ''')
        
        db.commit()
        db.close()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")

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
        
        # Extract token from "Bearer <token>"
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else auth_header
        
        user_data = verify_token(token)
        if not user_data:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Attach user data to request
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

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy', 
        'message': 'Map API is running',
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
        'scope': 'identify'
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
        
        # Create JWT token
        jwt_token = create_token(user_data)
        
        # Return HTML that sends message to parent window
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
                
                // Auto-close after 2 seconds
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
        pins = db.execute('SELECT * FROM pins ORDER BY created_at DESC').fetchall()
        db.close()
        
        pins_list = [dict(pin) for pin in pins]
        print(f"📍 Returning {len(pins_list)} pins")
        return jsonify(pins_list)
        
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
        
        # Validate required fields
        if not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400
        
        if not data.get('category'):
            return jsonify({'error': 'Category is required'}), 400
        
        if data.get('lat') is None or data.get('lng') is None:
            return jsonify({'error': 'Coordinates are required'}), 400
        
        db = get_db()
        cursor = db.execute('''
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
        db.commit()
        
        # Get the newly created pin
        pin = db.execute('SELECT * FROM pins WHERE id = ?', (cursor.lastrowid,)).fetchone()
        db.close()
        
        pin_dict = dict(pin)
        print(f"✅ Pin created: ID {pin_dict['id']}")
        return jsonify(pin_dict), 201
        
    except Exception as e:
        print(f"❌ Error creating pin: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['DELETE'])
@require_auth
def delete_pin(pin_id):
    """Delete a pin (only if user owns it)."""
    try:
        db = get_db()
        
        # Check if pin exists
        pin = db.execute('SELECT * FROM pins WHERE id = ?', (pin_id,)).fetchone()
        
        if not pin:
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
        # Check ownership
        if pin['discord_user_id'] != request.user['discord_id']:
            db.close()
            print(f"⛔ User {request.user['username']} tried to delete pin owned by {pin['discord_username']}")
            return jsonify({'error': 'You can only delete your own pins'}), 403
        
        # Delete the pin
        db.execute('DELETE FROM pins WHERE id = ?', (pin_id,))
        db.commit()
        db.close()
        
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
        
        # Check if pin exists
        pin = db.execute('SELECT * FROM pins WHERE id = ?', (pin_id,)).fetchone()
        
        if not pin:
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
        # Check ownership
        if pin['discord_user_id'] != request.user['discord_id']:
            db.close()
            return jsonify({'error': 'You can only edit your own pins'}), 403
        
        # Update pin
        db.execute('''
            UPDATE pins 
            SET title = ?, description = ?, category = ?, lat = ?, lng = ?
            WHERE id = ?
        ''', (
            data.get('title', pin['title']),
            data.get('description', pin['description']),
            data.get('category', pin['category']),
            data.get('lat', pin['lat']),
            data.get('lng', pin['lng']),
            pin_id
        ))
        db.commit()
        
        # Get updated pin
        updated_pin = db.execute('SELECT * FROM pins WHERE id = ?', (pin_id,)).fetchone()
        db.close()
        
        print(f"✏️ Pin {pin_id} updated by {request.user['username']}")
        return jsonify(dict(updated_pin))
        
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
    # When running with Gunicorn
    init_db()
    print("🚀 Running with Gunicorn...")