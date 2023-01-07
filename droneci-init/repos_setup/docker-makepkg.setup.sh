#!/usr/bin/env bash
source ~/.config/drone/config
REPO="zaggash/docker-makepkg"
if ! drone repo info "$REPO" > /dev/null;then echo "Repo error !" && exit 1; fi

echo "Activate the Repo"
drone repo enable "$REPO"

sleep 3

if ! $(drone repo ls --active | grep -q $REPO)
then
  echo "Set Repo Options"
  drone repo update \
    --timeout "60m" --visibility public \
    --ignore-forks --ignore-pull-requests \
    --auto-cancel-pushes --auto-cancel-pull-requests \
    "$REPO"
fi

echo "Add Cronjob: "
echo "trigger_build @weekly"
drone cron add --branch master "$REPO" trigger_build @weekly

