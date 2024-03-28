#!/usr/bin/env bash

### Current Node IP to setup as first script argument.
IP="$1"

### User setup in the destination node
USER="core"

### SAN used as LB for the ControlPlane/Server nodes.
LB="master.k3s.home.lan"

### IP of the first k3s server node
MASTER0="192.168.1.20"

### k3s version to install
K3S_VERSION=" v1.24.4+k3s1"

### kubeconfig context to merge in $HOME/.kube/config
CONTEXT="homelab/admin"

### S3 credentials for k3s etcd backups
S3_ACCESS_KEY=$(bw get item s3.home.lan | jq -r '.fields[] | select(.name | contains("k3s")) | .name')
S3_SECRET_KEY=$(bw get item s3.home.lan | jq -r '.fields[] | select(.name | contains("k3s")) | .value')

### Custom k3s options
MASTER_EXTRA_ARGS="\
--disable servicelb \
--disable traefik \
--disable local-storage \
--disable-cloud-controller \
--disable-network-policy \
--etcd-snapshot-retention 28 \
--etcd-s3 \
--etcd-s3-skip-ssl-verify \
--etcd-s3-endpoint s3.home.lan:9000 \
--etcd-s3-access-key $S3_ACCESS_KEY \
--etcd-s3-secret-key $S3_SECRET_KEY \
--etcd-s3-bucket k3s-cluster-backup \
"

## ----------------------------------- ##
### Setup command to build the cluster
## ----------------------------------- ##
echo "Copy paste the required commands below to bootsrap the node:"
echo "------------------------------------------------------------"
echo "$0 [node-IP]"
echo

echo "Download k3sup:"
version=$(curl -sI https://github.com/alexellis/k3sup/releases/latest | grep -i "location:" | awk -F"/" '{ printf "%s", $NF }' | tr -d '\r')
url=https://github.com/alexellis/k3sup/releases/download/$version/k3sup 
echo "curl -sSL $url --output 'k3sup' && chmod +x k3sup"
echo

echo "**First** Server node:"
echo ./k3sup install --ip $MASTER0 --tls-san $LB --k3s-version $K3S_VERSION --merge --local-path $HOME/.kube/config --context $CONTEXT --cluster --k3s-extra-args \'$MASTER_EXTRA_ARGS\' --sudo --user $USER
echo

echo "New Server node"
echo ./k3sup join --server --server-ip $MASTER0 --ip $IP --k3s-version $K3S_VERSION --sudo --user core
echo

echo "New Agent node"
echo ./k3sup join --server-ip $MASTER0 --ip $IP --k3s-version $K3S_VERSION --sudo --user core
echo

echo "Regenerate kubeconfig"
echo ./k3sup install --skip-install --ip $MASTER0 --sudo --user $USER --merge --local-path $HOME/.kube/config --context $CONTEXT 
echo
