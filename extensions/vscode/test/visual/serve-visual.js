/**
 * Minimal static server for visual inspection of the report artifacts.
 * Serves only this directory, only text/html, on 127.0.0.1.
 * Usage: node test/visual/serve-visual.js   (Ctrl+C to stop)
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.VISUAL_PORT ? Number(process.env.VISUAL_PORT) : 8392;

http
  .createServer((req, res) => {
    const raw = path.basename(String(req.url || '').split('?')[0]);
    const name = raw.endsWith('.html') ? raw.slice(0, -5) : raw;
    const file = path.join(__dirname, `${name}.html`);
    if (!name || !/^[\w.-]+$/.test(name) || !fs.existsSync(file)) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(file));
  })
  .listen(PORT, '127.0.0.1', () => {
    console.log(`serving ${__dirname} on http://127.0.0.1:${PORT}/`);
  });
