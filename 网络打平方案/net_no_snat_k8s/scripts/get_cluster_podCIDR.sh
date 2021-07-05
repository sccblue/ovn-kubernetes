kubectl -n ovn-kubernetes get configmaps ovn-config -o=jsonpath={.data.net_cidr}
