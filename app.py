from flask import Flask, request, Response, jsonify, render_template_string
import requests
import urllib.parse
import threading
from datetime import datetime, timedelta
import os
import base64

app = Flask(__name__)

# Configuration - Simplified without API keys
MAX_FREE_DAILY = 60
MAX_FREE_MONTHLY = 100
RESET_INTERVAL = 24 * 3600  # Daily reset in seconds

# Rate tracking
usage_tracker = {}
lock = threading.Lock()

def reset_usage():
    """Periodically reset usage counts"""
    with lock:
        now = datetime.now()
        for key, usage in list(usage_tracker.items()):
            # Reset daily counts
            if 'daily_reset' not in usage or (now - usage['daily_reset']).days >= 1:
                usage['daily_count'] = 0
                usage['daily_reset'] = now
            
            # Reset monthly counts
            if 'monthly_reset' not in usage or now.month != usage['monthly_reset'].month:
                usage['monthly_count'] = 0
                usage['monthly_reset'] = now

# Start reset thread
def reset_scheduler():
    while True:
        reset_usage()
        threading.Event().wait(RESET_INTERVAL)

threading.Thread(target=reset_scheduler, daemon=True).start()

def build_enhanced_prompt(base_prompt, params):
    """Enhance prompt with style and technical directives"""
    prompt_parts = [base_prompt]
    
    # Lighting control
    if params.get('lighting'):
        prompt_parts.append(f"{params['lighting']} lighting")
    
    # Camera angle
    if params.get('angle'):
        prompt_parts.append(f"{params['angle']} angle")
    
    # Style modifiers
    if params.get('style') == 'vintage':
        intensity = params.get('vintage_intensity', 0.5)
        prompt_parts.append(f"35mm film, grain, faded colors (intensity: {intensity})")
    elif params.get('style') == 'classic':
        prompt_parts.append("oil painting, brush strokes, renaissance style")
    elif params.get('style') == 'aethertic':
        prompt_parts.append("ethereal, dreamlike, mystical atmosphere")
    
    # HDR effect
    if params.get('hdr', False):
        prompt_parts.append("HDR, ultra-detailed, 8k")
    
    # Negative prompt
    if params.get('negative_prompt'):
        prompt_parts.append(f"| NEGATIVE: {params['negative_prompt']}")
    
    return ", ".join(prompt_parts)

