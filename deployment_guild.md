# Ashes of Creation Guild Map - Deployment Guide

## What You've Got

1. **Frontend (HTML)** - Interactive map that your guild members will use
2. **Backend (Flask API)** - Python server that stores all the pins
3. **requirements.txt** - Python dependencies

## Setup Instructions

### Option 1: Deploy to Render.com (Recommended - Easiest)

#### Step 1: Prepare Your Code
1. Create a new folder on your computer called `aoc-map`
2. Save these files in the folder:
   - `app.py` (the Flask backend)
   - `requirements.txt`
   - `index.html` (the frontend map)

#### Step 2: Create a GitHub Repository
1. Go to https://github.com and create a new repository (can be private)
2. Upload your three files to the repository

#### Step 3: Deploy to Render
1. Go to https://render.com and sign up (free)
2. Click "New +" → "Web Service"
3. Connect your GitHub account and select your repository
4. Configure:
   - **Name**: `aoc-guild-map` (or whatever you want)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: Free
5. Click "Create Web Service"
6. Wait 2-3 minutes for deployment
7. Copy your service URL (e.g., `https://aoc-guild-map.onrender.com`)

#### Step 4: Update Frontend
1. Open your `index.html` file
2. Find the line: `<input type="text" id="apiUrl" value="http://localhost:5000">`
3. Change it to: `<input type="text" id="apiUrl" value="https://YOUR-SERVICE-URL.onrender.com">`
4. Replace the placeholder map image URL with your actual AoC map image

#### Step 5: Host Frontend
You have several options:
- **GitHub Pages** (free): Upload `index.html` to a GitHub repo, enable Pages
- **Netlify** (free): Drag and drop your `index.html` file
- **Vercel** (free): Similar to Netlify
- **Share directly**: Just send the HTML file to guild members (they update the API URL)

---

### Option 2: Deploy to PythonAnywhere

#### Step 1: Sign Up
1. Go to https://www.pythonanywhere.com
2. Create a free account

#### Step 2: Upload Files
1. Go to "Files" tab
2. Upload `app.py` and `requirements.txt`

#### Step 3: Install Dependencies
1. Go to "Consoles" tab
2. Start a "Bash" console
3. Run: `pip install --user flask flask-cors`

#### Step 4: Configure Web App
1. Go to "Web" tab
2. Click "Add a new web app"
3. Choose "Flask" and Python 3.10
4. Set the path to your `app.py` file
5. Click "Reload" to start your app
6. Your API will be at: `https://YOUR-USERNAME.pythonanywhere.com`

#### Step 5: Update Frontend
- Change the API URL in `index.html` to your PythonAnywhere URL
- Host the frontend using any method above

---

## Using Your Map

### For You (Map Owner):
1. Open the HTML file in your browser
2. Update the API URL if needed
3. Click "Load Pins" to see existing pins
4. Toggle "Add Pin Mode" to start adding pins
5. Click anywhere on the map, fill in details, and save

### For Guild Members:
1. Share the HTML file or hosted URL with them
2. They can view all pins
3. They can add new pins (if you want to restrict this, see Security section)
4. All pins are saved to the server automatically

### Replacing the Map Image:
In the HTML file, find this line:
```javascript
const imageUrl = 'https://via.placeholder.com/2000x2000/1a1a1a/4CAF50?text=Replace+with+your+AoC+Map+Image';
```

Replace it with:
1. **Upload your map to an image host** (Imgur, Discord, etc.)
2. **Get the direct image URL**
3. **Replace the URL in the code**

Or use a local file:
```javascript
const imageUrl = 'path/to/your/aoc-map.jpg';
```

---

## Adding Security (Optional)

If you want to restrict who can add/delete pins, add this to `app.py`:

```python
# At the top of app.py
API_KEY = "your-secret-key-here"

# Add this check to create_pin and delete_pin functions
def create_pin():
    api_key = request.headers.get('X-API-Key')
    if api_key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    # ... rest of the function
```

Then update the frontend to include the key in requests.

---

## Troubleshooting

**"Error connecting to server"**
- Check if your backend is running (visit the health endpoint: `YOUR-API-URL/health`)
- Make sure CORS is enabled (it is by default in the code)
- Check the API URL in the frontend is correct

**Pins not persisting**
- Your backend might be sleeping (free tier on Render sleeps after 15 min of inactivity)
- First request after sleep takes 30-60 seconds to wake up

**Map image not showing**
- Make sure the image URL is publicly accessible
- Try opening the image URL directly in your browser
- Check browser console for errors (F12)

---

## Next Steps

1. Deploy the backend to Render
2. Replace the placeholder map with your actual AoC map
3. Host the frontend (GitHub Pages is easiest)
4. Share with your guild!
5. Consider adding password protection if needed

**Questions?** Check the Flask docs or Render docs for more details!