#!/usr/bin/python3.6
# -*- coding: utf-8 -*-
import sys
import os
import time
import json
import IPy
import subprocess
import logging
import requests
import configparser
import traceback
def get_nodename():
    cmd = 'sh scripts/get_nodename.sh'
    output_str= subprocess.getoutput(cmd)
    return set(output_str.split())

def get_nodeCIDR():
    cmd = 'sh scripts/get_nodeCIDR.sh'
    output_str= subprocess.getoutput(cmd).strip()
    ret = {}
    for line in output_str.split('\n'):
        nodename = line.split()[0]
        nodeCIDR = line.split()[1]
        ret.update({nodename:nodeCIDR})
    return ret

def get_nodeIP():
    cmd = 'sh scripts/get_nodeIP.sh'
    output_str= subprocess.getoutput(cmd).strip()
    ret = {}
    nodeIP_list = set([])
    for line in output_str.split('\n'):
        nodename = line.split()[0]
        nodeIP = line.split()[1]
        nodeIP_list.add(nodeIP)
        ret.update({nodename:nodeIP})
    return ret, nodeIP_list

def get_northdb_podname():
    cmd = 'sh scripts/get_northdb_podname.sh'
    output_str= subprocess.getoutput(cmd)
    return output_str

def get_GR_config(northdb_podname, nodename):
    cmd = 'kubectl -n ovn-kubernetes exec -it %s -c nb-ovsdb -- ovn-nbctl show GR_%s' % (northdb_podname, nodename)
    output_str= subprocess.getoutput(cmd)
    return output_str

def get_node_no_SNAT_nexthop(northdb_podname, nodename):
    cmd = 'kubectl -n ovn-kubernetes exec -it %s -c nb-ovsdb -- ovn-nbctl --data=bare find Logical_Router_Port name=rtoj-GR_%s | grep networks' % (northdb_podname, nodename)
    output_str= subprocess.getoutput(cmd)
    netAddr_str = output_str.split(':')[1].strip()
    for ipaddr in netAddr_str.split():
        ip=ipaddr.split('/')[0]
        if IPy.IP(ip).version() == 4:
            return ip

def get_cluster_info_from_config(config, section, option):
    return config.get(section, option)

def generate_cmd_by_no_SNAT_net(no_SNAT_net, nodeCIDR, cluster_podCIDR, nexthop):
    if not IPy.IP(cluster_podCIDR) in IPy.IP(no_SNAT_net):
        cmd_add = 'ovn-nbctl lr-policy-add ovn_cluster_router 10 "ip4.src == %s && ip4.dst == %s" reroute %s' % (nodeCIDR, no_SNAT_net, nexthop)
        cmd_del = 'ovn-nbctl lr-policy-del ovn_cluster_router 10 "ip4.src == %s && ip4.dst == %s"' % (nodeCIDR, no_SNAT_net)
    else:
        cmd_add = 'ovn-nbctl lr-policy-add ovn_cluster_router 11 "ip4.src == %s && ip4.dst == %s && ip4.dst != %s" reroute %s' % (nodeCIDR, no_SNAT_net, cluster_podCIDR, nexthop)
        cmd_del = 'ovn-nbctl lr-policy-del ovn_cluster_router 11 "ip4.src == %s && ip4.dst == %s && ip4.dst != %s"' % (nodeCIDR, no_SNAT_net, cluster_podCIDR)
    return cmd_add, cmd_del

def generate_cmd_by_nodeip(nodeCIDR, other_nodeIP, nexthop):
    cmd_add = 'ovn-nbctl lr-policy-add ovn_cluster_router 12 "ip4.src == %s && ip4.dst == %s" reroute %s' % (nodeCIDR, other_nodeIP, nexthop)
    cmd_del = 'ovn-nbctl lr-policy-del ovn_cluster_router 12 "ip4.src == %s && ip4.dst == %s"' % (nodeCIDR, other_nodeIP)
    return cmd_add, cmd_del

def run_no_SNAT_cmd(northdb_podname, cmd):
    cmd = 'kubectl -n ovn-kubernetes exec -it %s -c nb-ovsdb -- %s' % (northdb_podname, cmd)
    return subprocess.getoutput(cmd)

def get_cluster_podCIDR_by_kubectl():
    cmd = 'cd scripts && sh get_cluster_podCIDR.sh'
    output_str= subprocess.getoutput(cmd)
    return output_str

