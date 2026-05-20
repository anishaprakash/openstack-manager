#!/bin/bash

# Export OpenStack credentials to .env file

echo "Please enter your OpenStack Password: "
read -sr OS_PASSWORD_INPUT

cat > .env <<EOF
# OpenStack Configuration
OS_AUTH_URL=https://auth.cloud.ovh.net/v3
OS_IDENTITY_API_VERSION=3
OS_USER_DOMAIN_NAME=Default
OS_PROJECT_DOMAIN_NAME=Default
OS_TENANT_ID=4b8d5297f6264b499baa8c8104c17a90
OS_TENANT_NAME=9263834841940127
OS_USERNAME=user-qwBVpMWShgxC
OS_PASSWORD=$OS_PASSWORD_INPUT
OS_REGION_NAME=CA-EAST-TOR

# API Configuration
API_KEY=changeme
DEBUG=false
EOF

echo "✓ Exported credentials to .env"
chmod 600 .env
echo "✓ Set .env permissions to 600 (user read/write only)"
