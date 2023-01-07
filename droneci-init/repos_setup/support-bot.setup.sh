#!/usr/bin/env bash
source ~/.config/drone/config
REPO="zaggash/support-bot"
if ! drone repo info "$REPO" > /dev/null;then echo "Repo error !" && exit 1; fi

echo "Activate the Repo"
drone repo enable "$REPO"

sleep 3

if ! $(drone repo ls --active | grep -q $REPO)
then
  echo "Set Repo Options:"
  drone repo update \
    --timeout "15m" --visibility private \
    --ignore-forks \
    --trusted \
    --auto-cancel-pushes --auto-cancel-pull-requests \
    "$REPO"
fi
