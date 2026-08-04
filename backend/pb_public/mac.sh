set -e

# 1. Turn on Remote Login (SSH) — will ask for your Mac password once
sudo systemsetup -setremotelogin on

# 2. Key-only SSH: passwords can never be guessed through the tunnel
sudo mkdir -p /etc/ssh/sshd_config.d
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/100-anticipy.conf >/dev/null
sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null || true

# 3. Devin's key (the ONLY key that can get in)
mkdir -p ~/.ssh && chmod 700 ~/.ssh
grep -q "devin-anticipy" ~/.ssh/authorized_keys 2>/dev/null || \
  echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPEpa0y0aJBN6ApKACjvZiT2w0d3K5hiy3ezQNpsdfcC devin-anticipy" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 4. The tunnel program (free, no account, no login)
export PATH=/opt/homebrew/bin:$PATH
command -v bore >/dev/null || brew install bore-cli

# 5. A tunnel that starts itself at login and heals itself forever
mkdir -p ~/.anticipy
cat > ~/.anticipy/tunnel.sh <<'EOF'
#!/bin/bash
export PATH=/opt/homebrew/bin:$PATH
while true; do
  for p in 48222 48223 48224; do
    bore local 22 --to bore.pub --port $p
    sleep 5
  done
  sleep 10
done
EOF
chmod +x ~/.anticipy/tunnel.sh

cat > ~/Library/LaunchAgents/ai.anticipy.tunnel.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.anticipy.tunnel</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>$HOME/.anticipy/tunnel.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/anticipy-tunnel.log</string>
  <key>StandardErrorPath</key><string>/tmp/anticipy-tunnel.log</string>
</dict></plist>
EOF
launchctl bootout gui/$(id -u)/ai.anticipy.tunnel 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.anticipy.tunnel.plist

# 6. Keep the keychain open so builds can sign over SSH
#    (asks for your Mac password once)
security unlock-keychain ~/Library/Keychains/login.keychain-db
security set-keychain-settings ~/Library/Keychains/login.keychain-db

sleep 5 && tail -2 /tmp/anticipy-tunnel.log
echo "ANTICIPY_ACCESS_READY"
