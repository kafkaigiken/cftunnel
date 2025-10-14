#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import random
import uuid
import re
import json
import requests
from typing import Optional, List

# --- Configuration Variables ---
CONFIG_DIR = os.path.expanduser("~/.cloudflared")
CERT_FILE = os.path.join(CONFIG_DIR, "cert.pem")

# Word lists for generating memorable subdomains
WORD_LIST_1 = ["bridge", "connect", "secure", "proxy", "global"]
WORD_LIST_2 = ["fast", "agile", "tunnel", "link", "cloud"]
WORD_LIST_3 = ["node", "app", "service", "gateway", "extension"]

def generate_subdomain():
    """Generates a unique, three-word subdomain."""
    word1 = random.choice(WORD_LIST_1)
    word2 = random.choice(WORD_LIST_2)
    word3 = random.choice(WORD_LIST_3)
    # Append a short unique ID to avoid collisions
    unique_id = str(uuid.uuid4())[:4]
    return f"{word1}-{word2}-{word3}-{unique_id}"

def get_api_token():
    """Get Cloudflare API token from cert.pem file or environment variable."""
    # First try environment variable
    token = os.environ.get('CLOUDFLARE_API_TOKEN')
    if token:
        return token
    
    # Try to extract from cert.pem (origin certificate)
    # Note: cert.pem is an origin certificate, not an API token
    # Users need to set CLOUDFLARE_API_TOKEN environment variable
    if not token:
        print("Warning: CLOUDFLARE_API_TOKEN environment variable not set.")
        print("To use access authentication, please set your Cloudflare API token:")
        print("export CLOUDFLARE_API_TOKEN='your-api-token'")
        print("You can create an API token at: https://dash.cloudflare.com/profile/api-tokens")
        return None
    
    return token

