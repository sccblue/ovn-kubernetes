kubectl get node -o=jsonpath="{range .items[*]}{.metadata.name}{' '}{.status.addresses[0].address}{'\n'}"