# HTML form for user input
HTML_FORM = '''
<!DOCTYPE html>
<html>
<head>
    <title>Image Generation App</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .response { margin-top: 20px; padding: 15px; border-radius: 4px; }
        .success { background: #d4edda; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; border: 1px solid #f5c6cb; }
        .image-result { max-width: 100%; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>AI Image Generator</h1>
    <form id="imageForm" enctype="multipart/form-data">
        <div class="form-group">
            <label for="prompt">Prompt:</label>
            <textarea id="prompt" name="prompt" rows="3" required>a night dark sky with mountain range</textarea>
        </div>
        
        <div class="form-group">
            <label for="lighting">Lighting:</label>
            <select id="lighting" name="lighting">
                <option value="">Select lighting</option>
                <option value="artic" selected>Arctic</option>
                <option value="dramatic">Dramatic</option>
                <option value="soft">Soft</option>
                <option value="natural">Natural</option>
            </select>
        </div>
        
        <div class="form-group">
            <label for="angle">Camera Angle:</label>
            <select id="angle" name="angle">
                <option value="">Select angle</option>
                <option value="low-angle" selected>Low Angle</option>
                <option value="high-angle">High Angle</option>
                <option value="eye-level">Eye Level</option>
                <option value="aerial">Aerial</option>
            </select>
        </div>
        
        <div class="form-group">
            <label for="style">Style:</label>
            <select id="style" name="style">
                <option value="">Select style</option>
                <option value="aethertic" selected>Aethertic</option>
                <option value="vintage">Vintage</option>
                <option value="classic">Classic</option>
                <option value="realistic">Realistic</option>
            </select>
        </div>
        
        <div class="form-group">
            <label>
                <input type="checkbox" name="hdr" value="true" checked> HDR
            </label>
        </div>
        
        <div class="form-group">
            <label>
                <input type="checkbox" name="upscale" value="true" checked> Upscale
            </label>
        </div>
        
        <div class="form-group">
            <label for="batch_size">Batch Size (1-4):</label>
            <input type="number" id="batch_size" name="batch_size" min="1" max="4" value="1">
        </div>
        
        <div class="form-group">
            <label for="cfg_scale">CFG Scale:</label>
            <input type="number" id="cfg_scale" name="cfg_scale" step="0.1" min="1" max="20" value="9.0">
        </div>
        
        <div class="form-group">
            <label for="negative_prompt">Negative Prompt:</label>
            <input type="text" id="negative_prompt" name="negative_prompt" value="blurry, low quality">
        </div>
        
        <div class="form-group">
            <label for="width">Width:</label>
            <input type="number" id="width" name="width" value="1280">
        </div>
        
        <div class="form-group">
            <label for="height">Height:</label>
            <input type="number" id="height" name="height" value="720">
        </div>
        
        <div class="form-group">
            <label for="image_upload">Upload Reference Image (optional):</label>
            <input type="file" id="image_upload" name="image_upload" accept="image/*">
        </div>
        
        <button type="submit">Generate Image</button>
    </form>
    
    <div id="response"></div>
    
    <script>
        document.getElementById('imageForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const responseDiv = document.getElementById('response');
            
            try {
                responseDiv.innerHTML = '<p>Generating image... Please wait.</p>';
                
                const response = await fetch('/generate', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    responseDiv.innerHTML = `
                        <div class="response success">
                            <p>Image generated successfully!</p>
                            <img src="${url}" alt="Generated image" class="image-result">
                            <p><a href="${url}" download="generated-image.jpg">Download Image</a></p>
                        </div>
                    `;
                } else {
                    const error = await response.json();
                    responseDiv.innerHTML = `
                        <div class="response error">
                            <p>Error: ${error.error || 'Unknown error'}</p>
                            ${error.details ? `<p>Details: ${error.details}</p>` : ''}
                        </div>
                    `;
                }
            } catch (error) {
                responseDiv.innerHTML = `
                    <div class="response error">
                        <p>Network error: ${error.message}</p>
                    </div>
                `;
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Serve the main form"""
    return render_template_string(HTML_FORM)

@app.route('/generate/<path:prompt>')
@app.route('/generate', methods=['GET', 'POST'])
def generate_image(prompt=None):
    # Handle both GET (URL) and POST requests
    if prompt:
        # GET request with prompt in URL
        decoded_prompt = urllib.parse.unquote_plus(prompt)
        user_input = {'prompt': decoded_prompt, **request.args}
    elif request.method == 'POST':
        # Handle form data
        if request.content_type and 'multipart/form-data' in request.content_type:
            user_input = request.form.to_dict()
            # Handle file upload
            if 'image_upload' in request.files:
                uploaded_file = request.files['image_upload']
                if uploaded_file.filename:
                    # Convert image to base64 for potential reference (you can modify this based on your needs)
                    user_input['uploaded_image'] = base64.b64encode(uploaded_file.read()).decode('utf-8')
        else:
            user_input = request.json or {}
    else:
        user_input = request.args.to_dict()

    # Rate limiting (free users only)
    ip = request.remote_addr
    
    with lock:
        if ip not in usage_tracker:
            usage_tracker[ip] = {
                'daily_count': 0,
                'monthly_count': 0,
                'daily_reset': datetime.now(),
                'monthly_reset': datetime.now()
            }
        
        if usage_tracker[ip]['daily_count'] >= MAX_FREE_DAILY:
            return jsonify({
                'error': 'Daily free limit exceeded',
                'limit': MAX_FREE_DAILY,
                'reset': (usage_tracker[ip]['daily_reset'] + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
            }), 429
        
        if usage_tracker[ip]['monthly_count'] >= MAX_FREE_MONTHLY:
            return jsonify({
                'error': 'Monthly free limit exceeded',
                'limit': MAX_FREE_MONTHLY,
                'reset': usage_tracker[ip]['monthly_reset'].strftime('%Y-%m-%d')
            }), 429
        
        usage_tracker[ip]['daily_count'] += 1
        usage_tracker[ip]['monthly_count'] += 1

    # Generate image
    try:
        # Base parameters using the payload structure from your screenshot
        params = {
            "width": int(user_input.get('width', 1280)),
            "height": int(user_input.get('height', 720)),
            "seed": user_input.get('seed', int.from_bytes(os.urandom(2), "big")),
            "model": user_input.get('model', 'flux'),
            "nologo": not user_input.get('add_logo', False),
            "steps": int(user_input.get('steps', 50)),
            "cfg_scale": float(user_input.get('cfg_scale', 9.0)),
            "sampler": user_input.get('sampler', 'k_euler')
        }

        # Enhanced prompt building using your payload structure
        enhanced_prompt = build_enhanced_prompt(
            user_input.get('prompt', 'a night dark sky with mountain range'),
            {
                'lighting': user_input.get('lighting', 'artic'),
                'angle': user_input.get('angle', 'low-angle'),
                'hdr': user_input.get('hdr') in ['true', 'True', '1', True],
                'style': user_input.get('style', 'aethertic'),
                'vintage_intensity': float(user_input.get('vintage_intensity', 0.5)),
                'negative_prompt': user_input.get('negative_prompt', 'blurry, low quality')
            }
        )

        # Batch processing
        batch_size = min(4, max(1, int(user_input.get('batch_size', 1))))
        
        # Upscaling
        if user_input.get('upscale') in ['true', 'True', '1', True]:
            params["upscale"] = "true"
            params["upscale_factor"] = min(4.0, max(1.0, float(user_input.get('upscale_factor', 2.0))))

        # Encode the final prompt
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        
        # Add batch_size to params
        params["batch_size"] = batch_size
        
        # Make request to pollinations.ai
        response = requests.get(url, params=params, timeout=300)
        response.raise_for_status()
        
        # Return image response
        return Response(
            response.content,
            mimetype='image/jpeg',
            headers={
                'X-RateLimit-Remaining': f"{MAX_FREE_DAILY - usage_tracker[ip]['daily_count']}/{MAX_FREE_MONTHLY - usage_tracker[ip]['monthly_count']}",
                'Cache-Control': 'no-store'
            }
        )

    except Exception as e:
        app.logger.error(f"Image generation failed: {str(e)}")
        return jsonify({'error': 'Image generation failed', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)
