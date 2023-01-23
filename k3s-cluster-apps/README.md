#### Bootstrap flux
Remove repo deploy SSH key from Github repo if it exists, it'll be redeployed  

```
flux bootstrap github \
  --owner=zaggash \
  --repository=homelab \
  --path=k3s-cluster-apps/init \
  --read-write-key \
  --personal \
  --private=false \
  --author-name ZaggBot \
  --author-email 101278001+ZaggBot@users.noreply.github.com
 ```

#### Create and add SOPS secret with `age`
`age-keygen -o age.agekey`

```
cat age.agekey |\
kubectl -n flux-system create secret generic sops-age \
--from-file=age.agekey=/dev/stdin
```

#### Encrypt secrets with SOPS
<details>
<summary>Create single secret</summary>  

---
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

---
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
