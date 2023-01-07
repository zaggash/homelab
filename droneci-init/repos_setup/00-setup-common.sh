#!/usr/bin/env bash
set -e
source ~/.config/drone/config
#export BW_SESSION=""
bw login --check
bw sync

### SSH Key for deployment
if ! $(drone orgsecret ls zaggash | grep -q CI_SSH_KEY)
then
  echo -n "Adding GH Drone SSH Key... "
  drone orgsecret add  -- "zaggash" "CI_SSH_KEY" @"$HOME/.ssh/SSH_drone_github"
  echo "ok"
fi

### Telegram Creds
if ! $(drone orgsecret ls zaggash | grep -q TELEGRAM_TOKEN) 
then
  echo -n "Adding Telegram Seedbox Group Token... "
  drone orgsecret add -- "zaggash" "TELEGRAM_TOKEN" "$(bw get item Telegram | jq -r '.fields[] |  select(.name=="SEEDBOX_TOKEN") | .value')"
  echo "ok"
fi

if ! $(drone orgsecret ls zaggash | grep -q TELEGRAM_GROUPID)
then 
  echo -n "Adding Telegram Seedbox GroupID... "
  drone orgsecret add -- "zaggash" "TELEGRAM_GROUPID" "$(bw get item Telegram | jq -r '.fields[] |  select(.name=="SEEDBOX_GROUPID") | .value')"
  echo "ok"
fi

### Discord Webhook Global
if ! $(drone orgsecret ls zaggash | grep -q GLOBAL_CI_DISCORD_ID)
then
  echo -n "Adding Global CI Discord WEBHOOK_ID... "
  drone orgsecret add -- "zaggash" "GLOBAL_CI_DISCORD_ID" "$(bw get item discord.com | jq -r '.fields[] |  select(.name=="GLOBAL_CI_DISCORD_ID") | .value')"
  echo "ok"
fi
if ! $(drone orgsecret ls zaggash | grep -q GLOBAL_CI_DISCORD_TOKEN)
then
  echo -n "Adding Global CI Discord WEBHOOK_TOKEN... "
  drone orgsecret add -- "zaggash" "GLOBAL_CI_DISCORD_TOKEN" "$(bw get item discord.com | jq -r '.fields[] |  select(.name=="GLOBAL_CI_DISCORD_TOKEN") | .value')"
  echo "ok"
fi

### Docker registry 
if ! $(drone orgsecret ls zaggash | grep -q DOCKER_USERNAME)
then 
  echo -n "Adding zaggash DockerHub Username... "
  drone orgsecret add -- "zaggash" "DOCKER_USERNAME"  "$(bw get username docker.com)"
  echo "ok"
fi
if ! $(drone orgsecret ls zaggash | grep -q DOCKER_PASSWORD)
then 
  echo -n "Adding zaggash DockerHub Password... "
  drone orgsecret add -- "zaggash" "DOCKER_PASSWORD"  "$(bw get password docker.com)"
  echo "ok"
fi

echo "Script Done..."
