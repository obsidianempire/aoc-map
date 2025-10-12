import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Replace this with the actual tile URL pattern you found
TILE_URL = "https://cdn.ashescodex.com/map/20250826/{z}/{x}/{y}.webp"

# Choose zoom level (experiment to see which gives full detail)
MAXZOOM = 50

# Define coordinate range — you can inspect from Network tab or just guess ranges
X_MIN, X_MAX = 0, 10
Y_MIN, Y_MAX = 0, 10

for zoom in range(8,MAXZOOM):

    xMax = 400
    yMax = 400
    for x in range(X_MIN, xMax + 1):
        for y in range(Y_MIN, yMax + 1):            
            url = TILE_URL.format(z=zoom, x=x, y=y)
            print(f"URL: {url}")
            try:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=10) as resp:
                    status = resp.getcode()
                    if status == 200:
                        OUTPUT_DIR = f"tiles/{zoom}/{x}"
                        os.makedirs(OUTPUT_DIR, exist_ok=True)
                        out_path = os.path.join(OUTPUT_DIR, f"{y}.webp")
                        data = resp.read()
                        with open(out_path, "wb") as f:
                            f.write(data)
                        print(f"Downloaded {x},{y}")
                    else:
                        print(f"Skipped {x},{y}: HTTP {status}")
            except HTTPError as e:
                print(f"Failed {x},{y}: HTTP {e.code}")
            except URLError as e:
                print(f"Failed {x},{y}: {e.reason}")
            except Exception as e:
                print(f"Failed {x},{y}: {e}")
