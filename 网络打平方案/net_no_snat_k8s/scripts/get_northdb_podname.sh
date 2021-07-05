kubectl -n ovn-kubernetes get pod -o=jsonpath='{range .items[*]}{.metadata.name}{"\n"}' | grep ovnkube-db
