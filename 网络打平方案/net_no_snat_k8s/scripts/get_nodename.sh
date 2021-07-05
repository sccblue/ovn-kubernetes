kubectl get node -o=jsonpath="{range .items[*]}{.metadata.name}{'\n'}"
