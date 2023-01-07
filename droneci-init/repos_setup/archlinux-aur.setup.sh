#!/usr/bin/env bash
source ~/.config/drone/config
REPO="zaggash/archlinux-aur"
if ! drone repo info "$REPO" > /dev/null;then echo "Repo error !" && exit 1; fi

bw login --check
bw sync

echo "Activate the Repo"
drone repo enable "$REPO"

sleep 3

if ! $(drone repo ls --active | grep -q $REPO)
then
  echo -n "Set Repo Options"
  drone repo update \
    --trusted --timeout "120m" --visibility public \
    --ignore-forks --ignore-pull-requests \
    --auto-cancel-pushes --auto-cancel-pull-requests \
    "$REPO"
fi

if ! $(drone secret ls "$REPO" | grep -q PGP_KEY)
then
  echo -n "Adding PGP Key... "
  drone secret add --repository "$REPO" --name "PGP_KEY" --data "$(keybase pgp export -q 54231a262e8bf5501c6945d275bcc090ca185c57 --secret --unencrypted | base64 -w0)"
  echo "ok"
fi

if ! $(drone secret ls "$REPO" | grep -q GIT_TOKEN)
then
  echo -n "Adding GIT Token... "
  drone secret add --repository "$REPO" --name "GIT_TOKEN" --data "$(bw get item github.com | jq -r '.fields[] | select(.name=="REPO_CI_TOKEN") | .value')"
  echo "ok"
fi

echo "Add Cronjobs [https://crontab.guru]: "
echo "check_updates At 01:00 on every day-of-week from Monday through Saturday."
drone cron add --branch 'master' "$REPO" 'check_updates' '0 0 1 * * 1-6'
echo "full_build At 01:00 on Sunday."
drone cron add --branch 'master' "$REPO" 'full_build' '0 0 1 * * 0'
