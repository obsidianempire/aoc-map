from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access

DATABASE = 'map_pins.db'

def get_db():
    """Connect to the SQLite database."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with pins table."""
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS pins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()
    db.close()

@app.route('/pins', methods=['GET'])
def get_pins():
    """Get all pins."""
    try:
        db = get_db()
        pins = db.execute('SELECT * FROM pins ORDER BY created_at DESC').fetchall()
        db.close()
        
        return jsonify([dict(pin) for pin in pins])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pins', methods=['POST'])
def create_pin():
    """Create a new pin."""
    try:
        data = request.json
        
        # Validate required fields
        if not data.get('title') or not data.get('category'):
            return jsonify({'error': 'Title and category are required'}), 400
        
        if data.get('lat') is None or data.get('lng') is None:
            return jsonify({'error': 'Coordinates are required'}), 400
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO pins (title, description, category, lat, lng)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['title'],
            data.get('description', ''),
            data['category'],
            data['lat'],
            data['lng']
        ))
        db.commit()
        
        # Get the newly created pin
        pin = db.execute('SELECT * FROM pins WHERE id = ?', (cursor.lastrowid,)).fetchone()
        db.close()
        
        return jsonify(dict(pin)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['DELETE'])
def delete_pin(pin_id):
    """Delete a pin by ID."""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM pins WHERE id = ?', (pin_id,))
        db.commit()
        
        if cursor.rowcount == 0:
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
        db.close()
        return jsonify({'message': 'Pin deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pins/<int:pin_id>', methods=['PUT'])
def update_pin(pin_id):
    """Update a pin by ID."""
    try:
        data = request.json
        db = get_db()
        
        # Check if pin exists
        pin = db.execute('SELECT * FROM pins WHERE id = ?', (pin_id,)).fetchone()
        if not pin:
            db.close()
            return jsonify({'error': 'Pin not found'}), 404
        
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
        
        return jsonify(dict(updated_pin))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'message': 'Map API is running'})

if __name__ == '__main__':
    # Initialize database on startup
    init_db()
    print("Database initialized!")
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)