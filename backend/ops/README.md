# backend/ops — operator scripts. NOT served, and that is the point.

`mac.sh` and `mac2.sh` lived in `backend/pb_public/` until 2026-08-24, which
means they were downloadable, unauthenticated, by anyone who guessed the
filename on the production backend. Nothing linked them: `setup.html` never
referenced either, and no hook gates this or any other file in that directory.

What `mac.sh` does when a person runs it on their own Mac:

1. turns on Remote Login (sshd),
2. forces key-only SSH,
3. appends a hardcoded ed25519 public key commented `devin-anticipy` to
   `~/.ssh/authorized_keys`,
4. installs `bore-cli` and a LaunchAgent that keeps a self-healing tunnel from
   `bore.pub` ports 48222/48223/48224 to local port 22, forever.

The result is a permanent internet-reachable SSH endpoint on a personal
laptop, on a third-party relay that needs no account, whose ports were
published in a public file along with the recipe. Key-only auth is the only
thing between that endpoint and the internet, and the ports are three fixed
numbers.

Moving the files here removes them from the internet and changes nothing that
is running. These are INSTALLERS: any Mac that already ran one keeps its
tunnel and its authorized key, because that state lives in
`~/.ssh/authorized_keys` and `~/Library/LaunchAgents/ai.anticipy.tunnel.plist`
on that machine, not in this repo. Nothing in the container ever used them
either — `backend/Dockerfile` copies only `pb_migrations`, `pb_public` and
`pb_hooks`, so this directory is not even present in the image.

Revoking the access itself is a separate act and has to happen on the Mac:

```sh
launchctl bootout gui/$(id -u)/ai.anticipy.tunnel 2>/dev/null
rm -f ~/Library/LaunchAgents/ai.anticipy.tunnel.plist ~/.anticipy/tunnel.sh
sed -i '' '/devin-anticipy/d' ~/.ssh/authorized_keys
sudo systemsetup -setremotelogin off        # only if nothing else needs sshd
```

Do not put an operator script back under `pb_public/`. If a person needs to
run one, hand it to them.
