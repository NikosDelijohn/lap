'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-23 02:49:04
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark
from lark import Transformer
import math
from typing import List, Dict, Tuple, Any
import random
import os
import sys

node_list=[] #contains all the node in the SoC

net_grammar=r"""
    net_list: net*

    net: "-" net_name ["(" "PIN" pin_name ")"] net_aliasing_list ["+" regular_wiring_statement] ";"
    net_name: /(\w|\/|\[|\])+/
    pin_name: /(\w)+\[[0-9]+\]/

    //net_name_alias
    net_aliasing_list: net_name_alias*
    net_name_alias: "(" component_path net_alias")"
    component_path: /(\w|\/)+/
    net_alias: CNAME

    regular_wiring_statement: "ROUTED" wire ("NEW" wire)*
    wire: layer "(" x y z? ")" ["(" x_ y_ z_? ")"] [via_name] 
    layer: CNAME
    x:NUMBER|"*"
    y:NUMBER|"*"
    z:NUMBER|"*"
    x_:NUMBER|"*"
    y_:NUMBER|"*"
    z_:NUMBER|"*"
    via_name: CNAME

    %import common.SIGNED_NUMBER    
    %import common.NUMBER           
    %import common.CNAME            
    %import common.WS
    %ignore WS
    """

class soc_node:
    name=None
    alias=[]
    layout=[]
    location=[0,0]

    def __init__(self, name, alias, layout, location) -> None:
        self.name=name
        self.alias=alias
        self.layout=layout
        self.location=location

# {net_name: [pin_name, aliasing_dict{component: alias}, wire_dict{layer: start_point}]}
class data_transformer(Transformer):
    def net_list(self, nets):
        return dict(nets)
    
    def net(self, net_info):
        net_name, other_info=net_info[0], net_info[1:]
        return net_name, other_info
    
    def net_name(self, name):
        return str(name[0])
    
    def pin_name(self, name):
        return str(name[0])
    
    def net_aliasing_list(self, alias_list):
        return dict(alias_list)
    
    def net_name_alias(self, alias_pair):
        path, name=alias_pair[0], alias_pair[1] 
        return path, name
        
    def component_path(self, path):
        return str(path[0])

    def net_alias(self, name):
        return str(name[0])
    
    def regular_wiring_statement(self, wire_list):
        return dict(wire_list)
    
    def wire(self, wire_info):
        layer, other_info=wire_info[0], [wire_info[1],wire_info[2]]
        return layer, other_info
    
    def layer(self, layer_name):
        return str(layer_name[0])
    
    def x(self, val):
        return int(val[0])
    
    def y(self, val):
        return int(val[0])

def sorting(node:soc_node)->Tuple[soc_node, float, soc_node, float]:
    
    # TODO: logic problem. n1 is the nearest node of n2, but we can't be sure that n2 is the nearest node of n1
    # finding all the node in the same layout.
    node_in_same_layout_list=[]
    for n in node_list:
        if n.layout==node.layout:
            node_in_same_layout_list.append([n, 0]) #[another node, distance to a specified node]
    node_in_same_layout_list.remove([node, 0]) # remove node itself

    # calculate euclidean distances between node (wire starting point) and other nodes (starting point)
    # TODO: Discuss: we should calculate the nearest distance between two broken lines instead of starting node?
    nearest_node=node_in_same_layout_list[0]
    second_nearest_node=nearest_node
    distance=math.dist(node_in_same_layout_list[0].location, node.location)
    second_distance=distance #TODO: check second nearest node calculator's logic

    for ele in node_in_same_layout_list[1:]:
        ele[1]=math.dist(ele[0].location, node.location)
        if ele[1]<=distance:
            second_nearest_node=nearest_node
            second_distance=distance
            nearest_node=ele[0]
            distance=ele[1]

    return nearest_node, distance, second_nearest_node, second_distance

def file_sparser(file_name:str, node_map:str=None) -> List[soc_node]:
    all_node={}

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    net_input = data[data.find("NETS") + 4 : data.find("END NETS")]
    
    # sparse the doc.def and get all the useful information of each node
    net_parser = Lark(net_grammar, start='net_list')
    net_data = net_parser.parse(net_input)

    # transform data to a dictionary
    all_node=data_transformer().transform(net_data)

    # extract nodes that are needed
    if node_map!=None:
        with open (node_map, "r") as map_file:
            map_list=map_file.readlines()
        
        node_in_need={}
        for node_path in map_list:
            for node, info in all_node.items():
                if node_path in info[0]:
                    node_in_need[node]=info
    else:
        node_in_need_dict=all_node

    for k,v in node_in_need_dict.items():
        node_obj=soc_node(k, v[0], v[1], [v[2], v[3]])
        node_in_need.append(node_obj)

    return node_in_need

def main():
    print("#######################################################################")
    print("##  \033[33mHINT\033[0m: argv[1] is the functional unit's node map, eg.'adder.map'  ##")
    print("#######################################################################\n")
    
    if len(sys.argv)<=1:
        node_list=file_sparser("ibex_top_working.def")
    else:
        node_list=file_sparser("ibex_top_working.def", sys.argv[1])
    exit(0)
    # create pairs
    with open(sys.argv[1], "w") as output:
        while len(node_list)>0:
            # get net couple
            if len(node_list)%2==0:
                n1=random.sample(node_list, 1)
                n2=sorting(n1)[0]
                pair=[n1, n2]
                node_list.remove(pair[0])
                node_list.remove(pair[1])
            elif len(node_list)%2==1:
                n1=random.sample(node_list, 1)
                n2=sorting(n1)[0]
                n3=sorting(n1)[2]
                pair=[n1, n2, n3]
                node_list.remove(pair[0])
                node_list.remove(pair[1])
                node_list.remove(pair[2])
            
            # parse pair string
            p_lst=[]
            for p in pair:    
                p_lst.append(p.rstrip("\n"))
                print(p_lst)
            
            if len(p_lst)==2:
                output.write("{};{}\n".format(p_lst[0], p_lst[1]))
            elif len(p_lst)==3:
                output.write("{};{};{}\n".format(p_lst[0], p_lst[1], p_lst[2]))
        
if __name__=="__main__":
    main()

