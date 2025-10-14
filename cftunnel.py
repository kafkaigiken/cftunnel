#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import random
import uuid
import re

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

    args = parser.parse_args()

    local_url = args.url
    base_domain = args.domain
    custom_subdomain = args.subdomain

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