if __name__ == "__main__":
    action = 'add'
    node = 'all'
    if len(sys.argv) > 1:
        action = sys.argv[1]
    if len(sys.argv) > 2:
        node = sys.argv[2]

    nodename_set = get_nodename()
    #print(nodename_set)

    nodeCIDR_dict = get_nodeCIDR()
    #print(nodeCIDR_dict)

    nodeIP_dict, nodeIP_list = get_nodeIP()
    print(nodeIP_list)

    northdb_podname = get_northdb_podname()
    print('northdb_podname:%s' % northdb_podname)

    #for nodename in nodename_set:
    #    GR_config = get_GR_config(northdb_podname, nodename)

    # set config file
    scritpPath = os.path.split(os.path.realpath(__file__))[0]
    config = configparser.ConfigParser()
    configFileName = 'conf/ovn.conf'
    configFile = scritpPath + '/' + configFileName
    config.read(configFile)

    # get podCIDR svcCIDR
    cluster_podCIDR = get_cluster_podCIDR_by_kubectl()
    print('podCIDR:%s' % cluster_podCIDR)

    # 将需要打平的命令写到列表里面
    cmd_all_add_set = set([])
    cmd_all_del_set = set([])
    cmd_node_add_dict = {}
    cmd_node_del_dict = {}
    # 打平网段
    no_SNAT_net_list = ['192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12']
    for no_SNAT_net in no_SNAT_net_list:
        for nodename in nodeCIDR_dict.keys():
            nodeCIDR = nodeCIDR_dict[nodename]
            nexthop = get_node_no_SNAT_nexthop(northdb_podname, nodename)
            cmd_add, cmd_del = generate_cmd_by_no_SNAT_net(no_SNAT_net, nodeCIDR, cluster_podCIDR, nexthop)
            cmd_all_add_set.add(cmd_add)
            cmd_all_del_set.add(cmd_del)
            if not nodename in cmd_node_add_dict.keys():
                cmd_node_add_dict[nodename] = []
            if not nodename in cmd_node_del_dict.keys():
                cmd_node_del_dict[nodename] = []
            cmd_node_add_dict[nodename].append(cmd_add)
            cmd_node_del_dict[nodename].append(cmd_del)
    # pod访问非本node的主网卡ip走mp0网卡，即ip= x.2
    nodeIp_list = nodeIP_dict.values()
    for nodename in nodeCIDR_dict.keys():
        nodeCIDR = nodeCIDR_dict[nodename]
        this_nodeIP = nodeIP_dict[nodename]
        netAddr = nodeCIDR.split('/')[0]
        nexthop_hex = hex(int(IPy.IP(netAddr).strHex(),base=16)+2)
        nexthop_ip = IPy.IP(nexthop_hex)
        for other_nodeIP in nodeIp_list:
            if other_nodeIP == this_nodeIP:
                continue
            cmd_add, cmd_del = generate_cmd_by_nodeip(nodeCIDR, other_nodeIP, nexthop_ip)
            cmd_all_add_set.add(cmd_add)
            cmd_all_del_set.add(cmd_del)
            cmd_node_add_dict[nodename].append(cmd_add)
            cmd_node_del_dict[nodename].append(cmd_del)
    #print(json.dumps(cmd_node_add_dict, indent=2))
    #print(json.dumps(cmd_node_del_dict, indent=2))
    #sys.exit()
    if action == 'add':
        if node == 'all':
            for cmd in cmd_all_add_set:
                print(cmd)
                run_no_SNAT_cmd(northdb_podname, cmd)
        else:
            if node in nodename_set:
                for cmd in cmd_node_add_dict[node]:
                    print(cmd)
                    run_no_SNAT_cmd(northdb_podname, cmd)
    if action == 'del':
        if node == 'all':
            for cmd in cmd_all_del_set:
                print(cmd)
                run_no_SNAT_cmd(northdb_podname, cmd)
        else:
            if node in nodename_set:
                for cmd in cmd_node_del_dict[node]:
                    print(cmd)
                    run_no_SNAT_cmd(northdb_podname, cmd)
    if action == 'list':
        cmd = 'ovn-nbctl lr-policy-list ovn_cluster_router'
        print(run_no_SNAT_cmd(northdb_podname, cmd))
