#!/bin/bash
# ABOUTME: Renews the m24tom.com certificate and puts the files where nginx reads them.
# ABOUTME: Run with sudo from the site directory; stops at the first error.

set -e

# Configuration - Relative paths
BASE_DIR="server/certbot/conf"
LIVE_ROOT="$BASE_DIR/live"
ARCHIVE_ROOT="$BASE_DIR/archive"
DOMAIN="m24tom.com"
YAML_FILE="docker-certbot.yaml"

# 1. Run Docker Compose Certbot Dry Run
echo "--- Starting Certbot Dry Run ---"
docker compose -f "$YAML_FILE" run --rm certbot certonly --webroot \
    --webroot-path /var/www/certbot/ --dry-run -d "$DOMAIN"

read -p "Did the dry run succeed? (y/n): " confirm
if [[ $confirm != "y" ]]; then
    echo "Aborting."
    exit 1
fi

# 2. Run Actual Certbot Generation
echo "--- Running actual Certbot generation ---"
docker compose -f "$YAML_FILE" run --rm certbot certonly --webroot \
    --webroot-path /var/www/certbot/ -d "$DOMAIN"

# 3. Handle Directory Logic (Finding the highest -000n in archive/)
echo "Searching for the highest versioned directory (m24tom.com-########)..."

# Match ANY numeric suffix (so -0010, -0009, etc. are included)
HIGHEST_DIR=$(ls -1v "$ARCHIVE_ROOT" \
  | grep -E "^${DOMAIN}-[0-9]+$" \
  | tail -n 1)

if [ -z "$HIGHEST_DIR" ]; then
  echo "Error: No archive directory found for $DOMAIN in $ARCHIVE_ROOT"
  exit 1
fi

TARGET_ARCHIVE_DIR="$ARCHIVE_ROOT/$HIGHEST_DIR"
echo "Found highest versioned archive dir: $TARGET_ARCHIVE_DIR"

# Use the highest numbered certificate and the key that belongs to it
NUMBER=$(ls -1v "$TARGET_ARCHIVE_DIR" \
  | sed -nE 's/^fullchain([0-9]+)\.pem$/\1/p' \
  | tail -n 1)

for name in fullchain privkey; do
  if [ ! -f "$TARGET_ARCHIVE_DIR/$name$NUMBER.pem" ]; then
    echo "Error: $TARGET_ARCHIVE_DIR/$name$NUMBER.pem not found"
    exit 1
  fi
done

# 4. Backup current live directory
echo "Backing up current $LIVE_ROOT/$DOMAIN to $LIVE_ROOT/$DOMAIN.old..."
rm -rf "$LIVE_ROOT/$DOMAIN.old"
cp -a "$LIVE_ROOT/$DOMAIN" "$LIVE_ROOT/$DOMAIN.old"

# 5. Replace symlinks in live with physical files from that archive dir
echo "Replacing symlinks in $LIVE_ROOT/$DOMAIN with physical files from archive..."

# Make both copies before replacing anything, so a failed copy leaves the current files
for name in fullchain privkey; do
  cp "$TARGET_ARCHIVE_DIR/$name$NUMBER.pem" "$LIVE_ROOT/$DOMAIN/$name.pem.copy"
done

# Optional but usually correct permissions:
chmod 600 "$LIVE_ROOT/$DOMAIN/privkey.pem.copy"
chmod 644 "$LIVE_ROOT/$DOMAIN/fullchain.pem.copy"

for name in fullchain privkey; do
  mv -f "$LIVE_ROOT/$DOMAIN/$name.pem.copy" "$LIVE_ROOT/$DOMAIN/$name.pem"
done

# --- Requested Check ---
echo "--- Contents of $LIVE_ROOT/$DOMAIN ---"
ls -la "$LIVE_ROOT/$DOMAIN"
echo "--------------------------------------------------"

# 6. Restart Docker
# A failed restart continues to the question below, which offers the rollback
echo "Restarting Docker services..."
docker compose restart || echo "Error: restart failed. Answer n below to roll back."

# 7. Verification
echo "------------------------------------------------"
echo "ACTION REQUIRED: Check https://$DOMAIN in your browser."
read -p "Is the website responding correctly with SSL? (y/n): " ssl_ok

# 8. Cleanup
if [[ $ssl_ok == "y" ]]; then
    echo "Cleaning up backup..."
    rm -rf "$LIVE_ROOT/$DOMAIN.old"
    echo "Success! Certificates are now physical files in the live directory."
else
    echo "Rollback initiated..."
    rm -rf "$LIVE_ROOT/$DOMAIN"
    mv "$LIVE_ROOT/$DOMAIN.old" "$LIVE_ROOT/$DOMAIN"
    docker compose restart
    echo "Rollback complete. Previous state restored."
fi
