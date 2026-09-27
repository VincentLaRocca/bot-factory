# 5090 kit — run the lead system on your own machine

The escalation path when the cloud hits a wall (`[5090]` in the pipeline).
From this machine the inbound listener is always on (for forms, texts, and
Claude in Chrome), and local models (Ollama) are there for when scoring moves
past rules.

## One-time setup (Windows, PowerShell)

1. **Get the code**
   ```powershell
   cd $HOME
   git clone https://github.com/VincentLaRocca/bot-factory
   cd bot-factory; git checkout leads/full-lead-system   # until PR #10 is merged
   py -m pip install -e .
   ```
2. **Secrets:** copy `leads\deploy\5090\.env.example` to `.env` in the same folder, and fill it in.
   `LEADS_WEBHOOK_TOKEN` can be any long random string:
   `[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")`
3. **Tunnel.** Cloudflare is already set up on this machine (`~\.cloudflared`).
   - Stable address: follow the three commands at the top of `cloudflared.example.yml`, then save it as `cloudflared.yml`.
   - Just trying it: skip that and use `start-tunnel.ps1 -Quick` (prints a random `trycloudflare.com` URL).
4. **Try it**
   ```powershell
   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\start-leads.ps1     # window 1
   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\start-tunnel.ps1    # window 2
   ```
   Open `https://<tunnel-host>/health` (expect `{"status": "ok"}`), then
   `https://<tunnel-host>/intake?token=<token>` and send a test lead.
5. **Always on:** run `install-autostart.ps1` once from an admin PowerShell.
   Both start at login and restart if they fall over.

## Day to day

- Log: `data\leads.log` · store: `data\leads.db`
- Last leads: `py -m leads --store data\leads.db recent`
- Force a sweep now: `py -m leads --store data\leads.db sweep --force`
- Claude in Chrome posts its finds at `https://<tunnel-host>/intake?token=…`
  (playbook: `pipeline/lead-system/chrome-listener.md`)

## Which scheduler runs what

GitHub Actions sweeps email, Reddit replies and SAM.gov, and sends the digest.
This machine runs the inbound listener, plus any RSS feeds you turn on. If both
end up sweeping the same listener, the board rejects the repeats.
