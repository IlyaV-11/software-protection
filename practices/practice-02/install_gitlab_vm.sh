#!/usr/bin/env bash
# Выполняется только внутри отдельной учебной Ubuntu-машины.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

printf '\nЭТАП 1. ПАРАМЕТРЫ UBUNTU\n'
cat /etc/os-release
uname -m
free -h
df -h /

printf '\nЭТАП 2. ОБНОВЛЕНИЕ И ЗАВИСИМОСТИ\n'
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y curl openssh-server ca-certificates tzdata perl git docker.io
printf '%s\n' 'postfix postfix/mailname string gitlab.local' 'postfix postfix/main_mailer_type select Internet Site' | sudo debconf-set-selections
sudo apt-get install -y postfix
sudo systemctl enable --now docker

printf '\nЭТАП 3. ОФИЦИАЛЬНЫЕ РЕПОЗИТОРИИ GITLAB И RUNNER\n'
curl --fail --show-error --silent --location https://packages.gitlab.com/install/repositories/gitlab/gitlab-ce/script.deb.sh -o /tmp/gitlab-ce-repository.sh
sudo bash /tmp/gitlab-ce-repository.sh
curl --fail --show-error --silent --location https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh -o /tmp/gitlab-runner-repository.sh
sudo bash /tmp/gitlab-runner-repository.sh

printf '\nЭТАП 4. КОНФИГУРАЦИЯ И УСТАНОВКА\n'
sudo install -d -m 0700 /etc/gitlab
sudo tee /etc/gitlab/gitlab.rb >/dev/null <<'GITLAB'
external_url 'http://127.0.0.1:8929'
gitlab_rails['gitlab_shell_ssh_port'] = 2222
puma['worker_processes'] = 0
sidekiq['concurrency'] = 10
GITLAB
sudo env EXTERNAL_URL='http://127.0.0.1:8929' DEBIAN_FRONTEND=noninteractive apt-get install -y gitlab-ce gitlab-runner

printf '\nЭТАП 5. ПРОВЕРКА СЛУЖБ\n'
sudo gitlab-ctl status
sudo gitlab-runner --version
sudo gitlab-runner status
sudo docker version
git --version