def get_account_id(api_token: str) -> Optional[str]:
    """Get Cloudflare account ID using the API."""
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get('https://api.cloudflare.com/client/v4/accounts', headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') and data.get('result'):
            # Return the first account ID
            return data['result'][0]['id']
        else:
            print(f"Failed to get account ID: {data.get('errors')}")
            return None
    except Exception as e:
        print(f"Error getting account ID: {e}")
        return None

def get_zone_id(api_token: str, domain: str) -> Optional[str]:
    """Get Cloudflare zone ID for a domain."""
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(
            f'https://api.cloudflare.com/client/v4/zones?name={domain}',
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') and data.get('result'):
            return data['result'][0]['id']
        else:
            print(f"Failed to get zone ID for domain {domain}: {data.get('errors')}")
            return None
    except Exception as e:
        print(f"Error getting zone ID: {e}")
        return None

def create_access_application(
    api_token: str,
    account_id: str,
    zone_id: str,
    app_name: str,
    domain: str,
    email_pattern: str,
    bypass_paths: Optional[List[str]] = None
) -> Optional[str]:
    """Create a Cloudflare Access Application with email OTP authentication."""
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    # Build the application configuration
    app_config = {
        'name': app_name,
        'domain': domain,
        'type': 'self_hosted',
        'session_duration': '24h',
        'auto_redirect_to_identity': False,
        'allowed_idps': [],  # Empty means use one-time PIN
        'cors_headers': {
            'enabled': False
        }
    }
    
    # Add path bypass if specified
    if bypass_paths:
        # For Zero Trust Access, we need to create the application without path exclusions
        # and handle them in the policy instead
        pass
    
    try:
        # Create the access application
        response = requests.post(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps',
            headers=headers,
            json=app_config
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') and data.get('result'):
            app_id = data['result']['id']
            print(f"Access application created with ID: {app_id}")
            
            # Create the access policy
            create_access_policy(api_token, account_id, app_id, email_pattern, bypass_paths)
            
            return app_id
        else:
            print(f"Failed to create access application: {data.get('errors')}")
            return None
    except Exception as e:
        print(f"Error creating access application: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"API Error Details: {error_data}")
            except:
                print(f"Response text: {e.response.text}")
        return None

def create_access_policy(
    api_token: str,
    account_id: str,
    app_id: str,
    email_pattern: str,
    bypass_paths: Optional[List[str]] = None
):
    """Create an access policy for the application with email domain matching."""
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    # Create the include rule for email pattern matching
    include_rules = [
        {
            'email': {
                'email': email_pattern
            }
        }
    ]
    
    # Main policy configuration
    policy_config = {
        'name': 'Email OTP Policy',
        'decision': 'non_identity',  # Use one-time PIN
        'include': include_rules
    }
    
    try:
        # Create the policy
        response = requests.post(
            f'https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps/{app_id}/policies',
            headers=headers,
            json=policy_config
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            print("Access policy created successfully")
        else:
            print(f"Failed to create access policy: {data.get('errors')}")
    except Exception as e:
        print(f"Error creating access policy: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"API Error Details: {error_data}")
            except:
                print(f"Response text: {e.response.text}")

def create_bypass_applications(
    api_token: str,
    account_id: str,
    zone_id: str,
    base_name: str,
    hostname: str,
    bypass_paths: List[str]
):
    """Create bypass Access Applications for specified paths.
    
    Cloudflare Access evaluates applications in order. Bypass applications
    for specific paths should be created with higher precedence.
    """
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    
    for path in bypass_paths:
        # Create a bypass application for this specific path
        full_path = f"{hostname}{path}"
        if not path.startswith('/'):
            full_path = f"{hostname}/{path}"
        
        app_config = {
            'name': f"{base_name} - Bypass {path}",
            'domain': full_path,
            'type': 'self_hosted',
            'session_duration': '24h',
            'auto_redirect_to_identity': False,
            'allowed_idps': [],
        }
        
        try:
            # Create the bypass application
            response = requests.post(
                f'https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps',
                headers=headers,
                json=app_config
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success') and data.get('result'):
                app_id = data['result']['id']
                print(f"Bypass application created for path {path} with ID: {app_id}")
                
                # Create a bypass policy for this application
                bypass_policy_config = {
                    'name': f'Bypass All for {path}',
                    'decision': 'bypass',
                    'include': [
                        {
                            'everyone': {}
                        }
                    ]
                }
                
                policy_response = requests.post(
                    f'https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps/{app_id}/policies',
                    headers=headers,
                    json=bypass_policy_config
                )
                policy_response.raise_for_status()
                policy_data = policy_response.json()
                
                if policy_data.get('success'):
                    print(f"Bypass policy created for path: {path}")
                else:
                    print(f"Warning: Failed to create bypass policy for {path}: {policy_data.get('errors')}")
            else:
                print(f"Warning: Failed to create bypass application for {path}: {data.get('errors')}")
        except Exception as e:
            print(f"Error creating bypass application for {path}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"API Error Details: {error_data}")
                except:
                    print(f"Response text: {e.response.text}")

def main():
    """Main function to parse arguments and create the tunnel."""

    # --- Initial Check & Instructions ---
    if not os.path.exists(CERT_FILE):
        print("--- IMPORTANT: One-Time Manual Setup Required ---")
        print("It seems you have not authenticated with Cloudflare yet.")
        print("Please run the following command in your terminal first:")
        print("cloudflared tunnel login")
        print("This will open a browser window for you to log in.")
        print("After successful login, run this script again.")
        print("-" * 20)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Automatically creates a Cloudflare tunnel.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--url",
        required=True,
        help="The local service URL (e.g., http://localhost:8000)"
    )
    parser.add_argument(
        "--domain",
        default="mydomain.io",
        help="Your domain name. (default: mydomain.io)"
    )
    parser.add_argument(
        "--subdomain",
        help="Optional custom subdomain. If not provided, one will be generated automatically."
    )
    parser.add_argument(
        "--access-email",
        help="Email pattern for access authentication (e.g., *@mycompany.com). Requires CLOUDFLARE_API_TOKEN."
    )
    parser.add_argument(
        "--access-path-bypass",
        action='append',
        help="Paths that bypass authentication (can be specified multiple times)."
    )

    args = parser.parse_args()

    local_url = args.url
    base_domain = args.domain
    custom_subdomain = args.subdomain
    access_email = args.access_email
    access_path_bypass = args.access_path_bypass

    # Use a custom subdomain or generate one automatically
    if custom_subdomain:
        subdomain_name = custom_subdomain
    else:
        subdomain_name = generate_subdomain()

    tunnel_name = subdomain_name
    public_hostname = f"{subdomain_name}.{base_domain}"

    print(f"--- Tunnel details ---")
    print(f"Tunnel Name: {tunnel_name}")
    print(f"Public URL: {public_hostname}")
    print(f"Local Service: {local_url}")
    if access_email:
        print(f"Access Email Pattern: {access_email}")
        if access_path_bypass:
            print(f"Bypass Paths: {', '.join(access_path_bypass)}")
    print("-" * 20)

    tunnel_uuid = None
    # --- Create the tunnel ---
    print("--- Creating or Verifying Cloudflare Tunnel ---")
    try:
        result = subprocess.run(
            ["cloudflared", "tunnel", "create", tunnel_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # New tunnel created, parse the UUID from stdout
        match = re.search(r'with id ([a-f0-9-]+)', result.stdout)
        if match:
            tunnel_uuid = match.group(1)
            print(f"Tunnel '{tunnel_name}' created successfully with ID {tunnel_uuid}.")
        else:
            print(f"Tunnel '{tunnel_name}' created, but could not retrieve its ID.")
            print("Attempting to get ID with 'info' command.")
            info_result = subprocess.run(
                ["cloudflared", "tunnel", "info", tunnel_name],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Check both stdout and stderr for the UUID with a more flexible pattern
            info_output = info_result.stdout + info_result.stderr
            match = re.search(r'(?:Tunnel ID|tunnel) ([a-f0-9-]+)', info_output)
            if match:
                tunnel_uuid = match.group(1)
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr:
            print(f"Tunnel '{tunnel_name}' already exists. Getting its ID...")
            # Tunnel already exists, get the UUID using the info command
            info_result = subprocess.run(
                ["cloudflared", "tunnel", "info", tunnel_name],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Check both stdout and stderr for the UUID with a more flexible pattern
            info_output = info_result.stdout + info_result.stderr
            match = re.search(r'(?:Tunnel ID|tunnel) ([a-f0-9-]+)', info_output)
            if match:
                tunnel_uuid = match.group(1)
                print(f"Found existing tunnel with ID {tunnel_uuid}.")
            else:
                print("Could not retrieve UUID for existing tunnel.")
                print("`cloudflared tunnel info` output for debugging:")
                print("STDOUT:", info_result.stdout)
                print("STDERR:", info_result.stderr)
                sys.exit(1)
        else:
            print(f"Error creating tunnel: {e.stderr}")
            sys.exit(1)

    if not tunnel_uuid:
        print("Failed to get tunnel ID. Exiting.")
        sys.exit(1)

    # Use the UUID to construct the correct credentials file path
    CREDENTIALS_FILE = os.path.join(CONFIG_DIR, f"{tunnel_uuid}.json")
    CONFIG_FILE = os.path.join(CONFIG_DIR, f"{tunnel_name}.yml")

    # --- Write configuration file ---
    print("--- Writing Configuration File ---")
    os.makedirs(CONFIG_DIR, exist_ok=True)

    config_content = f"""
tunnel: {tunnel_name}
credentials-file: {CREDENTIALS_FILE}

ingress:
  - hostname: {public_hostname}
    service: {local_url}
    originRequest:
      originServerName: {public_hostname}
  - service: http_status:404
"""
    with open(CONFIG_FILE, "w") as f:
        f.write(config_content)

    # --- Create DNS record ---
    print("--- Creating DNS Record ---")
    subprocess.run(["cloudflared", "tunnel", "route", "dns", tunnel_name, public_hostname], check=True)

    # --- Create Access Application if email pattern is specified ---
    if access_email:
        print("--- Creating Access Application ---")
        api_token = get_api_token()
        if api_token:
            account_id = get_account_id(api_token)
            zone_id = get_zone_id(api_token, base_domain)
            
            if account_id and zone_id:
                # Create bypass applications first (they should have higher priority)
                if access_path_bypass:
                    print("Creating bypass applications for specified paths...")
                    create_bypass_applications(
                        api_token,
                        account_id,
                        zone_id,
                        f"Access for {tunnel_name}",
                        public_hostname,
                        access_path_bypass
                    )
                
                # Create main access application
                app_id = create_access_application(
                    api_token,
                    account_id,
                    zone_id,
                    f"Access for {tunnel_name}",
                    public_hostname,
                    access_email,
                    access_path_bypass
                )
                if app_id:
                    print(f"Access application configured successfully!")
                    print(f"Users matching '{access_email}' will receive OTP codes to access the service.")
                    if access_path_bypass:
                        print(f"Paths {', '.join(access_path_bypass)} are configured to bypass authentication.")
                else:
                    print("Warning: Failed to create access application. Tunnel will be created without authentication.")
            else:
                print("Warning: Could not get account or zone ID. Tunnel will be created without authentication.")
        else:
            print("Warning: No API token available. Tunnel will be created without authentication.")
            print("To enable access authentication, set CLOUDFLARE_API_TOKEN environment variable.")

    # --- Run the tunnel ---
    print("--- Running the Tunnel ---")
    print("Press Ctrl+C to stop the tunnel.")
    try:
        subprocess.run(
            ["cloudflared", "tunnel", "--config", CONFIG_FILE, "run", tunnel_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except KeyboardInterrupt:
        print("\nTunnel stopped.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the tunnel: {e.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    main()
