from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import requests
import jwt
from datetime import datetime, timedelta
from functools import wraps

# --- NEW: SQLAlchemy / Postgres ---
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
CORS(app, supports_credentials=True, origins=['*'])

# Discord OAuth2 settings
DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', '')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'

# ---------- DATABASE (PostgreSQL via SQLAlchemy) ----------
def _normalize_db_url(url: str) -> str:
    # Some providers (including older Render strings) use postgres://; SQLAlchemy prefers postgresql://
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Force psycopg v3 driver
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = _normalize_db_url(os.environ.get("DATABASE_URL", ""))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Add it in Render > Environment.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,              # drops dead connections
    pool_recycle=1800,               # recycle every 30 min
)

def init_db():
    """Initialize the database with pins table (idempotent)."""
    try:
        create_sql = """
        CREATE TABLE IF NOT EXISTS pins (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lng DOUBLE PRECISION NOT NULL,
            discord_user_id TEXT NOT NULL,
            discord_username TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        with engine.begin() as conn:
            conn.execute(text(create_sql))
        print("✅ PostgreSQL initialized (table: pins)")
    except SQLAlchemyError as e:
        print(f"❌ Error initializing PostgreSQL: {e}")
        raise

# ---------- Auth / JWT (unchanged) ----------
def create_token(user_data):
    payload = {
        'discord_id': user_data['id'],
        'username': user_data['username'],
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

def verify_token(token):
    try:
        return jwt.decode(token, app.secret_key, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {e}")
        return None

def require_auth(f):
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
    return send_from_directory('.', 'index.html')

@app.route('/AshesMapVerra.jpg')
def serve_map_image():
    return send_from_directory('.', 'AshesMapVerra.jpg')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Map API is running',
        'discord_configured': bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET)
    })

@app.route('/login', methods=['GET'])
def login():
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
    code = request.args.get('code')
    if not code:
        return '<html><body><p>Error: No authorization code received</p></body></html>', 400
    try:
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

        access_token = token_response.json()['access_token']
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
                setTimeout(function() {{ window.close(); }}, 2000);
            </script>
        </body>
        </html>
        '''
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        return f'<html><body><p>Error during authentication: {str(e)}</p></body></html>', 500

# --- Removed local-file deleter; Postgres isn't a file. Keep endpoint as a safe NOOP or 410. ---
@app.route("/delete_db", methods=["DELETE"])
def delete_db():
    return jsonify({"error": "not-applicable: using PostgreSQL now"}), 410

@app.route('/verify', methods=['GET'])
def verify():
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
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM pins ORDER BY created_at DESC")).mappings().all()
        pins_list = [dict(r) for r in rows]
        print(f"📍 Returning {len(pins_list)} pins")
        return jsonify(pins_list)
    except SQLAlchemyError as e:
        print(f"❌ Error getting pins: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins', methods=['POST'])
@require_auth
def create_pin():
    """Create a new pin (auth required)."""
    try:
        data = request.json or {}
        print(f"📝 Creating pin: {data.get('title')} by {request.user['username']}")

        # Validation
        if not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400
        if not data.get('category'):
            return jsonify({'error': 'Category is required'}), 400
        if data.get('lat') is None or data.get('lng') is None:
            return jsonify({'error': 'Coordinates are required'}), 400

        insert_sql = text("""
            INSERT INTO pins (title, description, category, lat, lng, discord_user_id, discord_username)
            VALUES (:title, :description, :category, :lat, :lng, :discord_user_id, :discord_username)
            RETURNING id, title, description, category, lat, lng, discord_user_id, discord_username, created_at
        """)
        params = {
            "title": data["title"],
            "description": data.get("description", ""),
            "category": data["category"],
            "lat": float(data["lat"]),
            "lng": float(data["lng"]),
            "discord_user_id": request.user["discord_id"],
            "discord_username": request.user["username"],
        }
        with engine.begin() as conn:
            row = conn.execute(insert_sql, params).mappings().one()
        pin_dict = dict(row)
        print(f"✅ Pin created: ID {pin_dict['id']}")
        return jsonify(pin_dict), 201
    except (SQLAlchemyError, ValueError, KeyError) as e:
        print(f"❌ Error creating pin: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['DELETE'])
@require_auth
def delete_pin(pin_id):
    """Delete a pin (only if user owns it)."""
    try:
        with engine.begin() as conn:
            pin = conn.execute(text("SELECT * FROM pins WHERE id = :id"), {"id": pin_id}).mappings().first()
            if not pin:
                return jsonify({'error': 'Pin not found'}), 404
            if pin['discord_user_id'] != request.user['discord_id']:
                print(f"⛔ User {request.user['username']} tried to delete pin owned by {pin['discord_username']}")
                return jsonify({'error': 'You can only delete your own pins'}), 403
            conn.execute(text("DELETE FROM pins WHERE id = :id"), {"id": pin_id})
        print(f"🗑️ Pin {pin_id} deleted by {request.user['username']}")
        return jsonify({'message': 'Pin deleted successfully'})
    except SQLAlchemyError as e:
        print(f"❌ Error deleting pin: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['PUT'])
@require_auth
def update_pin(pin_id):
    """Update a pin (only if user owns it)."""
    try:
        data = request.json or {}
        with engine.begin() as conn:
            pin = conn.execute(text("SELECT * FROM pins WHERE id = :id"), {"id": pin_id}).mappings().first()
            if not pin:
                return jsonify({'error': 'Pin not found'}), 404
            if pin['discord_user_id'] != request.user['discord_id']:
                return jsonify({'error': 'You can only edit your own pins'}), 403

            new_vals = {
                "title": data.get('title', pin['title']),
                "description": data.get('description', pin['description']),
                "category": data.get('category', pin['category']),
                "lat": float(data.get('lat', pin['lat'])),
                "lng": float(data.get('lng', pin['lng'])),
                "id": pin_id
            }
            conn.execute(text("""
                UPDATE pins
                   SET title = :title,
                       description = :description,
                       category = :category,
                       lat = :lat,
                       lng = :lng
                 WHERE id = :id
            """), new_vals)

            updated = conn.execute(text("SELECT * FROM pins WHERE id = :id"), {"id": pin_id}).mappings().first()
        print(f"✏️ Pin {pin_id} updated by {request.user['username']}")
        return jsonify(dict(updated))
    except (SQLAlchemyError, ValueError) as e:
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
