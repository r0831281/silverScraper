const cors_proxy = require('cors-anywhere');
const PORT = 8080;

// Start the CORS Anywhere server
cors_proxy.createServer({
    originWhitelist: [], // Allow all origins
    setHeaders: {
        'Accept-Language': 'nl,en;q=0.9,fr;q=0.8'
    },
    handleInitialRequest: (req, res, location) => {
        // Ensure Accept-Language header is set for Dutch content
        if (!req.headers['accept-language']) {
            req.headers['accept-language'] = 'nl,en;q=0.9,fr;q=0.8';
        }
        return false; // Continue with the request
    }
}).listen(PORT, () => {
    console.log(`CORS Proxy running on http://localhost:${PORT}`);
    console.log(`Headers will include: Accept-Language: nl,en;q=0.9,fr;q=0.8`);
}).setTimeout(300000);
