'''
@ Author: ZhouCH
@ Date: Do not edit
LastEditors: Please set LastEditors
LastEditTime: 2023-02-22 04:32:23
@ FilePath: Do not edit
@ Description: 
@ License: MIT
'''

from lark import Lark
from lark import Transformer
import math
from typing import List, Dict, Tuple
import random
import os
import sys

node_list=[] #contains all the node in the SoC

net_grammar = r"""
    net_list: net*

    net: "-" net_name ["(" "PIN" pin_name ")"] net_name_alias* ["+" regular_wiring_statement] ";"
    net_name: /(\w)+\[[0-9]+\]/
    pin_name: /(\w)+\[[0-9]+\]/

    //net_name_alias
    net_name_alias: "(" net_path net_alias")"
    net_path: /(\w|\/)+/
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

# TODO: doesn't successfully transform
class data_transformer(Transformer):
    def net_list(self, nets):
        return dict(nets)
    
    def net(self, net_info):
        net_name, net_param=net_info[0], list(net_info[1:-1])
        return net_name, net_param
    
    def net_name(self, name):
        return str(name)
    
    def pin_name(self, name):
        return str(name)
    
    def net_name_alias(self, alias_list):
        return list(alias_list)
    
    def net_path(self, path):
        return str(path)

    def net_alias(self, name):
        return str(name)
    
    def regular_wiring_statement(self, wire_list):
        return list(wire_list)
    
    def wire(self, wire_info):
        return list(wire_info)
    
    def layer(self, layer_name):
        return str(layer_name)
    
    def x(self, val):
        return int(val)
    def y(self, val):
        return int(val)
    def z(self, val):
        return str(val)
    def x_(self, val):
        return str(val)
    def y_(self, val):
        return str(val)
    def z_(self, val):
        return str(val)
    
    def via_name(self, name):
        return str(name)

def sorting(node:soc_node, second_near:int=1)->List[soc_node,float]:
    
    # TODO: logic problem. n1 is the nearest node of n2, but we can't be sure that n2 is the nearest node of n1
    # finding all the node in the same layout.
    node_in_same_layout_list=[]
    for n in node_list:
        if n.layout==node.layout:
            node_in_same_layout_list.append([n, 0]) #[another node, distance to a specified node]
    node_in_same_layout_list.remove([node, 0]) # remove node itself

    # calculate euclidean distances between node£¨wire starting point£©and other nodes£¨starting point£©
    # TODO: Discuss: we should calculate the nearest distance between two broken lines
    nearest_node=node_in_same_layout_list[0]
    second_nearest_node=nearest_node
    distance=math.dist(node_in_same_layout_list[0].location, node.location)
    second_distance=distance #TODO: check logic

    for ele in node_in_same_layout_list[1:]:
        ele[1]=math.dist(ele[0].location, node.location)
        if ele[1]<=distance:
            second_nearest_node=nearest_node
            second_distance=distance
            nearest_node=ele[0]
            distance=ele[1]

    return [nearest_node, distance, second_nearest_node, second_distance]

def file_sparser(file_name:str, node_map:str=None) -> List[soc_node]:
    all_node={}

    # read the file which is our target
    with open(file_name, "r") as input_file:
        data = input_file.read()
    net_input = data[data.find("NETS") + 4 : data.find("END NETS")]
    
    # sparse the doc.def and get all the useful information of each node
    net_parser = Lark(net_grammar, start='net_list', parser='lalr', )
    net_data = net_parser.parse(net_input)
    # print(net_data.pretty())

    # TODO: transform data to a dictionary {"node": [[aliasing_list], layer, x, y], ...}
    all_node=data_transformer().transform(net_data)
    
    # extract nodes that are in need
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
    print("argv[1] is the functional unit's node map, eg.'adder.map' ")
    node_list=file_sparser("ibex_top_working.def", sys.argv[1])

    # create pairs
    with open(sys.argv[1], "w") as output:
        while len(node_list)>0:
            # get net couple
            if len(node_list)%2==0:
                n1=random.sample(node_list, 1)
                n2=sorting(n1)[0]
                pair=[n1, n2]
                node_list.remove(pair[0])
                node_list.remove(pair[1])# TODO£º should I remove this ?
            elif len(node_list)%2==1:
                n1=random.sample(node_list, 1)
                n2=sorting(n1)[0]
                n3=sorting(n1)[2]
                pair=[n1, n2, n3]
                node_list.remove(pair[0])
                node_list.remove(pair[1])# TODO£º should I remove this ?
                node_list.remove(pair[2])# TODO£º should I remove this ?
            
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

