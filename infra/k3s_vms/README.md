Quick VMs setup while waiting on a Terraform provider for Truenas Scale VM provisionning  

# Write image to remote block device.  
  
### On Truenas  
#### Export block device  

```
qemu-nbd --export-name=remote-truenas /path/to/block/device -f raw  
```

### On my Machine  
#### Mount remote device locally  

```
sudo modprobe nbd  
sudo nbd-client -n -N remote-truenas truenas.ip.or.dns  
```
  
#### Download flatcar installer  

```
wget https://raw.githubusercontent.com/flatcar-linux/init/flatcar-master/bin/flatcar-install  
chmod +x flatcar-install  
```
  
#### Create butane init file  

```
docker run -i --rm quay.io/coreos/butane:release --pretty --strict < cloud-init/config.yaml > cloud-init/config.ign  
```
  
#### Write data  

```
sudo ./flatcar-install -d /dev/nbd0 -i cloud-init/config.ign  
sudo nbd-client -d /dev/nbd0  
rm -f flatcar-install cloud-init/config.ign  
```
  
# Build k3s cluster  
Use the script [bootstrap_k3s.sh](https://github.com/zaggash/homelab/blob/main/infra/k3s_vms/bootstrap_k3s.sh) to setup the k3s cluster.  
  
# Add Cluster app  
Follow instruction on the [k3s-cluster-apps folder](https://github.com/zaggash/homelab/tree/main/k3s-cluster-apps) to sync FluxCD to the cluster.  

