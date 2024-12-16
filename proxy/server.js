const cors_proxy = require('cors-anywhere');
const PORT = 8080;

// Start the CORS Anywhere server
cors_proxy.createServer({
    originWhitelist: [], // Allow all origins
}).listen(PORT, () => {
    console.log(`CORS Proxy running on http://localhost:${PORT}`);
}).setTimeout(300000);
