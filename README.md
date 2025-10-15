# cftunnel
Tools for creating and managing CloudFlare ZeroTrust tunnels

Run `cloudflared tunnel login` first, then run:-

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io
```

To specify the exact sub-domain or reuse existing sub-domain:-

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io --subdomain flyby-extension-stargate
```

## Access Authentication

You can add email-based OTP (One-Time Password) authentication to your tunnel using Cloudflare Access:

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io --subdomain flyby-extension-stargate --access-email=*@mycompany.com
```

### API Token Setup

**Important:** While `cloudflared login` authenticates you for tunnel operations, creating Cloudflare Access applications requires additional API permissions.

You need to set the `CLOUDFLARE_API_TOKEN` environment variable with a token that has Access permissions:

```
export CLOUDFLARE_API_TOKEN='your-api-token-here'
```

You can create an API token at: https://dash.cloudflare.com/profile/api-tokens

The API token needs the following permissions:
- Account > Cloudflare Access > Edit
- Zone > Zone > Read

**Why is this needed?** The cert.pem file from `cloudflared login` is an origin certificate for tunnel authentication. It doesn't include permissions to manage Zero Trust Access applications, which are part of Cloudflare's security features and require explicit API access.

### Bypass Paths

You can specify certain paths that should bypass authentication:

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io --subdomain flyby-extension-stargate --access-email=*@mycompany.com --access-path-bypass=/api/stripe/ --access-path-bypass=/webhooks/
```

Users accessing paths like `/api/stripe/` or `/webhooks/` will not need to authenticate, while all other paths will require email OTP verification.

### Removing Access Applications

When you no longer need access authentication for a domain, you can remove all Access Applications with a single command:

```
python cftunnel.py --remove-access --domain kafkai.io --subdomain flyby-extension-stargate
```

This will:
- Remove the main Access Application for the domain
- Remove any bypass applications for paths (e.g., `/api/stripe/`)
- Clean up all associated policies

**Note:** You need `CLOUDFLARE_API_TOKEN` set and the `--subdomain` parameter to specify which domain to clean up.
