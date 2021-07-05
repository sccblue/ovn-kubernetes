# 最原始的自行编译ovn-kubernetes网络插件
# 已经在kubernetes 1.19.9(最后一个docker版本的k8s） 和 1.21.2(当前最新版，使用containerd作为容器运行时CRI）
# 编译机环境  centos7.8.2003  内核版本 3.10.0-1062.18.1.el7.x86_64
# 基础组件版本
    openvswitch 2.15.0
    ovn-21.06.0
    ovn-kubernetes commit_id cda525710b984ad23b23dc69c6f52966367f192a Wed Jun 30 08:47:24 2021
    
# 准备工作
    yum install -y gcc rpm-build
    yum install -y rpm-build
    yum install -y unbound unbound-devel
    yum install -y autoconf gcc-c++ automake openssl-devel 
    yum install -y desktop-file-utils groff graphviz
    yum install -y checkpolicy libcap-ng-devel selinux-policy-devel
    yum install -y /usr/bin/sphinx-build-3 # 没错就是这个样子，不知道为啥取名成这个样子
    yum install -y /usr/bin/sphinx-build # 没错就是这个样子

# 编译ovn-kubernetes cni插件
    1 先编译openvswitch 2.15.0
        官方提交了release包（make dist过）
        wget -k https://www.openvswitch.org/releases/openvswitch-2.15.0.tar.gz
        tar -zxvf openvswitch-2.15.0.tar.gz
        cd openvswitch-2.15.0
        ./boot.sh # 生成configure文件，这步最好不做，下一步使用官方的方式，不去做修改，避免引入其他传统
        ./configure --prefix=/usr --localstatedir=/var --sysconfdir=/etc
        make rpm-fedora # 生成rpm文件
        cp -r rpm/rpmbuild/RPMS/* ~/rpm/ovs-2.15.0  # 备份rpm 
    2 ovn编译打包rpm v21.06.0.tar.gz
        ovn官网没提供release的tar.gz，从github上拉取，使用21.06.0
        wget https://github.com/ovn-org/ovn/archive/v21.06.0.tar.gz
        tar -zxvf v21.06.0.tar.gz
        cd ovn-21.06.0/
        ./boot.sh # 生成configure文件
        将上面的ovs release打包环境地址传给configure命令
        ./configure --prefix=/usr --localstatedir=/var --sysconfdir=/etc --with-ovs-source=/root/openvswitch-2.15.0/
        官方文档提示要在ovs的目录下make dist，实际上并不需要，因为本身已经是编译目录
        make rpm-fedora
    3 打ovn-kubernetes的可用镜像
        openvswitch和ovn是ovn-kubernetes插件的基础，插件只是借助这2个工具创建路由交换拓扑图而已
        3.1 开始编译基础二进制文件
            首先下载源码，官方比较恶心，只有master分支，没有release，也没有分支，最近一次release和分支是2018年5月，因此不能随便升级这个插件
                git clone https://github.com/ovn-org/ovn-kubernetes.git
            编译4个基础组件: ovnkube ovn-kube-util ovndbchecker ovn-k8s-cni-overlay。在Dockerfile用到，第58和59行：
                cd ovn-kubernetes/go-controller/cmd/ovnkube && go build
                cd ovn-kubernetes/go-controller/cmd/ovn-kube-util && go build
                cd ovn-kubernetes/go-controller/cmd/ovndbchecker/ && go build
                cd ovn-kubernetes/go-controller/cmd/ovn-k8s-cni-overlay && go build
                cd /root/ovn-kubernetes/go-controller/cmd/ovnkube-trace && go build
                编译完成后，会在同目录下生产二进制文件ovnkube ovn-kube-util ovndbchecker ovn-k8s-cni-overlay ovnkube-trace
            拷贝二进制可执行文件到镜像build的目录下: 
                cd ovn-kubernetes/dist/images/
                cp -f ../../go-controller/cmd/ovnkube/ovnkube .
                cp -f ../../go-controller/cmd/ovn-kube-util/ovn-kube-util .
                cp -f ../../go-controller/cmd/ovndbchecker/ovndbchecker .
                cp -f ../../go-controller/cmd/ovnkube-trace/ovnkube-trace .
                cp -f ../../go-controller/cmd/ovn-k8s-cni-overlay/ovn-k8s-cni-overlay .
        3.2 拷贝第1、2两个步骤的rpm包到当前目录下
            cd ovn-kubernetes/dist/images/ && mkdir rpms && cd rpms
            cp /root/openvswitch-2.15.0/rpm/rpmbuild/RPMS/noarch/* .
            cp /root/openvswitch-2.15.0/rpm/rpmbuild/RPMS/x86_64/* .
            cp /root/ovn-21.06.0/rpm/rpmbuild/RPMS/x86_64/* .
        3.3 替换Dockerfile中关于ovn ovs软件的部分
            将Dockerfile中第37-53行替换成如下
                COPY rpms/* /root/

                RUN yum localinstall -y /root/*.rpm && \
                rm -f /root/*.rpm && \
                rm -rf /var/cache/yum && \
                mkdir -p /var/run/openvswitch
            打镜像，quay.chargebolt.com是我自建的的私有仓库，可以改成自己的私有仓库
                docker build -t quay.chargebolt.com/ovn/ovn-daemonset-u:2021.07.01 .
                docker push quay.chargebolt.com/ovn/ovn-daemonset-u:2021.07.01 .
# 搭建k8s集群，不是本文档的目的，不做赘述

# 按照模板生产yaml文件
cd ovn-kubernetes/dist/images
./daemonset.sh --image=quay.chargebolt.com/ovn/ovn-daemonset-u:2021.07.01 \
    --net-cidr=172.29.64.0/20 \
    --svc-cidr=172.30.64.0/20 \
    --v4-join-subnet=172.31.64.0/20 \
    --gateway-mode="local" \
    --k8s-apiserver=https://172.17.32.15:6443 \
    --master-loglevel="5" \
    --node-loglevel="5" \
    --dbchecker-loglevel="5" \
    --ovn-loglevel-northd="-vconsole:info -vfile:info" \
    --ovn-loglevel-nb="-vconsole:info -vfile:info" \
    --ovn-loglevel-sb="-vconsole:info -vfile:info" \
    --ovn-loglevel-controller="-vconsole:info" \
    --ovn-loglevel-nbctld="-vconsole:info"
    
    参数解释：我做了自定义修改，改成自己的设置网段
    v4-join-subnet参数指定的网段172.31.64.0/20，如果不指定网段，会使用默认的100.64/10网段,会和阿里云的100.64.0.0/10冲突（slb健康检查 oss地址等使用100段）
    net-cidr 集群pod网段
    svc-cidr 集群service网段
    k8s-apiserver 集群apiserver的地址,最后是域名

# 部署插件
    1 卸载集群原来的calico插件，并清理干净（最好重启写node，将vxlan网卡清理掉，清理干净）
    
    2 先启动openvswitch，不使用ovs.yaml文件
    在每台node上安装上一步生成的2个rpm文件 
    yum install -y openvswitch-2.15.0-1.el7.x86_64.rpm openvswitch-test-2.15.0-1.el7.noarch.rpm
    systemctl enable openvswitch
    systemctl start openvswitch

    3 开始部署组件
    kubectl apply -f ovn-setup.yaml
    kubectl apply -f ovnkube-db.yaml # 等待1-2分钟，STATUS running  READY 2/2
    kubectl apply -f ovnkube-master.yaml # 等待上一步 STATUS running  READY 2/2后再执行
    kubectl apply -f ovnkube-node.yaml # 等待上一步 STATUS running  READY 3/3后再执行
    kubectl get no 查看node是否ready

    4 部署一个daemonset，在每个worker node上都起1个pod
    随便找一个node 执行ping pod_ip，探测连通性

# 进阶 -- 网络打平方案
    极其适用于云网络，在阿里云上已经测试通过，配合阿里云的ccm，美滋滋 registry.ap-southeast-3.aliyuncs.com/acs/cloud-controller-manager-amd64:v1.9.3.339-g9830b58-aliyun
    方案链接
