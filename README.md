# cftunnel
Tools for creating and managing CloudFlare ZeroTrust tunnels

Run `cloudflared tunnel login` first, then run:-

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io
```

To specify the exact sub-domain or reuse existing sub-domain:-

```
python cftunnel.py --url http://localhost:8000 --domain kafkai.io --sub-domain flyby-extension-stargate
```
