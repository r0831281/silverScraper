import time
import requests
from flask import Flask, request, Response
from urllib.parse import urlparse

app = Flask(__name__)

# Proxy route to forward the request
@app.route('/<path:url>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(url):
    # Rebuild the full target URL from the path
    # This will correctly handle https:// in the target URL
    target_url = f"https://{url}" if not url.startswith('https://') else f"http://{url}"

    # Get the method (GET, POST, etc.)
    method = request.method
    
    # Forward the request to the target server using the requests library
    try:
        if method == 'GET':
            response = requests.get(target_url, params=request.args, headers=request.headers)
        elif method == 'POST':
            response = requests.post(target_url, data=request.form, headers=request.headers)
        elif method == 'PUT':
            response = requests.put(target_url, data=request.form, headers=request.headers)
        elif method == 'DELETE':
            response = requests.delete(target_url, headers=request.headers)
        
        # Return the response from the target server back to the client
        return Response(response.content, status=response.status_code, content_type=response.headers['Content-Type'])
    except requests.RequestException as e:
        # If the request fails, return an error
        return f"Error fetching page: {e}", 500


def run():
    app.run(host='127.0.0.1', port=8080, debug=False)

if __name__ == '__main__':
    run()
