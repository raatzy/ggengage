#!/bin/bash
# Web Gecko Social Post Manager — server install script
# Run as root on your VPS: bash deploy/install.sh

set -e

APP_DIR=/var/www/webgecko-social
PYTHON=python3

echo "==> Creating app directory"
mkdir -p $APP_DIR
cp -r . $APP_DIR/
cd $APP_DIR

echo "==> Creating virtual environment"
$PYTHON -m venv venv
venv/bin/pip install --quiet -r requirements.txt

echo "==> Creating data directories"
mkdir -p data/images

echo "==> Setting up .env"
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  IMPORTANT: Edit $APP_DIR/.env and fill in your credentials before starting."
    echo ""
fi

echo "==> Installing systemd service"
cp deploy/webgecko-social.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable webgecko-social

echo "==> Installing nginx config"
cp deploy/nginx.conf /etc/nginx/sites-available/webgecko-social
ln -sf /etc/nginx/sites-available/webgecko-social /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo ""
echo "Done. Next steps:"
echo "  1. Edit /var/www/webgecko-social/.env"
echo "  2. Run:  certbot --nginx -d social.webgecko.com.au"
echo "  3. Run:  systemctl start webgecko-social"
echo "  4. Visit https://social.webgecko.com.au"
