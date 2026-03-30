#!/bin/sh
set -eu

# --- Install dockeruser's public key (if provided) ---
if [ "${DOCKERUSER_PUBLIC_KEY:-}" != "" ]; then
  mkdir -p /home/dockeruser/.ssh
  chmod 700 /home/dockeruser/.ssh
  printf '%s\n' "$DOCKERUSER_PUBLIC_KEY" > /home/dockeruser/.ssh/authorized_keys
  chown -R dockeruser:dockeruser /home/dockeruser/.ssh
  chmod 600 /home/dockeruser/.ssh/authorized_keys
  install -d -m 755 /etc/ssh/authorized_keys
  printf '%s\n' "$DOCKERUSER_PUBLIC_KEY" > /etc/ssh/authorized_keys/dockeruser
  chmod 644 /etc/ssh/authorized_keys/dockeruser
fi

# --- Start the nested Docker daemon in the background ---
if command -v /usr/local/bin/dockerd-entrypoint.sh > /dev/null 2>&1; then
  /usr/local/bin/dockerd-entrypoint.sh dockerd > /var/log/dockerd.log 2>&1 &
else
  dockerd-entrypoint.sh dockerd > /var/log/dockerd.log 2>&1 &
fi

ssh-keygen -A > /dev/null 2>&1 || true

# Wait up to 30 s for the nested daemon.
for i in $(seq 1 60); do
  if docker version > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# --- Harden sshd ---
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/g' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/g' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/g' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/g' /etc/ssh/sshd_config
sed -i 's|^#\?AuthorizedKeysFile.*|AuthorizedKeysFile /etc/ssh/authorized_keys/%u .ssh/authorized_keys|g' /etc/ssh/sshd_config
sed -i 's/^#\?StrictModes.*/StrictModes no/g' /etc/ssh/sshd_config
printf '\nPasswordAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\nListenAddress 0.0.0.0\n' \
  >> /etc/ssh/sshd_config
sed -i 's/^#\?AllowTcpForwarding.*/AllowTcpForwarding yes/g' /etc/ssh/sshd_config
sed -i 's|^#\?Subsystem[[:space:]]\+sftp.*|Subsystem sftp /usr/lib/ssh/sftp-server|g' /etc/ssh/sshd_config

mkdir -p /var/run/sshd
chmod 700 /home/dockeruser || true
chown dockeruser:dockeruser /home/dockeruser || true

usermod -U dockeruser > /dev/null 2>&1 || true
passwd -u dockeruser > /dev/null 2>&1 || true

if ! /usr/sbin/sshd -t; then
  echo "sshd configuration test failed" >&2
  exit 1
fi

exec /usr/sbin/sshd -D -e
