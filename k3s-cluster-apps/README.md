### Install FluxCD

#### Bootstrap FluxCD

`kubectl apply --server-side --kustomize ./bootstrap/flux`

#### Create and add SOPS secret with `age`
`age-keygen -o age.agekey`

```
cat age.agekey |\
kubectl -n flux-system create secret generic sops-age \
--from-file=age.agekey=/dev/stdin
```

#### Create GitHub deploy key
*identity*:  as private key  
*identity.pub*: as public key  
*known_hosts*: as github.com SSH public keys  

```
export GH_SSH=$(ssh-keyscan github.com)
kubectl create secret generic flux-system --from-file=identity=./private --from-file=identity.pub=./public.pub --from-literal=known_hosts=$GH_SSH --namespace flux-system
```

#### Encrypt secrets with SOPS
<details>
<summary>Create single secret</summary>  

##### Create single secret
```
kubectl -n myns create secret generic my-secret \
  --from-literal=user=admin \
  --from-literal=password=change-me \
  --dry-run=client \
  -o yaml > secret.yaml
```  

---
</details>

<details>
<summary>Create cluster wide secret</summary>  

##### Create cluster wide secret
```
kubectl -n flux-system create secret generic cluster-secrets \
  --from-env-file=./cluster-secrets.txt \
  --dry-run=client \
  -o yaml > cluster-secrets.yaml
```  

---
</details>

##### Encrypt
```
sops \
  --age=age15h7jhdq9xjgf58pjs6qm8zc0r9h6d8zezvg8ghtj748dcjhwkf2spa6cms \
  --encrypt \
  --encrypted-regex '^(data|stringData)$' \
  --in-place cluster-secrets.yaml
```

#### Start FluxCD
Apply **agekey secret**, **github deploy secret** and **cluster-secrets** to the cluster.

```
sops --decrypt ./bootstrap/flux/age.agekey.encoded.yaml | kubectl apply -f -
sops --decrypt ./bootstrap/flux/github-deploy-key.encoded.yaml | kubectl apply -f -
sops --decrypt ./flux/variables/cluster-secrets.encoded.yaml | kubectl apply -f -
```

Then apply the config and start Flux on the Repo:
`kubectl apply --server-side --kustomize ./flux/config`
